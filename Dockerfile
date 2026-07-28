FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JAVCODE_HOST=0.0.0.0 \
    JAVCODE_PORT=8765 \
    JAVCODE_DB=/app/data/collection.db

COPY requirements.txt requirements-db.txt ./
# Include optional DB drivers so mysql:// and postgresql:// work in the image.
RUN pip install --no-cache-dir -r requirements.txt -r requirements-db.txt

COPY run.py .
COPY src/ src/
COPY public/ public/

RUN mkdir -p /app/data

EXPOSE 8765

CMD ["python", "run.py"]
