# Third-party components

The custom D2HA Bridge license applies only to the project's original files.
It does not replace the licenses of dependencies or container components.

- **Eclipse Paho MQTT Python 2.1.0** is installed from PyPI when the Docker image
  is built. It is dual licensed under Eclipse Public License 2.0 and Eclipse
  Distribution License 1.0. See the upstream
  [license notice](https://github.com/eclipse-paho/paho.mqtt.python/blob/v2.1.0/LICENSE.txt),
  [EPL text](https://github.com/eclipse-paho/paho.mqtt.python/blob/v2.1.0/epl-v20),
  and [EDL text](https://github.com/eclipse-paho/paho.mqtt.python/blob/v2.1.0/edl-v10).
- **Python and Alpine Linux components** come from the official
  [`python:3.11.17-alpine3.23` container image](https://hub.docker.com/_/python),
  pinned by its multi-architecture digest in the Dockerfile.
  They retain their respective licenses and notices supplied in that image.

This repository does not vendor those dependencies. The release workflow is
prepared to publish versioned multi-architecture GHCR images; Home Assistant
downloads the released image. Publication/anonymous pulls remain pending until
the owner completes the release steps.
