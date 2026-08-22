# Opportunity Radar — dashboard + pipeline in one image.
# Needs both Python (FastAPI pipeline/dashboard) and Node (Bright Data CLI).

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @brightdata/cli

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x scripts/start.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["./scripts/start.sh"]
