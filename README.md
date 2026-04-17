# AWS IoT Python Template

This repository is a starter boilerplate for Python-based IoT applications that publish telemetry to AWS IoT Core and can execute AWS IoT Jobs on the device (fleet command / OTA-style workflows).

## What is included

- Environment-driven configuration
- A small domain model for telemetry payloads
- A deterministic telemetry generator for demos and tests
- An AWS IoT Core MQTT client wrapper built around the AWS IoT Device SDK v2
- AWS IoT Jobs device workflow (`notify-next`, `start-next`, `UpdateJobExecution`) with allowlisted job types and optional audit publish
- A service loop that can run in real mode or `--dry-run`
- Unit tests for configuration and payload generation
- Container packaging via Docker

## Project layout

```text
.
├── app/
│   ├── __init__.py
│   ├── aws_iot.py
│   ├── config.py
│   ├── iot_jobs.py
│   ├── logging.py
│   ├── models.py
│   ├── remote_config.py
│   ├── service.py
│   ├── shadow.py
│   └── telemetry.py
├── tests/
├── .env.example
├── Dockerfile
├── main.py
└── pyproject.toml
```

## Quick start

1. Create a virtual environment.
2. Install the package.
3. Copy `.env.example` to `.env` and fill in your AWS IoT Core values.
4. Run the simulator.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .[aws]
cp .env.example .env
python main.py --dry-run --count 3
```

For a real AWS IoT Core connection:

```bash
python main.py
```

## Required AWS IoT values

- `IOT_ENDPOINT`
- `IOT_CLIENT_ID`
- `IOT_TOPIC`
- `IOT_CERT_PATH`
- `IOT_KEY_PATH`

`IOT_CA_PATH` is optional if your runtime environment already provides the root CA, but keeping it explicit is usually better for device deployments.

## Template behavior

- `--dry-run` prints messages locally instead of connecting to AWS. IoT Jobs are not started in dry-run (no MQTT subscriptions).
- `--count` publishes a finite number of messages and exits.
- Without `--count`, the service runs continuously until interrupted.
- In live mode, when `IOT_JOBS_ENABLED=true`, the device subscribes to Jobs topics for `IOT_THING_NAME`, calls `StartNextPendingJobExecution` over MQTT, runs allowlisted operations from the job document, updates status to `IN_PROGRESS` then `SUCCEEDED` or `FAILED`, and optionally publishes a small audit record to `IOT_JOBS_AUDIT_TOPIC` when set.

### Job documents (examples)

Operations are allowlisted; arbitrary shell or code execution from the job JSON is not supported.

- **noop** — `{"operation": "noop"}` (or omit `operation`)
- **config** — merge a shadow-shaped patch: `{"operation": "config", "patch": {"sampling_interval_seconds": 10}}`
- **diagnostic** — `{"operation": "diagnostic", "name": "ping"}` or `"metrics_snapshot"`
- **firmware** — simulated staging: `{"operation": "firmware", "target_version": "1.2.0"}` (does not modify the running binary)

## Docker

Build:

```bash
docker build -t aws-iot-python-template .
```

Run:

```bash
docker run --rm --env-file .env aws-iot-python-template python main.py --dry-run --count 5
```

## Notes

This is intentionally a boilerplate starter. It is designed to be extended with:

- Deeper OTA / artifact verification and real firmware apply paths
- Greengrass integration
- Custom business logic and sensor drivers
