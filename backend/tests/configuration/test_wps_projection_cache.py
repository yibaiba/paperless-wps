from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest

from presales.wps.projection_cache import CompletionProjectionCache


def test_same_projection_key_is_computed_once_for_concurrent_requests():
    cache = CompletionProjectionCache()
    started, release = Event(), Event()
    calls = 0
    calls_lock = Lock()

    def compute():
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=2)
        return {"checked": {"value": []}}

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cache.get_or_compute, "same", compute) for _ in range(8)]
        assert started.wait(timeout=2)
        release.set()
        results = [future.result(timeout=2) for future in futures]

    assert calls == 1
    assert results == [{"checked": {"value": []}}] * 8
    results[0]["checked"]["value"].append("mutated")
    assert results[1]["checked"]["value"] == []


def test_failed_projection_is_not_cached():
    cache = CompletionProjectionCache()
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("projection failed")
        return {"attempt": calls}

    with pytest.raises(RuntimeError, match="projection failed"):
        cache.get_or_compute("retry", compute)

    assert cache.get_or_compute("retry", compute) == {"attempt": 2}
    assert cache.get_or_compute("retry", compute) == {"attempt": 2}
    assert calls == 2
