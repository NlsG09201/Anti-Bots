from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, VARCHAR

# JSONB on PostgreSQL, JSON on SQLite (tests)
JsonType = JSON().with_variant(JSONB(), "postgresql")

# String arrays: native ARRAY on PostgreSQL, JSON list on SQLite
StringArrayType = JSON().with_variant(ARRAY(VARCHAR), "postgresql")
