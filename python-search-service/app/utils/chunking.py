from typing import Iterable, List, TypeVar

T = TypeVar('T')

def chunked(iterable: Iterable[T], size: int) -> List[List[T]]:
    out = []
    batch = []
    for i, v in enumerate(iterable, start=1):
        batch.append(v)
        if i % size == 0:
            out.append(batch)
            batch = []
    if batch:
        out.append(batch)
    return out
