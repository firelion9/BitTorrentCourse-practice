from typing import Any, Callable, Optional, Type, TypeVar, overload


class ParseError(BaseException): ...


def chunked(data: bytes, chunk_len: int) -> list[bytes]:
    if len(data) % chunk_len != 0:
        raise ParseError(f"Chunked data len is not multiple of chunk len {chunk_len}")

    return [data[idx : (idx + chunk_len)] for idx in range(0, len(data), chunk_len)]


__T = TypeVar("__T")
__R = TypeVar("__R")


def get_field(d: dict[str, Any], field: str, t: Type[__T]) -> __T:
    if not field in d:
        raise ParseError(f"No `{field}` field")
    res = d[field]
    if not isinstance(res, getattr(t, "__origin__", t)):
        raise ParseError(f"Illegal `{field}` value `{res}`")
    return res


def get_field_or_default(
    d: dict[str, Any], field: str, t: Type[__T], default: __T = None
) -> __T:
    if not field in d:
        return default
    return get_field(d, field, t)


def map_optional(fn: Callable[[__T], __R], x: Optional[__T]) -> Optional[__R]:
    return None if x is None else fn(x)


class Bitset:
    @overload
    def __init__(self, size: int) -> None:
        ...

    @overload
    def __init__(self, data: bytes) -> None:
        ...

    @overload
    def __init__(self, data: 'Bitset') -> None:
        ...

    def __init__(self, data_or_size: bytes|int) -> None:
        if isinstance(data_or_size, int):
            self.size = data_or_size
            self.data = bytearray((data_or_size + 7) // 8)
        elif isinstance(data_or_size, Bitset):
            self.size = data_or_size.size
            self.data = bytearray(data_or_size.data)
        else:
            self.size = len(data_or_size) * 8
            self.data = bytearray(data_or_size)


    def __len__(self) -> int:
        return self.size

    def __getitem__(self, idx: int) -> bool:
        byte_idx = idx >> 3
        bit_idx = 7 - (idx & 0x7)
        return (self.data[byte_idx] & (1 << (bit_idx))) != 0

    def __setitem__(self, idx: int, val: bool) -> None:
        byte_idx = idx >> 3
        bit_idx = 7 - (idx & 0x7)
        self.data[byte_idx] = ((self.data[byte_idx] & ~(1 << bit_idx)) | (
            (1 if val else 0) << bit_idx
        )) & 0xff
