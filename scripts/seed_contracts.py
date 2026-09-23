#!/usr/bin/env python3
"""
scripts/seed_contracts.py
=========================
Command line utility to seed demo corporate contracts, MSAs, and SLAs into KruschBiz.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backend.db import SessionLocal, init_db
from src.backend.ingest import ingest_mock_data


def main():
    print("Initializing KruschBiz database...")
    init_db()
    db = SessionLocal()
    try:
        report = ingest_mock_data(db)
        print(f"Seeding completed successfully: {report['inserted']} inserted, {report['skipped']} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
