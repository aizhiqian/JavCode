FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JAVCODE_HOST=0.0.0.0 \
    JAVCODE_PORT=8765 \
    JAVCODE_DB=/app/data/collection.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run.py .
COPY src/ src/
COPY public/ public/

RUN mkdir -p /app/data

EXPOSE 8765

CMD ["python", "run.py"]
