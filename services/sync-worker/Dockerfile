FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY pyproject.toml README.md ./
COPY libs ./libs
COPY services ./services

RUN pip install --no-cache-dir .

CMD ["sync-worker"]
