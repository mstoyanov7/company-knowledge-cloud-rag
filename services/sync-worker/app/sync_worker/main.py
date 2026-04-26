import argparse
import logging

from shared_schemas import get_settings

from sync_worker.observability import configure_observability
from sync_worker.runner import WorkerRunner


def run() -> None:
    parser = argparse.ArgumentParser(description="Plan configured sync jobs.")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Plan jobs once and exit.",
    )
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    configure_observability(settings, default_service_name="sync-worker")

    runner = WorkerRunner(settings)
    if args.run_once:
        runner.run_once()
        return

    runner.run_loop()


if __name__ == "__main__":
    run()
