#!/usr/bin/env python3

from common import * # Общие константы
import socket # Сетевые сокеты
import hashlib # Хеши

if __name__ == "__main__":
    # https://docs.python.org/3/howto/sockets.html
    # Создаём TCP-сокет 
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Привязываем его к локальному порту (ECHO_PORT --- константа из файла common.py)
    # Мы привязались к адресу localhost:ECHO_PORT, до такого сокета можно достучаться только с той же самой машины
    # Вместо localhost можно указать любой IP-адрес текущей машины (их может быть несколько) или 0.0.0.0 (все возможные адреса)
    # В питоне вместо "0.0.0.0" можно указать просто ""
    server_sock.bind(("localhost", ECHO_PORT))
    
    # Начинаем слушать входящие подключения
    server_sock.listen()

    # Ждём клиента
    (sock, address) = server_sock.accept()

    # Сервер больше не нужен --- его можно закрыть
    server_sock.close() 

    # Задание 1: 
    # В цикле считывайте сообщения от клиента и отправляйте их обратно до EOF
    raise NotImplementedError("Сервер, задание 1")
    # while True:
    #     sock.recv(...)
    #     ...
    #     sock.send(...)

    # Задание 2:
    # 1. Считайте длину сообщения от клиента, а потом ровно столько байт сообщения
    # 2. Посчитайте хеш сообщения
    # 3. Отправьте этот хеш клиенту
    # hashlib.sha256(...).digest()     
    