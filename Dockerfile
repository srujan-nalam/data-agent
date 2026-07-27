FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY agent ./agent
COPY data ./data
COPY service ./service
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .
# bake the curated datasets into the image
RUN python scripts/ingest.py --synthetic
EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
