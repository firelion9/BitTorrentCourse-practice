from typing import Optional
from bencode import *
from util import *
import pathlib
import hashlib


class TorrentMetadata:
    def __init__(
            self, 
            info_hash: bytes,
            trackers: list[list[str]], piece_len: int, pieces: list[bytes], files: list[tuple[int, pathlib.Path]], 
            creation_date: Optional[int], comment: Optional[str], created_by: Optional[str]
    ) -> None:
        self.info_hash = info_hash
        self.trackers = trackers
        self.piece_len = piece_len
        self.pieces = pieces
        self.files = files
        self.creation_date = creation_date
        self.comment = comment
        self.created_by = created_by
        self.total_len = sum(map(lambda f: f[0], files))

    def __str__(self) -> str:
        return f"""
pieces={list(map(bytes.hex, self.pieces))}
info_hash={self.info_hash.hex()}
trackers={self.trackers}
piece_len={self.piece_len}
files={self.files}
creation_date={self.creation_date}
comment={self.comment}
created_by={self.created_by}
"""

    @staticmethod
    def parse(data: bytes) -> 'TorrentMetadata':
        inp = ParserInput(data)

        metafile = parse_bencoded(inp)
        inp.require_consumed()
        info_marks = [(off, tag) for (off, (tag, key)) in inp.marks if key == "info"]

        # Задание 4: распарсите .torrent файл.
        # Вам пригодятся функции из util:
        # get_field(dict, field, type) --- получить поле с указным типом, например get_field(info, "name", bytes)
        #                                  Никаких преобразований типов не происходит! Все строки у нас на  самом деле bytes
        # get_field_or_default(dict, field, type, default) --- позволяет указать значение по-умолчанию, например
        #                                                      get_field_or_default(metafile, "announce-list", list[list[bytes]], [])
        # chunked(data, chunk_len) --- нарезает массив байт на кусочки равной длины 


        # if len(info_marks) != 2:
        #     raise RuntimeError("Unsupported torrent file: expect single `info` key")
        # info_hash=hashlib.sha1(data[info_marks[0][0]:info_marks[1][0]]).digest()
        
        trackers = [[get_field(metafile, "announce", bytes).decode()]]
        # Добавите announce-list. Помните, что это *список списков*
        trackers.extend(...)

        info = get_field(metafile, "info", dict[str, Any])
        
        files = []
        if "length" in info:
            # single-file
            # Поля length и name
            files.append((..., pathlib.Path(...)))
        else:
            # multi-file
            # Поля name и files
            # name --- имя корневой папки
            # files --- список словарей
            #  - length --- длина файла
            #  - path --- путь в виде списка элементов пути. 
            #             То есть root/some/path/to/file будет записан как
            #             ["some", "path", "to", "file"], а "root" пойдёт в name
            
            # fs = [(..., pathlib.Path(name, *map(bytes.decode, ...)))
            #         for f in ...]
            files.extend(...)

        return TorrentMetadata(
            info_hash=...,
            trackers=trackers,
            piece_len=..., # "piece length"
            pieces=..., # "pieces"
            files=files,
            creation_date=..., # "creation date"
            comment=map_optional(bytes.decode, ...), # "comment"
            created_by=map_optional(bytes.decode, ...), # "created by"
        )
    
    
    # Домашнее задание 2: напишите энкодер .torrent-файла.
    # Мы можете пока считать, что мы работаем исключительно с single-file раздачами
    def encode(self) -> bytes:
        return ...

