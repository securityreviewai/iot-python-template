from __future__ import annotations

import logging
import time

from app.aws_iot import IoTClient
from app.config import AppConfig
from app.telemetry import TelemetryGenerator


class TelemetryService:
    def __init__(
        self,
        config: AppConfig,
        client: IoTClient,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.client = client
        self.logger = logger
        self.generator = TelemetryGenerator(thing_name=config.iot_thing_name)

    def run(self, max_messages: int | None = None) -> None:
        published = 0
        self.client.connect()

        try:
            while True:
                reading = self.generator.generate()
                self.client.publish(self.config.iot_topic, reading.to_payload())
                published += 1

                if max_messages is not None and published >= max_messages:
                    self.logger.info("Published %s message(s); stopping.", published)
                    return

                time.sleep(self.config.publish_interval_seconds)
        finally:
            self.client.disconnect()
