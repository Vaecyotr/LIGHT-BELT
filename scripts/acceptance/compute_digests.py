"""Scratch: compute pinned offline-render digests for the acceptance show test."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from light_engine.config import Config  # noqa: E402
from light_engine.mapping import Layout  # noqa: E402
from light_engine.models import EffectContext  # noqa: E402
from light_engine.outputs.transform import OutputTransform  # noqa: E402
from light_engine.show import TargetCatalog, load_show  # noqa: E402
from light_engine.show.compositor import ShowRuntime, black_base_frame  # noqa: E402

PROFILE = ROOT / "config/profiles/rk3588-host-service.yaml"
SHOW = ROOT / "config/acceptance/single-strip-acceptance-v1/show.yaml"
FPS = 15


def main() -> None:
    Config.reset()
    config = Config.get_instance(PROFILE)
    layout = Layout.from_config(config)
    catalog = TargetCatalog.from_layout(layout)
    show = load_show(SHOW, catalog)
    runtime = ShowRuntime.from_layout(show, layout)
    transform = OutputTransform(
        global_brightness=config.get("system.smoothing.max_brightness", 0.85),
        gamma=config.get("system.smoothing.gamma", 1.0),
        power_limit=5.0,
        per_zone_warm_bias={},
        per_zone_cool_bias={},
    )
    strips = list(layout.strips)
    zones = list(layout.zones)
    frame_index = 0
    dt = 1.0 / FPS
    total_frames = int(show.duration * FPS)
    results: dict[str, str] = {}
    while frame_index < total_frames:
        t = frame_index * dt
        ctx = EffectContext(
            timestamp=t,
            delta_time=dt,
            sequence=frame_index,
            audio_features=None,
            video_features=None,
            music_control_state=None,
            mode_parameters={"strip_defs": [], "zone_defs": []},
        )
        base = black_base_frame(timestamp=t, sequence=frame_index,
                                analog_zones=zones, digital_strips=strips)
        frame = runtime.render(ctx, base)
        if frame_index % 900 == 8:
            transformed = transform.apply_to_frame(frame)
            strip = next(s for s in transformed.strips if s.strip_id == "strip_31")
            payload = json.dumps(strip.to_uint8(), separators=(",", ":"))
            results[f"{t:.3f}"] = hashlib.sha256(payload.encode()).hexdigest()
        frame_index += 1
    print(json.dumps(results, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
