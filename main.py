from __future__ import annotations

import argparse

from app.aws_iot import AwsIotClient, ConsoleIotClient
from app.config import AppConfig
from app.logging import configure_logging
from app.iot_jobs import JobsBridge
from app.remote_config import RemoteConfigPoller
from app.service import TelemetryService
from app.shadow import DeviceConfigStore, ShadowBridge, ShadowDeviceConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish simulated device telemetry to AWS IoT Core."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads locally instead of connecting to AWS IoT Core.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Publish a finite number of messages before exiting.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AppConfig.from_env()
    logger = configure_logging(config.log_level)

    if args.dry_run:
        client = ConsoleIotClient(logger=logger)
    else:
        missing = config.missing_connection_fields()
        if missing:
            logger.error("Missing AWS IoT configuration: %s", ", ".join(missing))
            logger.info("Use --dry-run to validate the template without AWS credentials.")
            return 1
        client = AwsIotClient(config=config, logger=logger)

    store = DeviceConfigStore(ShadowDeviceConfig.from_app_config(config))
    shadow_bridge: ShadowBridge | None = None
    if not args.dry_run:
        shadow_bridge = ShadowBridge(
            config=config,
            client=client,
            logger=logger,
            store=store,
        )

    remote_poller: RemoteConfigPoller | None = None
    if config.remote_config_url:
        remote_poller = RemoteConfigPoller(config=config, store=store, logger=logger)

    jobs_bridge: JobsBridge | None = None
    if not args.dry_run and config.iot_jobs_enabled:
        jobs_bridge = JobsBridge(config=config, client=client, logger=logger, store=store)

    service = TelemetryService(
        config=config,
        client=client,
        logger=logger,
        store=store,
        shadow=shadow_bridge,
        remote_poller=remote_poller,
        jobs=jobs_bridge,
    )

    try:
        service.run(max_messages=args.count)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    except Exception:
        logger.exception("Telemetry service failed unexpectedly.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
