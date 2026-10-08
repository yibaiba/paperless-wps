"""Bounded process-local cache for immutable workbook projection results."""

from collections import OrderedDict
from copy import deepcopy
from threading import Lock

MAX_PROJECTIONS = 16


class CompletionProjectionCache:
    def __init__(self, *, capacity=MAX_PROJECTIONS):
        self.capacity = capacity
        self._entries = OrderedDict()
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry)

    def put(self, key, value):
        with self._lock:
            self._entries[key] = deepcopy(value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
