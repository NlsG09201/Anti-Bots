import json
import subprocess
from pathlib import Path

import pytest

import scripts.database_backup as backup


DATABASE_URL = (
    "postgresql+asyncpg://backup_user:p%40ss%3Aword@db.example:5432/antibots"
    "?sslmode=require&application_name=backup"
)


def test_database_url_is_written_to_private_service_file_not_command_args(tmp_path):
    values = backup._libpq_service_values(DATABASE_URL)
    service_contents = backup._service_file_contents(values)

    assert "password='p@ss:word'" in service_contents
    assert "sslmode='require'" in service_contents
    assert DATABASE_URL not in service_contents
    assert "user='backup_user'" in service_contents


def test_unsupported_database_url_options_are_rejected():
    with pytest.raises(backup.BackupError, match="Unsupported PostgreSQL URL options"):
        backup._libpq_service_values(f"{DATABASE_URL}&unknown_option=value")


def test_backup_writes_manifest_and_verifies_archive(tmp_path, monkeypatch):
    commands = []

    def fake_run(command, *, env, capture_stdout=True):
        commands.append(command)
        if command[0] == "pg_dump":
            Path(command[command.index("--file") + 1]).write_bytes(b"valid archive")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(backup, "_run", fake_run)

    dump_path = backup.create_backup(tmp_path, DATABASE_URL)
    manifest = backup.verify_backup(dump_path)

    assert dump_path.exists()
    assert manifest["file"] == dump_path.name
    assert manifest["sha256"] == backup._hash_file(dump_path)
    assert len(commands) == 3  # dump, archive validation, and explicit verify
    assert DATABASE_URL not in " ".join(commands[0])
    assert "service=anti_bots_backup" in commands[0]
    assert json.loads(backup._manifest_path(dump_path).read_text())["version"] == 1


def test_backup_verification_rejects_tampering(tmp_path, monkeypatch):
    dump_path = tmp_path / "backup.dump"
    dump_path.write_bytes(b"valid archive")
    backup._manifest_path(dump_path).write_text(
        json.dumps(
            {
                "version": 1,
                "file": dump_path.name,
                "size_bytes": dump_path.stat().st_size,
                "sha256": backup._hash_file(dump_path),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        backup,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0),
    )
    dump_path.write_bytes(b"tampered file")

    with pytest.raises(backup.BackupError, match="size does not match"):
        backup.verify_backup(dump_path)


def test_restore_refuses_nonempty_target(tmp_path, monkeypatch):
    monkeypatch.setattr(
        backup,
        "_run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 0, stdout="not_empty\n", stderr=""
        ),
    )

    with pytest.raises(backup.BackupError, match="not empty"):
        backup._assert_empty_target(DATABASE_URL)


def test_restore_cli_requires_explicit_empty_target_confirmation(capsys, monkeypatch):
    monkeypatch.setattr(
        backup,
        "_database_url_from_settings",
        lambda: pytest.fail("must refuse before reading database settings"),
    )

    assert backup.main(["restore", "backup.dump"]) == 1
    assert "--confirm-empty-target" in capsys.readouterr().err
