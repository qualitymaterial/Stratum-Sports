FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x /app/start.sh /app/worker-start.sh \
    && groupadd --system app \
    && useradd --system --gid app --create-home app \
    && chown -R app:app /app

USER app

EXPOSE 8000
CMD ["/app/start.sh"]
