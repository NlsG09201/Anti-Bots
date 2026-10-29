"""Local entry point for the BI warehouse ETL.

Run from the backend directory with:
    python ../business-intelligence/scripts/refresh_warehouse.py

Render Cron uses backend/scripts/refresh_warehouse.py, backed by the same
implementation in app.services.analytics.warehouse_refresh.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.analytics.warehouse_refresh import run


if __name__ == "__main__":
    run()
