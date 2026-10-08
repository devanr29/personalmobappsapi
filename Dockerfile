FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Jakarta

# slim ships without zoneinfo, so TZ would silently fall back to UTC.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# 1 worker on purpose: APScheduler runs in-process (app.py), so extra
# workers would each fire reminders/alerts/quotes. --timeout 300 keeps the
# wallet-sync rationale from railway.toml.
CMD ["gunicorn", "app:app", "--workers", "1", "--threads", "4", "--timeout", "300", "--bind", "0.0.0.0:8000"]
