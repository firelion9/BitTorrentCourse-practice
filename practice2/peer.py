#!/usr/bin/env python3

import abc
from dataclasses import dataclass
import hashlib
from logging import warning
from mmap import mmap, ACCESS_WRITE
import pathlib
import concurrent.futures
import requests
import struct
import time
import threading
import socket
import queue
from collections import deque
import metafile
from bencode import *
from util import *

_SOCK_TIMEOUT = 30
_MIN_ANNOUNCE_INTERVAL = 30
_FAILURE_ANNOUNCE_INTERVAL = 60 * 60
_PEER_AVG_SPEED_INTERVAL = 20
_REQUEST_SIZE = 16 * 1024
_SYNC_INTERVAL = 10

_T = TypeVar("__T")


class BtCommunicationMessage:
    @classmethod
    @abc.abstractmethod
    def tag(cls) -> int | None: ...

    @classmethod
    @abc.abstractmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T: ...

    def encode(self) -> bytes:
        body = self.encode_body()
        res = bytearray()
        res.extend(len(body).to_bytes(length=4, byteorder="big"))
        res.extend(body)
        return res

    @abc.abstractmethod
    def encode_body(self) -> bytes: ...


class KeepAlive(BtCommunicationMessage):
    @classmethod
    def tag(cls) -> int | None:
        return None

    def encode_body(self) -> bytes:
        return b""


@dataclass
class Choke(BtCommunicationMessage):
    @classmethod
    def tag(cls) -> int | None:
        return 0

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        return Choke()  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack("B", Choke.tag())


@dataclass
class Unchoke(BtCommunicationMessage):
    @classmethod
    def tag(cls) -> int | None:
        return 1

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        return Unchoke()  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack("B", Unchoke.tag())


@dataclass
class Interested(BtCommunicationMessage):
    @classmethod
    def tag(cls) -> int | None:
        return 2

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        return Interested()  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack("B", Interested.tag())


@dataclass
class NotInterested(BtCommunicationMessage):
    @classmethod
    def tag(cls) -> int | None:
        return 3

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        return NotInterested()  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack("B", NotInterested.tag())


@dataclass
class Have(BtCommunicationMessage):
    piece_idx: int

    @classmethod
    def tag(cls) -> int | None:
        return 4

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        return Have(struct.unpack(">I", data)[0])  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack(">BI", Have.tag(), self.piece_idx)


@dataclass
class Bitfield(BtCommunicationMessage):
    bitfield: Bitset

    @classmethod
    def tag(cls) -> int | None:
        return 5

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        return Bitfield(Bitset(data))  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack(
            f"B{len(self.bitfield.data)}s", Bitfield.tag(), self.bitfield.data
        )


@dataclass
class Request(BtCommunicationMessage):
    index: int
    begin: int
    length: int

    @classmethod
    def tag(cls) -> int | None:
        return 6

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        index, begin, length = struct.unpack(">III", data)
        return Request(index, begin, length)  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack(">BIII", Request.tag(), self.index, self.begin, self.length)


@dataclass
class Piece(BtCommunicationMessage):
    index: int
    begin: int
    block: bytes

    @classmethod
    def tag(cls) -> int | None:
        return 7

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        index, begin, block = struct.unpack(f">II{len(data) - 8}s", data)
        return Piece(index, begin, block)  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack(">BIIs", Request.tag(), self.index, self.begin, self.block)


@dataclass
class Cancel(BtCommunicationMessage):
    index: int
    begin: int
    length: int

    @classmethod
    def tag(cls) -> int | None:
        return 8

    @classmethod
    def decode_body(cls: Type[_T], data: bytes) -> _T:
        index, begin, length = struct.unpack(">III", data)
        return Cancel(index, begin, length)  # type: ignore

    def encode_body(self) -> bytes:
        return struct.pack(">BIII", Cancel.tag(), self.index, self.begin, self.length)


def _decode_msg(data: bytes) -> BtCommunicationMessage:
    if len(data) == 0:
        return KeepAlive()

    tag = data[0]

    msg_clses = [
        Choke,
        Unchoke,
        Interested,
        NotInterested,
        Have,
        Bitfield,
        Request,
        Piece,
        Cancel,
    ]

    for msg_cls in msg_clses:
        if tag == msg_cls.tag():
            return msg_cls.decode_body(data[1:])

    raise ParseError(f"Illegal message id {tag}")


class Peer:
    def __init__(
        self, out_dir: pathlib.Path, metadata: metafile.TorrentMetadata, id: bytes
    ) -> None:
        now = int(time.time())

        self.out_dir = out_dir
        self.metadata = metadata
        self.id = id
        self.trackers: list[list[tuple[str, int, int]]] = [
            [
                (tr, now - _MIN_ANNOUNCE_INTERVAL - 1, now)
                for tr in trs
                if tr.startswith("http")
            ]
            for trs in metadata.trackers
        ]
        self.known_peers: set[tuple[str, int]] = set()

    def announce_peers(self, event: str | None = None):
        self.trackers = [
            [self.__announce_at(tracker) for tracker in trs] for trs in self.trackers
        ]

    def __announce_at(
        self, tracker: tuple[str, int, int], event: str | None = None
    ) -> tuple[str, int, int]:
        now = int(time.time())
        if now < tracker[1] + _MIN_ANNOUNCE_INTERVAL:
            return tracker

        params = {
            # эти 4 параметра пока оставим такими
            "port": str(0),
            "uploaded": str(0),
            "downloaded": str(0),
            "left": str(self.metadata.piece_len * len(self.metadata.pieces)),
            # TODO задание 5
            ...: ...,
        }
        if not event is None:
            params["event"] = event

        res = requests.get(tracker[0], params=params)
        if res.ok:
            response = parse_bencoded(ParserInput(res.content))
            # TODO задание 5
            interval = ...
            peers = ...  # get_field(response, "peers", list | bytes)

            with self.peers_lock:
                for p in peers:
                    self.known_peers.add(p)

            return (tracker[0], now, now + interval)

        return (tracker[0], now, now + _FAILURE_ANNOUNCE_INTERVAL)


if __name__ == "__main__":
    # Задание 5: сделайте анонс на трекер на сервере.
    # В data/practice1.torrent есть пример торрент-файла, в котором уже прописан нужный трекер
    # В качестве id укажите
    meta = metafile.TorrentMetadata.parse(
        pathlib.Path("data/practice1.torrent").read_bytes()
    )

    peer = Peer(pathlib.Path("data"), meta, id=b"-qB5100-.fsanoifneawolcasdaw"[0:20])
    peer.announce_peers()
