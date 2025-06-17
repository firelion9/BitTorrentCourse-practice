import socket

# Порт, на котором работает эхо-сервер
ECHO_PORT = 42346

BUFFER_SIZE = 2 ** 13

# Посылает указанное сообщение по сокету
def socket_send(sock: socket.socket, msg):
    offset = 0
    while offset < len(msg):
        sent = sock.send(msg[offset:])
        if sent == 0:
            raise RuntimeError("socket connection broken")
        offset = offset + sent

# Принимает сообщение **ровно** указанной длины из сокета
def socket_receive(sock: socket.socket, length: int):
    chunks = []
    received_cnt = 0
    while received_cnt < length:
        chunk = sock.recv(min(length - received_cnt, BUFFER_SIZE))
        if chunk == b'':
            raise RuntimeError("socket connection broken")
        chunks.append(chunk)
        received_cnt = received_cnt + len(chunk)
    return b''.join(chunks)
