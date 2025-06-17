#!/usr/bin/env python3

from common import * # Общие константы
import shutil # чтобы скопировать файл
import filecmp # чтобы сравнить файлы
import mmap # memory mapping

if __name__ == "__main__":
    # Задание 6: 
    # В следующий раз (иил через раз) мы будем загружать файлы через BitTorrent.
    # В общем случае для этого потребуется запись в произвольное место файла (а не только в конец).
    # Такое можно сделать и с обычным файлом, открытым через open, перемещая текущее место записи через .seek.
    # Но мы поступим чуть-чуть хитрее: в питоне очень удобно пользоваться штукой, 
    # которая называется memory mapping: она позволяет притвориться, что байты файла находятся прямо в оперативной памяти,
    # и работать с ними как с обычным массивом

    shutil.copy("data/input", "data/work_copy.tmp")
    with open("data/work_copy.tmp", "a+") as f:
        with mmap.mmap(f.fileno(), 0) as file_bytes:
            # Задание поменяйте в файле все вхождения байтовой строки 0x33_33_33 на 0x39_3d_47
            # (3 байта на 3 байта, всё в BE (то есть 0x39 идёт в 1ый байт))
            raise NotImplementedError("Задание 6")
    
    if not filecmp.cmp("data/work_copy.tmp", "data/expected"):
        print("err")
    else:
        print("ok!")
        