import logging
import time
from datetime import datetime, timezone

from .db import IngestJob, SessionLocal
from .ingest import ingest_business_document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (kruschbiz.worker) %(message)s"
)
logger = logging.getLogger("kruschbiz.worker")


def process_next_job():
    """Poll and process next pending IngestJob using atomic database transaction."""
    db = SessionLocal()
    try:
        is_postgres = "postgresql" in str(db.bind.url)
        if is_postgres:
            job = db.query(IngestJob).filter(
                IngestJob.status == "pending"
            ).with_for_update(skip_locked=True).first()
        else:
            job = db.query(IngestJob).filter(
                IngestJob.status == "pending"
            ).first()

        if not job:
            return False

        logger.info(f"Picked up IngestJob {job.id} for file: {job.file_path}")
        job.status = "running"
        job.stage = "parsing"
        job.heartbeat_at = datetime.now(timezone.utc)
        db.commit()

        try:
            report = ingest_business_document(
                file_path=job.file_path,
                db=db
            )
            job.status = "completed"
            job.stage = "completed"
            job.inserted_records = report.get("records_inserted", 0)
            job.total_pages = report.get("pages_in", 0)
            job.chunks_total = report.get("chunks_out", 0)
            job.error_message = None
            db.commit()
            logger.info(f"IngestJob {job.id} completed successfully ({job.inserted_records} records inserted).")
        except Exception as e:
            logger.error(f"IngestJob {job.id} failed: {e}")
            job.status = "failed"
            job.stage = "failed"
            job.error_message = str(e)
            job.retry_count = (job.retry_count or 0) + 1
            db.commit()

        return True
    finally:
        db.close()


def run_worker_loop():
    """Continuous polling loop for KruschBiz background worker."""
    logger.info("Starting KruschBiz Persistent Ingestion Worker daemon...")
    while True:
        try:
            processed = process_next_job()
            if not processed:
                time.sleep(2.0)
        except KeyboardInterrupt:
            logger.info("Worker stopped by operator.")
            break
        except Exception as e:
            logger.error(f"Worker encountered unexpected error: {e}")
            time.sleep(5.0)


if __name__ == "__main__":
    run_worker_loop()
