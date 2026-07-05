"""RS-485 v2 output for STM32 RGB+CCT analog nodes."""

from __future__ import annotations

from typing import Optional

from light_engine.mapping.physical import PhysicalFrame
from light_engine.outputs import LatestFrameQueue, LightOutput, OutputMode
from light_engine.outputs.rs485_v2 import RS485v2Packet


class SerialOutputV2(LightOutput):
    """RS-485 v2 transport for complete physical analog frames.

    MEMORY and FAKE modes are explicit non-hardware modes. PRODUCTION opens the
    configured serial port and never falls back to memory if opening or writing
    fails.
    """

    def __init__(
        self,
        *,
        mode: OutputMode | str = OutputMode.MEMORY,
        port: str = "COM3",
        baudrate: int = 115200,
        timeout: float = 0.1,
        transport: Optional[object] = None,
        auto_flush: bool = True,
    ) -> None:
        super().__init__()
        self.mode = OutputMode.from_config(mode)
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._transport = transport
        self._owns_transport = False
        self._memory_transport = bytearray()
        self._queue: LatestFrameQueue[PhysicalFrame] = LatestFrameQueue()
        self._auto_flush = auto_flush

    def open(self) -> None:
        if self._transport is not None:
            self._open = True
            return
        if self.mode is OutputMode.PRODUCTION:
            try:
                import serial as _serial

                self._transport = _serial.Serial(
                    self._port, self._baudrate, timeout=self._timeout
                )
                self._owns_transport = True
            except Exception as exc:
                self._health.healthy = False
                self._health.last_error = (
                    f"RS-485 production port {self._port} unavailable: {exc}"
                )
                raise RuntimeError(self._health.last_error) from exc
        self._open = True

    def send_frame(self, frame: PhysicalFrame) -> None:
        if not self._open:
            self._health.frames_dropped += 1
            self._health.last_error = "RS-485 output is not open"
            return
        if self._queue.push(frame):
            self._health.frames_dropped += 1
        if self._auto_flush:
            self.flush_latest()

    def flush_latest(self) -> None:
        frame = self._queue.pop_latest()
        if frame is None:
            return
        try:
            packets = self._encode_frame(frame)
            for packet in packets:
                self._write_packet(packet)
                self._health.packets_sent += 1
            self._health.logical_frames_sent += 1
            self._health.mark_success()
        except Exception as exc:
            self._health.frames_dropped += 1
            self._health.last_error = f"RS-485 v2 send error: {exc}"
            if self.mode is OutputMode.PRODUCTION:
                self._health.healthy = False
                raise

    def _encode_frame(self, frame: PhysicalFrame) -> list[bytes]:
        flags = 0x01 if frame.metadata.get("SAFE_STATE") is True else 0
        packets = []
        for command in sorted(frame.analog_commands, key=lambda item: item.node_id):
            channels = command.color.to_uint8()
            packets.append(
                RS485v2Packet(
                    node_id=command.node_id,
                    sequence=frame.sequence & 0xFF,
                    r=channels["r"],
                    g=channels["g"],
                    b=channels["b"],
                    warm_white=channels["warm_white"],
                    cool_white=channels["cool_white"],
                    fade_ms=command.fade_ms,
                    flags=flags,
                ).encode()
            )
        return packets

    def _write_packet(self, packet: bytes) -> None:
        if self.mode is OutputMode.FAKE:
            return
        if self.mode is OutputMode.MEMORY and self._transport is None:
            self._memory_transport.extend(packet)
            return
        if self._transport is None:
            raise RuntimeError("RS-485 production transport is not open")
        self._transport.write(packet)  # type: ignore[attr-defined]

    def close(self) -> None:
        if self._owns_transport and self._transport is not None:
            try:
                self._transport.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._transport = None
        self._owns_transport = False
        self._open = False

    def get_memory_bytes(self) -> bytes:
        return bytes(self._memory_transport)

    def pending_frames(self) -> int:
        return len(self._queue)

    def capabilities(self) -> dict:
        caps = super().capabilities()
        caps.update(
            {
                "supports_rgbcct": True,
                "protocol": "RS-485 RGB+CCT fixed frame v2",
                "frame_length": 16,
                "mode": self.mode.value,
                "transport": "injected"
                if self._transport is not None and not self._owns_transport
                else self.mode.value,
                "hardware_verified": False,
            }
        )
        return caps
