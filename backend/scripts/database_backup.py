"""Create, verify, and safely restore PostgreSQL custom-format backups."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings

SERVICE_NAME = "anti_bots_backup"
MANIFEST_VERSION = 1
SUPPORTED_QUERY_OPTIONS = {
    "application_name",
    "channel_binding",
    "client_encoding",
    "connect_timeout",
    "fallback_application_name",
    "gssencmode",
    "hostaddr",
    "keepalives",
    "keepalives_count",
    "keepalives_idle",
    "keepalives_interval",
    "load_balance_hosts",
    "options",
    "require_auth",
    "replication",
    "sslcert",
    "sslcrl",
    "sslcrldir",
    "sslkey",
    "ssl_max_protocol_version",
    "ssl_min_protocol_version",
    "sslmode",
    "sslpassword",
    "sslrootcert",
    "target_session_attrs",
    "tcp_user_timeout",
}


class BackupError(RuntimeError):
    """An expected backup or restore operation failed safely."""


def _libpq_service_values(database_url: str) -> dict[str, str]:
    url: URL = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+asyncpg", "postgres"}:
        raise BackupError("DATABASE_URL must use PostgreSQL")
    if not url.host or not url.database:
        raise BackupError("DATABASE_URL must include a host and database name")

    unsupported = set(url.query) - SUPPORTED_QUERY_OPTIONS
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise BackupError(f"Unsupported PostgreSQL URL options: {names}")

    values = {
        "host": url.host,
        "dbname": url.database,
    }
    if url.port:
        values["port"] = str(url.port)
    if url.username:
        values["user"] = url.username
    if url.password is not None:
        values["password"] = url.password
    for key, value in url.query.items():
        if isinstance(value, (tuple, list)):
            if len(value) != 1:
                raise BackupError(f"DATABASE_URL option {key} must have one value")
            value = value[0]
        values[key] = str(value)
    return values


def _service_file_contents(values: dict[str, str]) -> str:
    lines = [f"[{SERVICE_NAME}]"]
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise BackupError(f"PostgreSQL connection option {key} contains a newline")
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"{key}='{escaped}'")
    return "\n".join(lines) + "\n"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(
    command: Sequence[str],
    *,
    env: dict[str, str],
    capture_stdout: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise BackupError(f"Required PostgreSQL tool is unavailable: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        # Tool output is intentionally omitted: connection libraries can echo
        # connection details in diagnostics. The exit code is safe to report.
        raise BackupError(f"{command[0]} failed with exit code {exc.returncode}") from exc


def _connection_environment(database_url: str, temp_dir: Path) -> dict[str, str]:
    if os.name == "posix":
        temp_dir.chmod(0o700)
    service_file = temp_dir / "pg_service.conf"
    service_file.write_text(
        _service_file_contents(_libpq_service_values(database_url)),
        encoding="utf-8",
    )
    if os.name == "posix":
        service_file.chmod(0o600)
    env = os.environ.copy()
    env["PGSERVICEFILE"] = str(service_file)
    env["PGSERVICE"] = SERVICE_NAME
    return env


def _manifest_path(dump_path: Path) -> Path:
    return dump_path.with_suffix(dump_path.suffix + ".json")


def verify_backup(dump_path: Path) -> dict[str, object]:
    dump_path = dump_path.resolve()
    manifest_path = _manifest_path(dump_path)
    if not dump_path.is_file() or not manifest_path.is_file():
        raise BackupError("Backup dump and its JSON manifest must both exist")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError("Backup manifest is unreadable") from exc
    if manifest.get("version") != MANIFEST_VERSION:
        raise BackupError("Unsupported backup manifest version")
    if manifest.get("file") != dump_path.name:
        raise BackupError("Backup manifest filename does not match the dump")
    if manifest.get("size_bytes") != dump_path.stat().st_size:
        raise BackupError("Backup size does not match its manifest")
    if manifest.get("sha256") != _hash_file(dump_path):
        raise BackupError("Backup checksum does not match its manifest")

    # Ensure the custom-format archive is structurally readable before restore.
    _run(
        ["pg_restore", "--list", str(dump_path)],
        env=os.environ.copy(),
        capture_stdout=False,
    )
    return manifest


def create_backup(output_dir: Path, database_url: str) -> Path:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dump_path = output_dir / f"anti-bots-postgres-{timestamp}.dump"
    if dump_path.exists() or _manifest_path(dump_path).exists():
        raise BackupError("A backup with this timestamp already exists")

    fd, partial_name = tempfile.mkstemp(prefix=".anti-bots-postgres-", suffix=".partial", dir=output_dir)
    os.close(fd)
    partial_path = Path(partial_name)
    published_dump = False
    temp_manifest_path: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="anti-bots-pg-") as temp:
            env = _connection_environment(database_url, Path(temp))
            _run(
                [
                    "pg_dump",
                    "--no-password",
                    "--dbname",
                    f"service={SERVICE_NAME}",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(partial_path),
                ],
                env=env,
            )
            _run(
                ["pg_restore", "--list", str(partial_path)],
                env=env,
                capture_stdout=False,
            )

        checksum = _hash_file(partial_path)
        size_bytes = partial_path.stat().st_size
        os.replace(partial_path, dump_path)
        published_dump = True
        manifest = {
            "version": MANIFEST_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file": dump_path.name,
            "format": "postgresql-custom",
            "size_bytes": size_bytes,
            "sha256": checksum,
        }
        manifest_path = _manifest_path(dump_path)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_dir,
            prefix=".anti-bots-manifest-",
            suffix=".partial",
            delete=False,
        ) as manifest_file:
            json.dump(manifest, manifest_file, indent=2)
            manifest_file.write("\n")
            temp_manifest_path = Path(manifest_file.name)
        os.replace(temp_manifest_path, manifest_path)
        return dump_path
    except Exception:
        partial_path.unlink(missing_ok=True)
        if temp_manifest_path:
            temp_manifest_path.unlink(missing_ok=True)
        if published_dump and not _manifest_path(dump_path).exists():
            dump_path.unlink(missing_ok=True)
        raise


def _assert_empty_target(database_url: str) -> None:
    query = """
    SELECT CASE WHEN
      EXISTS (
        SELECT 1 FROM pg_namespace
        WHERE nspname NOT IN ('pg_catalog', 'information_schema')
          AND nspname NOT LIKE 'pg_toast%'
          AND nspname NOT LIKE 'pg_temp_%'
      )
      OR EXISTS (
        SELECT 1
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema')
          AND namespace.nspname NOT LIKE 'pg_toast%'
          AND namespace.nspname NOT LIKE 'pg_temp_%'
      )
      OR EXISTS (
        SELECT 1 FROM pg_proc AS procedure
        JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema')
          AND namespace.nspname NOT LIKE 'pg_%'
      )
      OR EXISTS (
        SELECT 1 FROM pg_extension AS extension
        JOIN pg_namespace AS namespace ON namespace.oid = extension.extnamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema')
      )
      OR EXISTS (
        SELECT 1 FROM pg_type AS type
        JOIN pg_namespace AS namespace ON namespace.oid = type.typnamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema')
          AND namespace.nspname NOT LIKE 'pg_toast%'
          AND namespace.nspname NOT LIKE 'pg_temp_%'
      )
      OR EXISTS (
        SELECT 1 FROM pg_collation AS collation
        JOIN pg_namespace AS namespace ON namespace.oid = collation.collnamespace
        WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema')
          AND namespace.nspname NOT LIKE 'pg_%'
      )
    THEN 'not_empty' ELSE 'empty' END;
    """
    with tempfile.TemporaryDirectory(prefix="anti-bots-pg-restore-") as temp:
        env = _connection_environment(database_url, Path(temp))
        result = _run(
            [
                "psql",
                "--no-password",
                "--dbname",
                f"service={SERVICE_NAME}",
                "--no-psqlrc",
                "--tuples-only",
                "--no-align",
                "--command",
                query,
            ],
            env=env,
        )
    if result.stdout.strip() != "empty":
        raise BackupError("Restore target is not empty; refusing to modify it")


def restore_backup(dump_path: Path, database_url: str) -> None:
    verify_backup(dump_path)
    _assert_empty_target(database_url)
    with tempfile.TemporaryDirectory(prefix="anti-bots-pg-restore-") as temp:
        env = _connection_environment(database_url, Path(temp))
        _run(
            [
                "pg_restore",
                "--no-password",
                "--dbname",
                f"service={SERVICE_NAME}",
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                str(dump_path.resolve()),
            ],
            env=env,
        )


def _database_url_from_settings() -> str:
    value = get_settings().database_url
    if not value:
        raise BackupError("DATABASE_URL is required")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup", help="create and verify a backup")
    backup_parser.add_argument("--output-dir", type=Path, default=Path("backups/postgres"))

    verify_parser = commands.add_parser("verify", help="verify a dump and its manifest")
    verify_parser.add_argument("dump", type=Path)

    restore_parser = commands.add_parser("restore", help="restore to an empty database")
    restore_parser.add_argument("dump", type=Path)
    restore_parser.add_argument(
        "--confirm-empty-target",
        action="store_true",
        help="confirm that DATABASE_URL points to a new, empty restore database",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            dump_path = create_backup(args.output_dir, _database_url_from_settings())
            manifest = verify_backup(dump_path)
            print(f"Backup created and verified: {dump_path}")
            print(f"SHA-256: {manifest['sha256']}")
        elif args.command == "verify":
            manifest = verify_backup(args.dump)
            print(f"Backup verified: {args.dump}")
            print(f"SHA-256: {manifest['sha256']}")
        else:
            if not args.confirm_empty_target:
                raise BackupError("Pass --confirm-empty-target after selecting a new empty database")
            restore_backup(args.dump, _database_url_from_settings())
            print(f"Backup restored: {args.dump}")
    except BackupError as exc:
        print(f"Database backup operation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
