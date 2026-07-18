# Slim Python base — no compiler toolchain needed since we use psycopg2-binary
FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first so this layer is cached unless
# requirements.txt actually changes (avoids re-installing on every code edit)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY app/ .
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
