import pytest
from pydantic import ValidationError

from app.api.v1.schemas import BanCreate, BlockViewerRequest, MitigationRequest


def test_mitigation_request_caps_target_count():
    with pytest.raises(ValidationError):
        MitigationRequest(
            targets=[{"type": "ip", "value": f"192.0.2.{index}"} for index in range(101)]
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"target_type": "ip", "target_value": "x" * 256, "reason": "valid"},
        {"target_type": "ip", "target_value": "192.0.2.1", "reason": "x" * 501},
        {"target_type": "ip", "target_value": "192.0.2.1", "reason": "valid", "duration_hours": 337},
        {"target_type": "ip", "target_value": "192.0.2.1", "reason": "valid", "ban_type": "execute"},
    ],
)
def test_ban_create_rejects_out_of_range_fields(payload):
    with pytest.raises(ValidationError):
        BanCreate(**payload)


def test_block_viewer_reason_is_bounded():
    with pytest.raises(ValidationError):
        BlockViewerRequest(reason="x" * 501)
