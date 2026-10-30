from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.incident.orchestrator import PlaybookExecutor


@pytest.mark.asyncio
async def test_action_failure_does_not_persist_exception_text(monkeypatch):
    secret = "provider-token-do-not-leak"

    async def fail_action(*_args, **_kwargs):
        raise RuntimeError(secret)

    class FakeDB:
        def add(self, _record):
            pass

        async def flush(self):
            pass

    executor = PlaybookExecutor(FakeDB())
    monkeypatch.setattr(executor, "_execute_action", fail_action)
    playbook = SimpleNamespace(
        id=uuid4(), conditions={}, actions=[{"action": "notify"}],
        execution_count=0, last_executed_at=None,
    )
    incident = SimpleNamespace(id=uuid4())

    execution = await executor.execute_playbook(playbook, incident, uuid4())

    assert execution.status == "partial"
    assert execution.failed_actions[0]["error"] == "action_failed"
    assert secret not in str(execution.failed_actions)
    assert playbook.execution_count == 1


@pytest.mark.asyncio
async def test_execution_failure_uses_stable_error_code(monkeypatch):
    secret = "database-url-password-do-not-leak"

    class FakeDB:
        def add(self, _record):
            pass

        async def flush(self):
            pass

    executor = PlaybookExecutor(FakeDB())

    def fail_condition(*_args):
        raise RuntimeError(secret)

    monkeypatch.setattr(executor, "_conditions_match", fail_condition)
    playbook = SimpleNamespace(
        id=uuid4(), conditions={"severity": 1}, actions=[],
        execution_count=0, last_executed_at=None,
    )
    incident = SimpleNamespace(id=uuid4())

    execution = await executor.execute_playbook(playbook, incident, uuid4())

    assert execution.status == "failed"
    assert execution.error_message == "execution_failed"
    assert secret not in execution.error_message


@pytest.mark.asyncio
async def test_alert_action_uses_tenant_id_not_stream_id():
    class FakeDB:
        def __init__(self):
            self.added = []

        def add(self, record):
            self.added.append(record)

        async def flush(self):
            pass

    db = FakeDB()
    tenant_id = uuid4()
    stream_id = uuid4()
    executor = PlaybookExecutor(db)

    await executor._action_alert(
        {"title": "Incident alert", "message": "Review required"},
        SimpleNamespace(id=uuid4(), stream_id=stream_id),
        tenant_id,
    )

    assert len(db.added) == 1
    assert db.added[0].tenant_id == tenant_id
    assert db.added[0].tenant_id != stream_id
