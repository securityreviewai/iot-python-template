FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md main.py ./
COPY app ./app

RUN python -m pip install --upgrade pip \
    && python -m pip install .[aws]

CMD ["python", "main.py", "--dry-run"]
