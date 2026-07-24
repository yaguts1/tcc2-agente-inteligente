import os
import time

from fastapi.testclient import TestClient

from interface import web


def test_lifespan_starts_and_stops_reconciler():
    # make reconciler interval short so test runs fast
    os.environ["DEVICE_RECONCILE_INTERVAL"] = "1"
    app = web.app

    # Start the TestClient context which triggers lifespan startup
    with TestClient(app) as client:
        # allow a tiny moment for the background task to be created
        time.sleep(0.05)
        task = getattr(app.state, "_reconcile_task", None)
        assert task is not None, "Reconciler task was not created on startup"
        # task should be running (not done) while the app context is active
        assert not task.done(), "Reconciler task is unexpectedly done during runtime"
        # if Task naming APIs are available, ensure the name matches
        get_name = getattr(task, "get_name", None)
        if callable(get_name):
            assert get_name() == "device_reconciler"

    # after exiting the context the lifespan shutdown should have awaited task cancellation
    task_after = getattr(app.state, "_reconcile_task", None)
    assert task_after is not None
    assert task_after.done(), "Reconciler task should be finished after shutdown"
