# -*- coding: utf-8 -*-
import asyncio
import logging
import time

LOGGER = logging.getLogger(__name__)
CURRENT_WRITER = object()

class DovitTcp:
    def __init__(self, host: str, port: int, heartbeat_interval: float = 5.0):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.heartbeat_interval = heartbeat_interval
        self._heartbeat_task: asyncio.Task | None = None
        self.connected_at = None
        self.last_rx_at = None
        self.rx_bytes = 0
        self.heartbeats_sent = 0
        self.on_connection_lost = None

    def _notify_connection_lost(self):
        # All TCP operations run on the owning asyncio loop.
        if self.on_connection_lost is not None:
            try:
                self.on_connection_lost()
            except Exception as exc:
                LOGGER.error("Dovit loss callback failed type=%s", type(exc).__name__)

    async def connect(self):
        await self.close()
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=10
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat())
        self.connected_at = time.monotonic()
        self.last_rx_at = None
        self.rx_bytes = 0
        self.heartbeats_sent = 0
        LOGGER.info('%s', f"Connected to Dovit {self.host}:{self.port}")

    async def send(self, data: bytes, *, expected_writer=CURRENT_WRITER):
        writer = self.writer
        if expected_writer is not CURRENT_WRITER and (expected_writer is None or writer is not expected_writer):
            LOGGER.warning("Dovit send rejected: stale connection; command not replayed")
            raise ConnectionError("Dovit command belongs to an expired connection")
        if writer is None or writer.is_closing():
            self._notify_connection_lost()
            LOGGER.error("Dovit send rejected: disconnected; command not queued or retried")
            raise ConnectionError("Dovit is disconnected")
        try:
            writer.write(data)
            await asyncio.wait_for(writer.drain(), timeout=10)
        except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
            # Never log payloads: alarm authentication frames contain secrets.
            LOGGER.error("Dovit send failed (%s); delivery unconfirmed, no retry", type(exc).__name__)
            if self.writer is writer:
                self._notify_connection_lost()
            writer.close()
            raise

    async def _heartbeat(self):
        writer = self.writer
        try:
            while True:
                # Captured Windows app traffic sends one NUL every five seconds.
                await self.send(b"\x00")
                self.heartbeats_sent += 1
                if self.heartbeats_sent % max(1, round(300 / self.heartbeat_interval)) == 0:
                    now = time.monotonic()
                    LOGGER.info("Dovit health connected_seconds=%.0f rx_bytes=%s last_rx_age_seconds=%s heartbeats_sent=%s",
                                now - self.connected_at, self.rx_bytes,
                                round(now - self.last_rx_at, 1) if self.last_rx_at else "none",
                                self.heartbeats_sent)
                await asyncio.sleep(self.heartbeat_interval)
        except asyncio.CancelledError:
            raise
        except (OSError, RuntimeError, asyncio.TimeoutError):
            # Closing wakes the read loop, which owns reconnection.
            if writer is not None and self.writer is writer:
                writer.close()

    async def close(self):
        self._notify_connection_lost()
        task, self._heartbeat_task = self._heartbeat_task, None
        self.reader = None
        writer, self.writer = self.writer, None
        self.connected_at = None
        if writer is not None:
            writer.close()
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if writer is not None:
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except (OSError, RuntimeError, asyncio.TimeoutError):
                pass

    async def read(self, n: int = 4096) -> bytes:
        if not self.reader:
            self._notify_connection_lost()
            raise RuntimeError("Dovit reader not set (not connected).")
        try:
            chunk = await self.reader.read(n)
        except (OSError, RuntimeError):
            await self.close()
            raise
        if not chunk:
            LOGGER.warning("Dovit TCP EOF: peer closed connection")
            await self.close()
        else:
            self.rx_bytes += len(chunk)
            self.last_rx_at = time.monotonic()
        return chunk
