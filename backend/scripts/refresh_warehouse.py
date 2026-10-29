"""Render Cron entry point for the BI warehouse ETL."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.analytics.warehouse_refresh import run


if __name__ == "__main__":
    run()
