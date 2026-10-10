FROM python:3.11.17-alpine3.23@sha256:924d53e01cee5204d35fbcfb71b6c1568c857d7c31141f960ff6a37e111ecc7f

# Pin the multi-platform index, retaining Python 3.11 and the Alpine runtime.
ARG BUILD_VERSION="3.1.1"
ARG BUILD_ARCH="aarch64|amd64"

LABEL io.hass.name="D2HA Bridge" \
      io.hass.description="Independent Dovit TCP/XML to MQTT bridge for Home Assistant" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"

LABEL org.opencontainers.image.source="https://github.com/SPRuben/d2ha-bridge" \
      org.opencontainers.image.version="${BUILD_VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY dovit_bridge /app/dovit_bridge
COPY dovit_devices.json /app/dovit_devices.json
CMD ["python", "-m", "dovit_bridge.main"]
