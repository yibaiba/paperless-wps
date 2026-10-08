"""Bounded process-local cache for immutable workbook projection results."""

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Callable

MAX_PROJECTIONS = 16


@dataclass
class ProjectionFlight:
    ready: Event = field(default_factory=Event)
    value: object | None = None
    error: BaseException | None = None


class CompletionProjectionCache:
    def __init__(self, *, capacity=MAX_PROJECTIONS):
        self.capacity = capacity
        self._entries = OrderedDict()
        self._flights = {}
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
            self._store(key, value)

    def get_or_compute(self, key, compute: Callable[[], object]):
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
                return deepcopy(entry)
            flight = self._flights.get(key)
            owner = flight is None
            if owner:
                flight = ProjectionFlight()
                self._flights[key] = flight
        if not owner:
            return self._wait(flight)
        return self._compute(key, flight, compute)

    def _compute(self, key, flight, compute):
        try:
            value = compute()
            with self._lock:
                self._store(key, value)
                flight.value = deepcopy(value)
            return deepcopy(value)
        except BaseException as error:
            flight.error = error
            raise
        finally:
            with self._lock:
                self._flights.pop(key, None)
                flight.ready.set()

    @staticmethod
    def _wait(flight):
        flight.ready.wait()
        if flight.error is not None:
            raise flight.error
        return deepcopy(flight.value)

    def _store(self, key, value):
        self._entries[key] = deepcopy(value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)
