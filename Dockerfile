FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/app

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system --gid 10001 incidental \
    && adduser --system --uid 10001 --ingroup incidental incidental \
    && mkdir /data \
    && chown incidental:incidental /data
COPY app ./app

USER 10001:10001
EXPOSE 8000
CMD ["python", "app/main.py"]
