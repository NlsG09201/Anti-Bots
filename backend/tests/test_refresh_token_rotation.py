from sqlalchemy.dialects import postgresql

from app.api.v1.auth import _active_refresh_token_query


def test_refresh_rotation_locks_active_token_row_in_postgres():
    statement = _active_refresh_token_query("test-jti")
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "refresh_tokens.is_revoked = false" in sql
    assert "FOR UPDATE" in sql
