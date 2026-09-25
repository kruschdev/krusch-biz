#!/usr/bin/env python3
"""
scripts/build_demo_db.py
========================
Builds and packages a frozen SQLite database fixture (data/demo.db) containing
sample active commercial agreements, confirmed relations, extracted structured slots,
and commercial clause embeddings.

Enables the KruschBiz REST API (/docs) and Review UI to launch out-of-the-box
with zero setup or external Ollama/PostgreSQL dependencies.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["USE_MOCK_EMBEDDINGS"] = "1"
os.environ["HEADLESS_MODE"] = "1"

import src.backend.db as db_mod
from src.backend.db import AgreementRelation, Base
from src.backend.ingest import ingest_mock_data


def main():
    demo_db_path = os.path.join(PROJECT_ROOT, "data", "demo.db")
    if os.path.exists(demo_db_path):
        os.remove(demo_db_path)

    print(f"Creating frozen demo database at: {demo_db_path}")
    demo_engine = create_engine(f"sqlite:///{demo_db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=demo_engine)
    DemoSession = sessionmaker(bind=demo_engine)
    db = DemoSession()

    try:
        report = ingest_mock_data(db, tenant_id="org_default")
        print(f"Ingested mock contracts: {report['inserted']} inserted, {report['skipped']} skipped.")

        # Ensure proposed relations are promoted to confirmed so graph walking works immediately
        rels = db.query(AgreementRelation).filter(AgreementRelation.status == "proposed").all()
        for r in rels:
            r.status = "confirmed"
            r.reviewer_id = "demo_system"
            r.reviewed_at = db_mod.func.now()
        db.commit()
        print(f"Confirmed {len(rels)} demo relation edges in precedence graph.")

        print(f"Successfully generated frozen fixture data/demo.db ({os.path.getsize(demo_db_path):,} bytes).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
