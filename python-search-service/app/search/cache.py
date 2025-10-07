from collections import OrderedDict
from typing import Any

class LRUCache:
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._data = OrderedDict()

    def get(self, key: str) -> Any:
        v = self._data.get(key)
        if v is not None:
            # move to end (most recently used)
            self._data.move_to_end(key)
        return v

    def set(self, key: str, value: Any):
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self.max_size:
            self._data.popitem(last=False)
