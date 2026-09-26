from threading import Barrier, Lock, current_thread
from types import SimpleNamespace

from grounded.transform import _provider_map


def test_cloud_work_is_bounded_parallel_and_results_keep_source_order():
    barrier = Barrier(4, timeout=5)
    lock = Lock()
    active = peak = 0

    def operation(value):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()
        with lock:
            active -= 1
        return value * 2

    assert _provider_map(SimpleNamespace(name="azure-test"), operation, range(4)) == [0, 2, 4, 6]
    assert peak == 4


def test_local_provider_stays_on_calling_thread():
    caller = current_thread()
    assert _provider_map(SimpleNamespace(name="local-test"), lambda _: current_thread(), range(3)) == [caller] * 3


def test_provider_failure_is_not_silently_treated_as_verified_output():
    def fail(_):
        raise RuntimeError("provider unavailable")

    [result] = _provider_map(SimpleNamespace(name="azure-test"), fail, [1])
    assert isinstance(result, RuntimeError)
    assert str(result) == "provider unavailable"
