"""Phase 10 no-hardware end-to-end acceptance test."""

from __future__ import annotations

import json
import math
from pathlib import Path

import light_engine.engine as engine_module
from light_engine.clock import OfflineRenderClock
from light_engine.config import Config
from light_engine.data.test_media import (
    cleanup_test_media,
    generate_test_video,
    generate_test_wav,
)
from light_engine.engine import Engine
from light_engine.outputs import OutputMode
from light_engine.outputs.json_output import JsonOutput
from light_engine.outputs.rs485_v2 import FRAME_LENGTH, RS485v2Packet
from light_engine.outputs.serial_output import SerialOutputV2
from light_engine.outputs.udp_output import UdpOutputV2
from light_engine.outputs.udp_v2 import FLAG_SAFE_STATE, UdpV2Packet


def _assert_finite(value: object, path: str = "root") -> None:
    if isinstance(value, float):
        assert math.isfinite(value), f"{path} is not finite: {value!r}"
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]")


def test_10s_video_audio_e2e(tmp_path: Path, monkeypatch) -> None:
    """Run video_audio_fusion through RS-485 v2, UDP v2, and JSON outputs."""
    video_path = tmp_path / "phase10_acceptance.mp4"
    audio_path = tmp_path / "phase10_acceptance.wav"
    json_path = tmp_path / "phase10_output.jsonl"

    generate_test_video(str(video_path), duration=10.0, fps=30.0, width=160, height=90)
    generate_test_wav(str(audio_path), duration=10.0, sample_rate=44100)
    monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)

    try:
        Config.reset()
        config = Config.get_instance()
        config._data["effects"]["video_audio_fusion"].update(
            {
                "video_weight": 0.75,
                "audio_weight": 0.15,
                "bass_boost": 0.0,
            }
        )
        engine = Engine(config, clock=OfflineRenderClock(fps=30.0))
        engine.load_video(str(video_path))
        engine.load_audio(str(audio_path))
        engine.set_effect("video_audio_fusion")

        rs485 = SerialOutputV2(mode=OutputMode.MEMORY)
        udp = UdpOutputV2(mode=OutputMode.MEMORY)
        json_output = JsonOutput(path=str(json_path))
        for output in (rs485, udp, json_output):
            output.open()
        engine._outputs = {
            "rs485_v2": rs485,
            "udp_v2": udp,
            "json": json_output,
        }

        engine.run(duration=10.0)

        normal_frame_count = engine.frame_count
        assert 300 <= normal_frame_count <= 301
        assert rs485.pending_frames() == 0
        assert udp.pending_frames() == 0

        rs485_raw = rs485.get_memory_bytes()
        assert len(rs485_raw) == (normal_frame_count + 1) * 6 * FRAME_LENGTH
        rs485_packets = [
            RS485v2Packet.decode(rs485_raw[offset : offset + FRAME_LENGTH])
            for offset in range(0, len(rs485_raw), FRAME_LENGTH)
        ]
        assert all(packet is not None for packet in rs485_packets)

        udp_datagrams = udp.get_sent_datagrams()
        assert len(udp_datagrams) == normal_frame_count + 1
        udp_packets = [UdpV2Packet.decode(data) for data, _address in udp_datagrams]
        assert all(packet is not None for packet in udp_packets)

        json_records = [
            json.loads(line)
            for line in json_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(json_records) == normal_frame_count + 1

        normal_rs485 = rs485_packets[: normal_frame_count * 6]
        normal_udp = udp_packets[:normal_frame_count]
        for frame_index in range(normal_frame_count):
            frame_rs485 = normal_rs485[frame_index * 6 : (frame_index + 1) * 6]
            frame_udp = normal_udp[frame_index]
            frame_json = json_records[frame_index]

            assert [packet.node_id for packet in frame_rs485] == [1, 2, 3, 4, 5, 6]
            assert frame_udp is not None
            assert frame_udp.digital_node_id == 7
            assert frame_json["sequence"] == frame_udp.sequence
            assert {packet.sequence for packet in frame_rs485} == {
                frame_udp.sequence & 0xFF
            }
            assert len(frame_json["analog_nodes"]) == 6
            assert len(frame_json["digital_nodes"]) == 1
            _assert_finite(frame_json, f"json_records[{frame_index}]")

        safe_rs485 = rs485_packets[normal_frame_count * 6 :]
        safe_udp = udp_packets[-1]
        safe_json = json_records[-1]

        assert len(safe_rs485) == 6
        assert safe_udp is not None
        assert safe_json["metadata"]["SAFE_STATE"] is True
        assert safe_json["metadata"]["safe_state"] is True
        assert {packet.sequence for packet in safe_rs485} == {safe_udp.sequence & 0xFF}
        assert all(packet.flags & FLAG_SAFE_STATE for packet in safe_rs485)
        assert safe_udp.flags & FLAG_SAFE_STATE
        assert all(
            packet.r == 0
            and packet.g == 0
            and packet.b == 0
            and packet.warm_white == 0
            and packet.cool_white == 0
            for packet in safe_rs485
        )
        assert all(pixel == (0, 0, 0) for pixel in safe_udp.pixels)
        assert all(
            node["r"] == 0
            and node["g"] == 0
            and node["b"] == 0
            and node["warm_white"] == 0
            and node["cool_white"] == 0
            for node in safe_json["analog_nodes"]
        )
        assert all(
            tuple(pixel) == (0, 0, 0)
            for node in safe_json["digital_nodes"]
            for pixel in node["pixels"]
        )
        _assert_finite(safe_json, "safe_json")
    finally:
        cleanup_test_media(str(video_path), str(audio_path))
