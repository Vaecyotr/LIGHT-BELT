"""
示例8: 视频分区颜色到灯带的映射验证。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\08_video_zone_mapping.py

生成人工五色测试画面，验证:
  - 视频五个区域颜色正确提取
  - 6条灯带正确绑定到各自视频区域
  - ceiling_left/right 都来自 top (黄色)
  - wall_left 来自 left (红色)
  - wall_right 来自 right (蓝色)
  - front/rear 来自 center (绿色)
"""

import sys
sys.path.insert(0, ".")

import cv2
import numpy as np
from light_engine.analysis.video import VideoAnalyzer
from light_engine.config import Config
from light_engine.mapping.resolve import resolve_video_color

# ---------- 1. 生成人工五色测试画面 ----------
# 布局: 上方黄色, 左侧红色, 中间绿色, 右侧蓝色, 下方紫色
H, W = 180, 320
frame = np.zeros((H, W, 3), dtype=np.uint8)

# top (上1/5): yellow
frame[0:36, :] = (0, 255, 255)      # BGR yellow

# left (左1/3): red
frame[36:144, 0:106] = (0, 0, 255)  # BGR red

# right (右1/3): blue
frame[36:144, 214:320] = (255, 0, 0) # BGR blue

# center (中间1/3): green
frame[36:144, 106:214] = (0, 255, 0) # BGR green

# bottom (下1/5): purple
frame[144:180, :] = (128, 0, 128)    # BGR purple

print("人工测试画面: 320x180")
print("  top    (0:36)   = 黄色 BGR(0,255,255)")
print("  left   (106:0)  = 红色 BGR(0,0,255)")
print("  center (106:214)= 绿色 BGR(0,255,0)")
print("  right  (214:320)= 蓝色 BGR(255,0,0)")
print("  bottom (144:180)= 紫色 BGR(128,0,128)")
print()

# ---------- 2. 视频分析 ----------
Config.reset()
analyzer = VideoAnalyzer(Config())
features = analyzer.analyze(frame, 0.0)

print("=" * 50)
print("  视频分析结果")
print("=" * 50)
print(f"  平均色:        ({features.average_rgb[0]:.2f},{features.average_rgb[1]:.2f},{features.average_rgb[2]:.2f})")
print(f"  主色:          ({features.dominant_rgb[0]:.2f},{features.dominant_rgb[1]:.2f},{features.dominant_rgb[2]:.2f})")
print(f"  亮度: {features.brightness:.3f}  饱和度: {features.saturation:.3f}")
for name in ("left", "center", "right", "top", "bottom"):
    c = features.zone_colors.get(name, (0, 0, 0))
    print(f"  zone[{name:>6s}]: R={c[0]:.2f} G={c[1]:.2f} B={c[2]:.2f}")
print()

# ---------- 3. 灯带映射 ----------
strip_map = [
    ("ceiling_left",  "top"),
    ("ceiling_right", "top"),
    ("wall_left",     "left"),
    ("wall_right",    "right"),
    ("front",         "center"),
    ("rear",          "center"),
]

print("=" * 50)
print("  灯带 → 视频区域映射结果")
print("=" * 50)

all_different = set()
for strip_id, video_zone in strip_map:
    r, g, b = resolve_video_color(video_zone, features, strip_id)
    print(f"  {strip_id:<16} <- {video_zone:<7s}  RGB=({r:.2f},{g:.2f},{b:.2f})")
    all_different.add((round(r, 1), round(g, 1), round(b, 1)))

print()

# ---------- 4. 验证 ----------
# ceiling_left == ceiling_right (both top=yellow)
cl = resolve_video_color("top", features, "ceiling_left")
cr = resolve_video_color("top", features, "ceiling_right")
assert abs(cl[0] - cr[0]) < 0.01 and abs(cl[1] - cr[1]) < 0.01, "Ceiling L/R should match"
print("[OK] ceiling_left == ceiling_right (both from top)")

# wall_left != wall_right (different zones)
wl = resolve_video_color("left", features, "wall_left")
wr = resolve_video_color("right", features, "wall_right")
assert wl[0] > wl[1], "Left should be red (R > G)"
assert wr[2] > wr[0], "Right should be blue (B > R)"
print("[OK] wall_left (red) != wall_right (blue)")

# front == rear (both center=green)
fr = resolve_video_color("center", features, "front")
re = resolve_video_color("center", features, "rear")
assert abs(fr[1] - re[1]) < 0.01, "Front/Rear should match"
assert fr[1] > fr[0] and fr[1] > fr[2], "Center should be green"
print("[OK] front == rear (both from center, green)")

# All zones are NOT the same
assert len(all_different) >= 3, f"Expected at least 3 different colors, got {len(all_different)}"
print(f"[OK] 灯带颜色不少于3种不同颜色 (实际{len(all_different)}种)")

print(f"\n全部映射验证通过! 视频分区颜色正确传递到各灯带。")
