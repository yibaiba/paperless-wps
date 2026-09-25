"""Run with python -m presales.configuration.search.worker (one local worker)."""

import fcntl
import os
import signal
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

from presales.storage import database_factory, now

from ..models import SearchIndexJob
from .provider import SearchModelClient
from .service import SearchIndexer
from .settings import PrivateSearchSettings

POLL_SECONDS = 2
ROOT = Path(__file__).resolve().parents[5]


def interrupt_running(factory):
    with factory() as session:
        jobs = session.scalars(select(SearchIndexJob).where(SearchIndexJob.status == "running"))
        for job in jobs:
            job.status = "interrupted"
            job.error = "智能索引工作进程已中断，请手动重试"
            job.updated_at = now()
        session.commit()


def process_one(factory, settings_store, provider_factory):
    with factory() as session:
        job = session.scalar(
            select(SearchIndexJob)
            .where(SearchIndexJob.status == "queued")
            .order_by(SearchIndexJob.updated_at)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False
        job.status = "running"
        job_id = job.id
        session.commit()
    try:
        SearchIndexer(factory, settings_store, provider_factory).process(job_id)
    except Exception as error:
        _fail_job(factory, job_id=job_id, error=error)
    return True


def _fail_job(factory, *, job_id, error):
    with factory() as session:
        job = session.get(SearchIndexJob, job_id)
        job.status = "failed"
        job.error = (
            str(error)
            if type(error) is ValueError
            else f"索引失败（{type(error).__name__}），请检查模型服务和数据库"
        )
        job.updated_at = now()
        session.commit()


def main():
    load_dotenv(ROOT / ".env")
    factory = database_factory(os.environ["DATABASE_URL"])
    settings_store = PrivateSearchSettings(ROOT / "data/private/search.json")

    def terminate(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    settings_store.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(settings_store.path.parent / "search-worker.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        interrupt_running(factory)
        try:
            with httpx.Client() as client:
                def provider():
                    return SearchModelClient(client, settings_store.read())

                while True:
                    if not process_one(factory, settings_store, provider):
                        time.sleep(POLL_SECONDS)
        finally:
            interrupt_running(factory)


if __name__ == "__main__":
    main()
