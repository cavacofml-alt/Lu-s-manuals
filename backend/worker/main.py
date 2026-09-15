"""Ingestion worker.

A separate OS process running the same codebase (docs/ARCHITECTURE.md §2.1). The
Postgres SKIP LOCKED queue lands in STEP 3; this is the process boundary only.
"""

from __future__ import annotations

import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")


def main() -> None:
    logger.info("worker started; queue consumer lands in STEP 3")
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
