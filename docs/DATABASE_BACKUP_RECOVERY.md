# PostgreSQL backup and recovery

The backup utility supports PostgreSQL custom-format archives. It verifies the archive can be listed and writes a JSON manifest containing its size and SHA-256 checksum. The utility does not schedule backups, encrypt them, or prune old files; those controls belong in the operator's backup destination and scheduler.

## Create and verify a backup

Install PostgreSQL client tools (`pg_dump`, `pg_restore`, and `psql`) on the backup runner. Provide `DATABASE_URL` through the runner's protected environment, then from `backend/` run:

```bash
python -m scripts.database_backup backup --output-dir ../backups/postgres
python -m scripts.database_backup verify ../backups/postgres/<backup-file>.dump
```

Backups contain the database's user and security data. Store them in access-controlled, encrypted storage outside the database host, restrict access to the manifest and dump together, and test the scheduler's success/failure alerting. Define retention to match the service's legal and operational requirements; the utility intentionally does not delete older backups.

## Restore to an isolated database

1. Create a new empty PostgreSQL database or isolated Neon branch. Do not target the live database.
2. Configure `DATABASE_URL` on the restore runner to point to that empty target, and verify the selected archive.
3. Run the restore with the explicit confirmation flag:

   ```bash
   python -m scripts.database_backup restore ../backups/postgres/<backup-file>.dump --confirm-empty-target
   ```

The restore verifies the manifest and PostgreSQL archive, checks that the target has no application schema objects, and runs `pg_restore` with `--single-transaction` and `--exit-on-error`. It refuses a nonempty target. Afterward, run application smoke checks and compare expected table/row counts before directing any service to the restored database.

Perform periodic isolated restore drills. A successful dump and checksum do not prove that credentials, extensions, permissions, or application compatibility are correct for recovery.
