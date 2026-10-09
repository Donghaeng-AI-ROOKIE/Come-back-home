FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN grep -vE '^(sentence-transformers|pytest)' requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
COPY backend/app ./app
COPY backend/scripts ./scripts
CMD ["python", "-m", "app.cloud_bridge.worker"]
