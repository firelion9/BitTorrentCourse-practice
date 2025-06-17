from typing import Any, Callable, TypeVar

__T = TypeVar('__T')

class ParserInput:
    def __init__(self, data: bytes|str, offset: int = 0) -> None:
        self.data = data if isinstance(data, bytes) else data.encode() # type: ignore
        self.offset = offset
        self.marks: list[tuple[int, Any]] = []

    def consume_char(self) -> str:
        return self.consume_chars(1)
    
    def peek_char(self) -> str:
        return self.peek_chars(1)
    
    def peek_chars(self, cnt: int) -> str:
        self.__check_len(cnt)
        res = self.data[self.offset:self.offset+cnt]
        return res.decode()

    def consume_chars(self, cnt: int) -> str:
        res = self.peek_chars(cnt)
        self.offset += cnt
        return res

    def peek_bytes(self, cnt: int) -> bytes:
        self.__check_len(cnt)
        res = self.data[self.offset:self.offset+cnt]
        return res

    def consume_bytes(self, cnt: int) -> bytes:
        res = self.peek_bytes(cnt)
        self.offset += cnt
        return res

    def require_consumed(self) -> None:
        if self.offset < len(self.data):
            raise BencodeParseError("Input is not fully consumed")

    def add_mark(self, mark: Any) -> None:
        self.marks.append((self.offset, mark))

    def __check_len(self, required: int = 1) -> None:
        if self.offset + required > len(self.data):
            raise BencodeParseError("Unexpected EOF")
        
class BencodeParseError(BaseException):
    ...

# Задание 1: реализуйте парсер bencode.
# parse_bencoded уже написана, вам нужно реализовать только парсинг 
# - чисел
# - строк
# - байтовых строк 
# - списков
# - словарей
#
# Все функции в качестве схода принимают ParserInput, 
# у которого есть методы consume/peek_char/chars/bytes.
# consume --- откусывает кусочек входных данных и возвращает его.
# peek --- только "подглядывает" этот кусочек,
# char/chars возвращают строки, а bytes --- байты
# require_consumed и add_mark понадобятся нам позже 
#
# Обратите внимание, что во все парсеры (кроме строковых) приходит вход,
# в котором уже нет символа-индикатора типа (`i`, `l`, `d`), 
# а parse_bencoded для удобства парсинга списокв и словарей возвращает 
# None, если встречает `e` (и откусывает его).
#
# В __parse_list и __parse_dict есть параметр str_parse_fn, 
# который надо передавать в парсеры дочерних элементов (parse_bencoded).

# Задание 2
# Проверьте, что ключи в словарях лексикографически упорядочены и не повторяются
# Подсказка: сравните соседние ключи 

# Задание 3 
# нам будет очень надо посмотреть, в каком месте начинается и кончается 
# поле info в .torrent файле. Поэтому мы вставим в парсер костыль.
# Перед началом парсинга значения в каждой паре ключ-значение в словаре
# вызовите inp.add_mark(("start", key)), а после --- inp.add_mark(("end", key))

def __parse_int(inp: ParserInput, end_char: str = 'e') -> int:
    raise NotImplemented("__parse_int")

def _parse_str(inp: ParserInput) -> str:
    raise NotImplemented("_parse_str")

def _parse_byte_str(inp: ParserInput) -> bytes:
    raise NotImplemented("_parse_byte_str")

def __parse_list(inp: ParserInput, str_parse_fn: Callable[[ParserInput], __T] = _parse_byte_str) -> list[Any]:
    raise NotImplemented("__parse_list")

def __parse_dict(inp: ParserInput, str_parse_fn: Callable[[ParserInput], __T] = _parse_byte_str) -> dict[str, Any]:
    raise NotImplemented("__parse_dict")

def parse_bencoded(inp: ParserInput, str_parse_fn: Callable[[ParserInput], __T] = _parse_byte_str) -> Any:
    t = inp.peek_char()

    if t == 'i':
        inp.consume_char()
        return __parse_int(inp)
    elif t >= '0' and t <= '9':
        return str_parse_fn(inp)
    elif t == 'l':
        inp.consume_char()
        return __parse_list(inp, str_parse_fn)
    elif t == 'd':
        inp.consume_char()
        return __parse_dict(inp, str_parse_fn)
    elif t == 'e':
        inp.consume_char()
        return None
    else:
        raise BencodeParseError(f"Unknown tag `{t}`")
