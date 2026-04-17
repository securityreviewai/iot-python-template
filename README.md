# AWS IoT Python Template

This repository is a starter boilerplate for Python-based IoT applications that publish telemetry to AWS IoT Core.

## What is included

- Environment-driven configuration
- A small domain model for telemetry payloads
- A deterministic telemetry generator for demos and tests
- An AWS IoT Core MQTT client wrapper built around the AWS IoT Device SDK v2
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
│   ├── logging.py
│   ├── models.py
│   ├── service.py
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

- `--dry-run` prints messages locally instead of connecting to AWS.
- `--count` publishes a finite number of messages and exits.
- Without `--count`, the service runs continuously until interrupted.

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

- Device shadow support
- Jobs handling
- Greengrass integration
- Custom business logic and sensor drivers
