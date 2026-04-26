from __future__ import annotations

import argparse
import logging

from shared_schemas import get_settings

from sync_worker.ops import GraphSubscriptionMaintenanceService


def run() -> None:
    parser = argparse.ArgumentParser(description="Ensure or renew Microsoft Graph subscriptions.")
    parser.add_argument("--ensure-sharepoint", action="store_true", help="Create the configured SharePoint subscription.")
    args = parser.parse_args()

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    service = GraphSubscriptionMaintenanceService(settings)
    if args.ensure_sharepoint:
        service.ensure_sharepoint_subscription()
    renewed = service.renew_due_subscriptions()
    logging.getLogger("sync_worker.jobs.subscription_renewal").info(
        "event=graph_subscription_renewal_report renewed=%s",
        renewed,
    )


if __name__ == "__main__":
    run()
