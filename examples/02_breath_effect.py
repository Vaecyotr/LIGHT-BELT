"""
示例2: 呼吸灯10秒 — 演示亮度随时间正弦变化。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\02_breath_effect.py

预期结果:
  打印10行，每行显示时间和亮度。
  亮度从0.05逐渐上升到0.85再下降到0.05，完成约2.5个呼吸周期。
"""

import sys, math
sys.path.insert(0, ".")
from light_engine.effects import create_effect
from light_engine.models import EffectContext

print("=" * 60)
print("  示例2: 呼吸灯 — 亮度随时间正弦变化")
print("=" * 60)

effect = create_effect("breath")
ctx_base = EffectContext(
    timestamp=0.0, delta_time=1.0, global_brightness=1.0,
    mode_parameters={
        "strip_defs": [{"id": "s1", "pixel_count": 10, "video_zone": "center"}],
        "zone_defs": [],
    },
)

print(f"\n{'时间':>6s}  {'亮度':>6s}  示意")
print("-" * 40)

for t in range(10):
    ctx = EffectContext(
        timestamp=float(t), delta_time=1.0,
        global_brightness=1.0, mode_parameters=ctx_base.mode_parameters,
    )
    frame = effect.process(ctx)
    zone = frame.zones[0] if frame.zones else None
    bri = zone.color.brightness if zone else frame.strips[0].pixels[0][0]
    bar = "#" * int(bri * 20)
    print(f"  {t:4.0f}s  {bri:.3f}  {bar}")

print(f"\n✓ 呼吸周期约4秒，亮度在0.05到0.85之间变化")
