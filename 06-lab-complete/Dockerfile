# STAGE 1: BIG FAT BUILDER
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y gcc \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# STAGE 2: LIGHTWEIGHT RUNTIME
FROM python:3.11-slim AS runtime

# Create a non-root user with a home directory
RUN groupadd -r appuser && useradd -r -m -g appuser appuser

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app app/
COPY utils utils/

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

# Environment variables
ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Use environment variable for port
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
