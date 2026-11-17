FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CODY_DATA=/data HOME=/data/reach
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs npm ca-certificates chromium cmake g++ make \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 kisocial && useradd --uid 10001 --gid 10001 --no-create-home kisocial
COPY collector/ collector/
COPY tools/ tools/
USER 10001:10001
EXPOSE 9131
CMD ["python", "collector/service.py"]
