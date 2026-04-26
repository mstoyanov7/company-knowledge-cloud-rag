from __future__ import annotations

import argparse
import logging

from shared_schemas import get_settings

from sync_worker.ops import OpsJobRunner


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the durable operations job worker.")
    parser.add_argument("--run-once", action="store_true", help="Process at most one due job and exit.")
    parser.add_argument(
        "--no-schedule",
        action="store_true",
        help="Do not enqueue periodic renewal/reconciliation jobs before claiming work.",
    )
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    runner = OpsJobRunner(settings)
    if args.run_once:
        runner.process_once(enqueue_periodic=not args.no_schedule)
        return
    runner.run_loop()


if __name__ == "__main__":
    run()
