#!/usr/bin/env python3

from common import * # Общие константы
import socket # Сетевые сокеты
import hashlib # Хеши
import secrets # Криптографический генератор псевдослучайных чисел

if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Задание 3:
    # 1. Получите uid и секрет у тг-бота 
    # 2. Реализуйте следующий протокол общения с сервером:
    #   1. Клиент посылает 4 байта [0xb1, 0x10, 0x4e, 0xc0], свой uid как 4 BE байта и ещё 16 случайных байт (client_r)
    #   2. Сервер присылает свои 16 случайных байт (server_r)
    #   3. Клиент посылает sha256(<server_r>:<client_r>:<secret>) (угловые скобки не входят в хеш, а двоеточия --- да)
    #   4. Сервер Присылает 3 байта: строку "Ok!", если всё хорошо, и "Err" иначе
    
    # Вам может пригодиться метод int.to_bytes(cnt, "little"|"big")
    # или даже https://docs.python.org/3/library/struct.html (но можно и без этого)

    # Для генерации случайных байт используйте secrets.token_bytes(cnt)

    raise NotImplementedError("Задание 3")

    # sock.connect((host, port))