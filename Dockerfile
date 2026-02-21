FROM python:3.12-slim AS base

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

ENV PYTHONUNBUFFERED=1
EXPOSE 8715

CMD ["python", "-m", "ygg_torznab.main"]
