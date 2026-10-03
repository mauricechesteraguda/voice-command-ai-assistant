# implementation-10032026-Maurice
FROM python:3.11.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
       ffmpeg pulseaudio-utils libpulse0 libpulse-mainloop-glib0 \
       ca-certificates curl procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 assistant
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && command -v piper \
    && command -v paplay \
    && command -v ffmpeg \
    && command -v curl
COPY . .
RUN chown -R assistant:assistant /app
USER assistant
ENTRYPOINT ["python", "assistant.py"]
