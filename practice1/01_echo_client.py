#!/usr/bin/env python3

from common import * # Общие константы
import socket # Сетевые сокеты

if __name__ == "__main__":
    # https://docs.python.org/3/howto/sockets.html
    # Создаём TCP-сокет 
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Подключаемся к серверу
    # localhost --- специальный DNS-адрес, который резолвится в так называемый "loopback interface"
    # Пакеты, отправленные на него, возвращаются обратно на компьютер и не уходят в сеть
    # Вместо него можно указать 127.0.0.1
    # ECHO_PORT --- константа из файла common.py.
    # Можете поменять её, но не используйте порты <= 2048
    sock.connect(("localhost", ECHO_PORT))

    # Задание 1: 
    # 1. Считайте строку из stdin
    # 2. Отправьте её через сокет
    # 3. Получите и выведите ответ от сервера 
    raise NotImplementedError("Клиент, задание 1")
    # Подсказка: str.encode(), bytes.decode()
    # sock.send(...)
    # ...
    # sock.recv(...)
    # ...

    # Задание 2: 
    # 1. Отправьте длину строчки перед ней самой (можно считать, что она меньше 256)
    # 2. Получите от сервера хеш и выведите его в виде 16-ричного числа (bytes.hex())
    