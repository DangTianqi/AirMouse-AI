import time
import pytest
from airmouse_ai.config import Settings, model_path
from airmouse_ai.controller import Controller, State
from runtime_fakes import blank_runtime, blocked_runtime, failed_runtime


@pytest.mark.parametrize('target',[blocked_runtime,failed_runtime])
def test_process_cancellation_and_failure(qt,backend,target):
    from airmouse_ai.worker import Worker
    c=Controller(backend,Settings())
    c.set_state(State.RUNNING)
    worker=Worker(c,runtime_target=target)
    worker.start()
    time.sleep(.3)
    c.set_state(State.PAUSED)
    start=time.monotonic()
    worker.stop()
    assert worker.wait(5000)
    assert time.monotonic()-start<4
    assert backend.events==[]


def test_real_model_in_isolated_process(qt,backend):
    if not model_path().exists():
        pytest.skip('Download official model to run integration test')
    from airmouse_ai.worker import Worker
    c=Controller(backend,Settings())
    c.set_state(State.RUNNING)
    worker=Worker(c,runtime_target=blank_runtime)
    worker.start()
    deadline=time.monotonic()+15
    image=None
    try:
        while time.monotonic()<deadline and worker.isRunning():
            image,_=worker.take()
            if image is not None: break
            qt.processEvents()
            time.sleep(.05)
        assert image is not None, worker.error
        assert image.width()==480
        assert backend.events==[]
    finally:
        worker.stop()
        assert worker.wait(5000)
