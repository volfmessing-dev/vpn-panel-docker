FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client wireguard-tools \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
RUN pip install --no-cache-dir --no-deps .
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
