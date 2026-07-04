"""
示例3: 跑马灯 — 显示光点位置如何随时间变化。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\03_chase_effect.py

预期结果:
  打印10行，显示光点沿10像素灯带前进的位置。
  使用delta_time推进，不依赖固定FPS。
"""

import sys
sys.path.insert(0, ".")
from light_engine.effects import create_effect
from light_engine.models import EffectContext

print("=" * 60)
print("  示例3: 跑马灯 — 位置随时间变化")
print("=" * 60)

effect = create_effect("chase")
strip_defs = [{"id": "s1", "pixel_count": 10, "video_zone": "center"}]
ctx_base = {"strip_defs": strip_defs, "zone_defs": []}

print(f"\n光点速度: 2像素/秒 (speed=1.0)")
print(f"帧间隔: 0.5秒 (正常情况下约0.033秒)")
print(f"\n{'帧':>4s}  {'时间':>6s}  {'位置':>6s}  灯光示意(10像素)")
print("-" * 55)

pos = 0.0
for frame_i in range(10):
    dt = 0.5  # 用较大dt便于观察
    ctx = EffectContext(
        timestamp=frame_i * dt, delta_time=dt, global_brightness=1.0,
        mode_parameters=ctx_base,
    )
    frame = effect.process(ctx)
    pos_str = effect.get_parameters()["position"]

    # 显示10像素的亮/暗
    pixels = frame.strips[0].pixels
    display = ""
    for i, (r, g, b) in enumerate(pixels):
        if max(r, g, b) > 0.1:
            display += "█"
        else:
            display += "·"
    print(f"  {frame_i:3d}  {frame_i*dt:5.1f}s  {pos_str:>6s}   {display}")

print(f"\n✓ 光点以每秒2像素的速度向右移动")
print(f"  改变delta_time不会改变移动速度，因为使用delta_time计算位移")
