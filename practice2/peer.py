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
import secrets
import random

_SOCK_TIMEOUT = 30
_MIN_ANNOUNCE_INTERVAL = 30
_FAILURE_ANNOUNCE_INTERVAL = 60 * 60
_PEER_AVG_SPEED_INTERVAL = 20
_REQUEST_SIZE = 16 * 1024
_SYNC_INTERVAL = 10
_OPTIMISTIC_LIVE_INTERVALS = 3
_MAX_REQUESTS = 1000
_MAX_PEERS = 50

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


@dataclass(frozen=True)
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
        return struct.pack(f">BII{len(self.block)}s", Piece.tag(), self.index, self.begin, self.block)


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


class PeerConnection:
    def __init__(
        self,
        my_id: bytes,
        metadata: metafile.TorrentMetadata,
        sock: socket.socket,
        is_initiator: bool,
        handle_piece: Callable[[Piece], None],
        handle_request: Callable[[Request], Optional[bytes]],
        on_disconnected: Callable[['PeerConnection', tuple[str, int]], None] = (lambda x, y: ...),
    ) -> None:
        self.my_id = my_id
        self.info_hash = metadata.info_hash
        self.sock = sock
        self.handle_piece = handle_piece
        self.handle_request = handle_request
        addr = sock.getsockname()
        self.on_disconnected = lambda: on_disconnected(self, addr)

        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False

        self.peer_bitfield = Bitset(len(metadata.pieces))
        self.download_records = deque()
        self.window_downloaded = 0
        self.data_lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.request_cond = threading.Condition(self.data_lock)
        self.is_closing = False
        
        self.peer_requests: set[Request] = set()

        self.peer_id: bytes

        self.send_thread = threading.Thread(target=self._send_loop)
        self.receive_thread = threading.Thread(target=self._receive_loop)

        self._handshake(is_initiator)

        self.receive_thread.start()
        self.send_thread.start()

    def _handshake(self, is_initiator: bool):
        # Задание 3.1: реализуйте BitTorrent-рукопожатие
        # Вам нужно написать 2 функции:
        # - send_handshake --- послать рукопожатие по self.sock
        # - receive_handshake --- получить рукопожатие. Тут надо проверить 
        #                         совпадение инфо-хешей и проставить self.peer_id

        self.sock.settimeout(_SOCK_TIMEOUT)
        protocol = b"BitTorrent protocol"

        def send_handshake():
            # TODO задание 3.1 
            self.sock.sendall(
                struct.pack(
                    ...
                )
            )

        def receive_handshake():
            # TODO задание 3.1
            # Для чтения байт используйте self._recv_bytes(cnt)
            flags, hash, id = ...
            self.peer_id = id

        if is_initiator:
            send_handshake()
            receive_handshake()
        else:
            receive_handshake()
            send_handshake()

        self.sock.settimeout(None)

    def send_msg(self, msg: BtCommunicationMessage) -> None:
        with self.send_lock:
            self.__send_msg(msg)

    def recv_msg(self) -> BtCommunicationMessage:
        msg_len = int.from_bytes(self._recv_bytes(4), byteorder="big")
        msg_bytes = self._recv_bytes(msg_len)
        return _decode_msg(msg_bytes)

    def peer_has_piece(self, piece_idx: int) -> None:
        with self.data_lock:
            return len(self.peer_bitfield) > piece_idx and self.peer_bitfield[piece_idx]

    def may_request(self):
        return self.am_interested and not self.peer_choking

    def on_have_piece(self, piece_idx: int) -> None:
        self.send_msg(Have(piece_idx))

    def avg_download_speed(self) -> float:
        with self.data_lock:
            self.__roll_download_statistics_history(int(time.time()))
            return self.window_downloaded / _PEER_AVG_SPEED_INTERVAL

    def choke(self) -> None:
        with self.send_lock:
            self.__send_msg(Choke())
            self.am_choking = True

    def unchoke(self) -> None:
        with self.send_lock:
            self.__send_msg(Unchoke())
            self.am_choking = False

    def interested(self) -> None:
        with self.send_lock:
            self.__send_msg(Interested())
            self.am_interested = True

    def not_interested(self) -> None:
        with self.send_lock:
            self.__send_msg(NotInterested())
            self.am_interested = False

    def close(self):
        with self.data_lock:
            if self.is_closing:
                return
            self.is_closing = True
        
        self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()
        self.receive_thread.join()
        with self.data_lock:
            self.request_cond.notify_all()
        self.send_thread.join()

    def _recv_bytes(self, cnt: int) -> bytes:
        buffer = bytearray()
        while len(buffer) < cnt:
            r = self.sock.recv(cnt - len(buffer))
            if len(r) == 0:
                raise IOError("Broken socket")
            buffer.extend(r)

        return buffer

    def _send_loop(self):
        try:
            while True:
                with self.data_lock:
                    while len(self.peer_requests) == 0 and self.receive_thread.is_alive():
                        self.request_cond.wait()
                    if len(self.peer_requests) == 0:
                        return
                    request = self.__pop_request()
                    data = self.handle_request(request)
                
                if not data is None:
                    with self.send_lock:
                        if not self.am_choking:
                            self.__send_msg(Piece(request.index, request.begin, data))
        except IOError:
            try: 
                self.sock.close()
            except ...: ...
            with self.data_lock:
                if not self.is_closing:
                    self.on_disconnected()

    def _receive_loop(self):
        try:
            while True:
                msg = self.recv_msg()

                match msg:
                    case Choke():
                        self.peer_choking = True
                    case Unchoke():
                        self.peer_choking = False
                    case Interested():
                        self.peer_interested = True
                    case NotInterested():
                        self.peer_interested = False
                    case Bitfield(bitfield):
                        with self.data_lock:
                            self.peer_bitfield = bitfield
                    case Have(idx):
                        with self.data_lock:
                            self.peer_bitfield[idx] = True
                    case Request(idx, offset, plen):
                        if not self.am_choking:
                            with self.data_lock:
                                if len(self.peer_requests) < _MAX_REQUESTS:
                                    self.peer_requests.add(msg)
                                    self.request_cond.notify()
                    case Piece(idx, offset, block):
                        self.handle_piece(msg)
                    case Cancel(idx, offset, plen):
                        with self.data_lock:
                            self.peer_requests.remove(msg)
        except IOError:
            try: 
                self.sock.close()
            except ...: ...
            with self.data_lock:
                if not self.is_closing:
                    self.on_disconnected()


    def _on_piece_received(self, piece: Piece) -> None:
        self.handle_piece(self.peer_id, piece)

    def __pop_request(self) -> Optional[Request]:
        if len(self.peer_requests) == 0:
            return None
        else:
            return self.peer_requests.pop()
        
    def __send_msg(self, msg: BtCommunicationMessage) -> None:
        self.sock.sendall(msg.encode())


class Peer:
    def __init__(
        self,
        out_dir: pathlib.Path,
        metadata: metafile.TorrentMetadata, 
        id: bytes,
        port: int = 0,
        on_sub_piece: Callable[[Any, int], None] = (lambda x: ...),
    ) -> None:
        now = int(time.time())

        self.out_dir = out_dir
        self.metadata = metadata
        self.id = id if isinstance(id, bytes) else id.encode()
        self.on_sub_piece = on_sub_piece
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.bind(("", port))
        self.trackers: list[list[tuple[str, int, int]]] = [
            [
                (tr, now - _MIN_ANNOUNCE_INTERVAL - 1, now)
                for tr in trs
                if tr.startswith("http")
            ]
            for trs in metadata.trackers
        ]
        self.known_peers: set[tuple[str, int]] = set()
        self.peers: dict[tuple[str, int], PeerConnection] = dict()

        self.peers_lock = threading.Lock()
        self.file_lock = threading.Lock()

        out_dir.mkdir(exist_ok=True)
        self.data_file = self.__data_file(out_dir, metadata).open("a+b")
        self.data_file_mmap = mmap(
            self.data_file.fileno(), self.metadata.total_len, access=ACCESS_WRITE
        )
        self.bitfield = Bitset(len(metadata.pieces))
        self.sub_pieces = Bitset(
            (metadata.total_len + _REQUEST_SIZE - 1) // _REQUEST_SIZE
        )
        self.sub_pieces_per_piece = (
            len(self.sub_pieces) + len(metadata.pieces) - 1
        ) // len(metadata.pieces)
        self.executor = concurrent.futures.ThreadPoolExecutor()
        self.accept_thread = threading.Thread(target=self.__accept_job)

        self.check_data()

        self.accept_thread.start()

    def announce_peers(self, event: str | None = None):
        self.trackers = [
            [self.__announce_at(tracker) for tracker in trs] for trs in self.trackers
        ]

    @staticmethod
    def __data_file(out_dir: pathlib.Path, metadata: metafile.TorrentMetadata) -> pathlib.Path:
        if len(metadata.files) == 1:
            file = metadata.files[0][1]
            if len(file.parts) == 1 and file.parts[0] not in ['.', '..']:
                return out_dir / file.parts[0]
            
        return out_dir / (metadata.info_hash.hex() + ".!t")
       
    # TODO: Не забудьте поменять порт на str(self.listen_socket.getsockname()[1])
    def __announce_at(
        self, tracker: tuple[str, int, int], event: str | None = None
    ) -> tuple[str, int, int]:
        now = int(time.time())
        if now < tracker[1] + _MIN_ANNOUNCE_INTERVAL:
            return tracker

        params = {
            "port": str(self.listen_socket.getsockname()[1]),
            "uploaded": str(0),
            "downloaded": str(0),
            "left": str(self.metadata.piece_len * len(self.metadata.pieces)),
            # TODO задание 2.5
            ...: ...,
        }
        if not event is None:
            params["event"] = event

        res = requests.get(
            tracker[0], 
            params=params,
            # headers={"uid": ..., "token": ...}
            )
        if res.ok:
            response = parse_bencoded(ParserInput(res.content))
            # TODO задание 2.5
            interval = ...
            peers = ...  # get_field(response, "peers", list | bytes)

            with self.peers_lock:
                for p in peers:
                    self.known_peers.add(p)

            return (tracker[0], now, now + interval)
        else:
            print(res, res.content)
        return (tracker[0], now, now + _FAILURE_ANNOUNCE_INTERVAL)

    def check_data(self) -> None:
        # Задание 3.2: проверьте целостность файла с данными (self.data_file_mmap).
        # Вам нужно посчитать посчитать SHA-1 хеши всех частей файла 
        # (каждая кроме последней по self.metadata.piece_len байт)
        # и сравнить и их со значениями self.metadata.pieces
        ...

    def _handle_piece(self, piece: Piece) -> None:
        if (
            piece.begin % _REQUEST_SIZE != 0
            or len(piece.block) != _REQUEST_SIZE
            and (
                piece.index * self.sub_pieces_per_piece + piece.begin // _REQUEST_SIZE
                != len(self.sub_pieces) - 1
            )
        ):
            warning(RuntimeWarning(f"Unaligned block {piece}"))
            return
        with self.file_lock:
            idx = piece.index * self.sub_pieces_per_piece + piece.begin // _REQUEST_SIZE
            off = idx * _REQUEST_SIZE
            self.data_file_mmap[off : off + len(piece.block)] = piece.block
            self.data_file_mmap.flush()
            self.sub_pieces[idx] = True
            sub_pieces_range = range(
                piece.index * self.sub_pieces_per_piece,
                min(
                    (piece.index + 1) * self.sub_pieces_per_piece, len(self.sub_pieces)
                ),
            )
            if all(map(lambda i: self.sub_pieces[i], sub_pieces_range)):
                offset = self.metadata.piece_len * piece.index
                end = min(offset + self.metadata.piece_len, self.metadata.total_len)
                has_part = (
                    hashlib.sha1(self.data_file_mmap[offset:end]).digest()
                    == self.metadata.pieces[piece.index]
                )
                if has_part:
                    self.data_file_mmap.flush()
                    self.bitfield[piece.index] = True
                    with self.peers_lock:
                        for p in self.peers.values():
                            self.executor.submit(p.on_have_piece, piece.index)
                else:
                    for i in sub_pieces_range:
                        self.sub_pieces[i] = False
        self.on_sub_piece(self, idx)

    def _handle_request(self, request: Request) -> Optional[bytes]:
        if request.begin + request.length > self.metadata.piece_len or request.length <= 0 or request.begin < 0 or request.length > _REQUEST_SIZE * 2:
            warning(RuntimeWarning(f"Illegal request {request}"))
            return None
        begin = request.index * self.metadata.piece_len + request.begin
        end = begin + request.length
        if end > self.metadata.total_len:
            warning(RuntimeWarning(f"Out of range request {request}"))
            return None
        
        with self.file_lock:
            if not self.bitfield[request.index]:
                return None
            
            return self.data_file_mmap[begin:end]
        
    def request_block(self, piece_idx: int, block_idx: int) -> None:
        size = min(
            self.metadata.total_len
            - (piece_idx * self.sub_pieces_per_piece + block_idx) * _REQUEST_SIZE,
            _REQUEST_SIZE,
        )
        msg = Request(piece_idx, block_idx * _REQUEST_SIZE, size)
        while True:
            with self.peers_lock:
                ps = [p for p in self.peers.values() if p.peer_has_piece(piece_idx) and p.may_request()]
                if len(ps) > 0:
                    p = random.choice(ps)
                    p.send_msg(msg)
                    return

            time.sleep(_SYNC_INTERVAL)

    def connect_to_peer(self, peer: tuple[str, int]) -> None:
        def connect() -> socket.socket:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(peer)
            return sock
        self._connect_to_peer(peer, connect, is_initiator=True)

    def try_connect_to_peer(self, peer: tuple[str, int]) -> bool:
        try:
            self.connect_to_peer(peer)
            return True
        except Exception as e:
            warning(e)
            return False

    def _connect_to_peer(self, peer: tuple[str, int], make_sock: Callable[[], socket.socket], is_initiator: bool) -> None:
        with self.peers_lock:
            if peer in self.peers:
                return
            sock = make_sock()
            conn = PeerConnection(
                self.id,
                self.metadata,
                sock,
                is_initiator=is_initiator,
                handle_piece=self._handle_piece,
                handle_request=self._handle_request,
                on_disconnected=self._on_disconnected,
            )
            self.peers[peer] = conn
            conn.send_msg(Bitfield(Bitset(self.bitfield)))

    def _on_disconnected(self, connection: PeerConnection, addr: tuple[str, int]) -> None:
        with self.peers_lock:
            if addr in self.peers and self.peers[addr] == connection:
                connection = self.peers.pop(addr)
                self.executor.submit(lambda: connection.close())

    def __accept_job(self) -> None:
        self.listen_socket.listen()
        try:
            while True:
                sock, peer = self.listen_socket.accept()
                with self.peers_lock:
                    if len(self.peers) >= _MAX_PEERS:
                        sock.shutdown()
                        sock.close()
                        sock = None
                
                if sock is None:
                    time.sleep(_SYNC_INTERVAL)
                    continue

                print(f"incoming {peer}")
                def action():
                    self._connect_to_peer(peer, lambda: sock, is_initiator=False)
                    self.peers[peer].unchoke()
                self.executor.submit(action)
        except IOError:
            ...

    def close(self) -> None:
        self.listen_socket.close()

        with self.peers_lock:
            for p in self.peers.values():
                try:
                    p.close()
                except:
                    ...
            self.peers.clear()

        with self.file_lock:
            self.data_file_mmap.close()
            self.data_file.close()

        self.executor.shutdown()
        self.accept_thread.join()

    def __enter__(self):
        try:
            self.announce_peers(event="started")
        except:
            self.close()
            raise

        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        peer.announce_peers(event="stopped")
        self.close()

if __name__ == "__main__":
    # Задание 2.5: сделайте анонс на трекер на сервере.
    # В data/practice1.torrent есть пример торрент-файла, в котором уже прописан нужный трекер
    # Чтобы в получить баллы в боте, отправьте 2 дополнительных заголовка (не параметра!):
    # - uid --- uid из бота строкой 
    # - token --- токен из бота (без каких-либо дополнительных преобразований)
    # Как только вы убедитесь, что баллы засчитаны --- уберите передачу заголовков, больше они не понадобятся  
    meta = metafile.TorrentMetadata.parse(
        pathlib.Path("data/image.jpg.torrent").read_bytes()
    )

    block_idx = 0
    received_parts = 0
    next_lock = threading.Lock()
    cond = threading.Condition(next_lock)

    def request_next(peer: Peer, idx: int) -> None:
        global block_idx
        global received_parts
        global next_lock
        global cond
        with next_lock:
            if idx >= 0:
                received_parts += 1
                if received_parts == len(peer.sub_pieces):
                    cond.notify()
            if block_idx == -1:
                if received_parts == len(peer.sub_pieces):
                    cond.notify()
                return

            peer.request_block(
                block_idx // peer.sub_pieces_per_piece,
                block_idx % peer.sub_pieces_per_piece,
            )
            block_idx += 1
            if block_idx == len(peer.sub_pieces):
                block_idx = -1

    with Peer(
        pathlib.Path("data"),
        meta,
        id=..., #TODO: выберете случайный 20-байтный id,
        on_sub_piece=request_next,
    ) as peer:
        while block_idx != -1 and peer.sub_pieces[block_idx]:
            received_parts += 1
            block_idx += 1
            if block_idx == len(peer.sub_pieces):
                block_idx = -1

        has_whole_file = received_parts == len(peer.sub_pieces)

        for p in peer.known_peers:
            print(f"Connecting to {p}")
            if peer.try_connect_to_peer(p):
                peer.peers[p].unchoke()
                if not has_whole_file: 
                    peer.peers[p].interested()
                print("Connected")
            else:
                print("Failed")

        time.sleep(3)
        request_next(peer, -1)
        request_next(peer, -1)
        request_next(peer, -1)

        if not has_whole_file:
            with next_lock:
                cond.wait()

        print("File downloaded")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            ...
        
        print("shutting down...")
