FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Default command (override in compose)
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
