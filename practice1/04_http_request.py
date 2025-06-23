#!/usr/bin/env python3

from common import * # Общие константы
import requests # HTTP-запросы
import hashlib # Хеши

if __name__ == "__main__":
    # Задание 4: 
    # 1. Отправите на сервер GET-запрос /day1/task4/rs, в теле он вернёт строку rs
    # 2. Сгенерируйте случайную строку rc
    # 3. Посчитайте challenge=sha256(<rs>:<rc>:<secret>).hex()
    # 4. Отправьте на сервер POST-запрос по пути /day1/task4/auth, в заголовки передайте:
    #    - X-uid=uid
    #    - X-rc=rc
    #    - X-challenge=challenge
    #    Сервер отвечает JSON-ом с описанием ошибки или с .result="Ok!" 
    
    raise NotImplementedError("Задание 4")
    # requests.get(...).content
    # requests.post(..., headers={...}).content

    # Задание 5: 
    # В последнем запросе отправьте параметры в теле запроса в json с полями uid, rc и challenge.
    # Закодируйте все параметры как строки.
    # Новый путь --- /day1/task5/auth
    