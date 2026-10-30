import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_pool_settings_have_bounded_defaults():
    settings = Settings(_env_file=None)

    assert settings.database_pool_size == 10
    assert settings.database_max_overflow == 5
    assert settings.database_pool_timeout_seconds == 30
    assert settings.database_pool_recycle_seconds == 1800


@pytest.mark.parametrize(
    "setting,value",
    [
        ("database_pool_size", 0),
        ("database_max_overflow", -1),
        ("database_pool_timeout_seconds", 0),
        ("database_pool_recycle_seconds", 59),
    ],
)
def test_database_pool_settings_reject_unsafe_bounds(setting, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})
