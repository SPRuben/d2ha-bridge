"""UTC, single-line logs suitable for the Home Assistant add-on log."""
import logging
import sys
import time


class SafeFormatter(logging.Formatter):
    converter = time.gmtime

    def __init__(self, secrets=()):
        super().__init__("%(asctime)s.%(msecs)03dZ %(levelname)s [%(name)s] %(message)s",
                         datefmt="%Y-%m-%dT%H:%M:%S")
        self.secrets = tuple(sorted({str(s) for s in secrets if s}, key=len, reverse=True))

    def format(self, record):
        result = super().format(record)
        for secret in self.secrets:
            result = result.replace(secret, "[REDACTED]")
        return result.replace("\r", "\\r").replace("\n", "\\n")


def setup_logging(secrets=()):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeFormatter(secrets))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
