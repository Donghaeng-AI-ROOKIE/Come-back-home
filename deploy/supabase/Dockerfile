FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt ./
RUN grep -vE '^(sentence-transformers|pytest)' requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
COPY backend/app ./app
COPY backend/scripts ./scripts
# The build context may be extracted with a restrictive umask. The worker runs
# as the data-volume owner rather than root; application code must stay readable.
RUN chmod -R a+rX /app/app /app/scripts
CMD ["python", "-m", "app.cloud_bridge.worker"]
