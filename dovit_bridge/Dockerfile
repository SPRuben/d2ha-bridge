FROM python:3.11-alpine

# Keep the existing Python/Alpine runtime. This FROM is authoritative even when
# an older Supervisor supplies the legacy BUILD_FROM argument from build.yaml.
ARG BUILD_VERSION="2.2"
ARG BUILD_ARCH="aarch64|amd64"

# The legacy addon type is also recognized by current Supervisor app releases.
LABEL io.hass.name="Dovit Bridge" \
      io.hass.description="Dovit TCP to MQTT bridge" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.type="addon" \
      io.hass.arch="${BUILD_ARCH}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt
COPY dovit_bridge /app/dovit_bridge
COPY dovit_devices.json /app/dovit_devices.json
CMD ["python", "-m", "dovit_bridge.main"]
