"""RQ worker entrypoint.

Run: python -m worker.main
Picks jobs from queue `transcribe` and runs transcribe_job.
"""
from __future__ import annotations

import logging
import sys

import redis
from rq import Queue, Worker

from shared.config import load_config
from shared.db import TRANSCRIBE_QUEUE_NAME

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","service":"worker","msg":%(message)r}',
)
log = logging.getLogger(__name__)


def main() -> int:
    cfg = load_config()
    conn = redis.from_url(cfg.redis_url)
    queue = Queue(TRANSCRIBE_QUEUE_NAME, connection=conn)
    worker = Worker([queue], connection=conn)
    log.info("worker starting, listening on queue %r", TRANSCRIBE_QUEUE_NAME)
    worker.work(with_scheduler=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
