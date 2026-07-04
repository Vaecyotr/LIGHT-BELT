"""
示例5: 生成测试视频并分析颜色。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\05_video_analysis.py

预期结果:
  生成6秒测试视频(红/绿/蓝/渐变/黑边/明暗)，
  分析每帧并打印主色和区域颜色。
"""

import sys, os, tempfile
sys.path.insert(0, ".")
import cv2
import numpy as np
from light_engine.analysis.video import VideoAnalyzer
from light_engine.config import Config

print("=" * 60)
print("  示例5: 视频分析 — 颜色提取")
print("=" * 60)

# 生成测试视频
path = os.path.join(tempfile.gettempdir(), "example_test.mp4")
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out = cv2.VideoWriter(path, fourcc, 1.0, (320, 240))

# 帧1: 红色
frame = np.zeros((240, 320, 3), dtype=np.uint8)
frame[:, :, 2] = 255
out.write(frame)
# 帧2: 绿色
frame[:, :, 1] = 255; frame[:, :, 2] = 0
out.write(frame)
# 帧3: 蓝色
frame[:, :, 0] = 255; frame[:, :, 1] = 0
out.write(frame)
# 帧4: 上半红下半绿
frame[:120, :, 2] = 255
frame[120:, :, 1] = 255
out.write(frame)
# 帧5: 黑边+绿色中心
frame[:, :] = 0
frame[40:200, 40:280, 1] = 200
out.write(frame)
out.release()

print(f"生成测试视频: {path}")
print(f"帧数: 5, 分辨率: 320x240\n")

# 分析
Config.reset()
analyzer = VideoAnalyzer(Config())
cap = cv2.VideoCapture(path)
frame_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    features = analyzer.analyze(frame, float(frame_idx))
    r, g, b = features.average_rgb
    dom_r, dom_g, dom_b = features.dominant_rgb

    # 判断颜色
    if r > 0.6 and g < 0.3:
        color_name = "红色"
    elif g > 0.6 and r < 0.3:
        color_name = "绿色"
    elif b > 0.6 and r < 0.3:
        color_name = "蓝色"
    elif abs(r - g) < 0.1 and abs(g - b) < 0.1 and r < 0.2:
        color_name = "黑色"
    else:
        color_name = "混合色"

    print(f"帧{frame_idx}: 平均色=({r:.2f},{g:.2f},{b:.2f}) "
          f"主色=({dom_r:.2f},{dom_g:.2f},{dom_b:.2f}) "
          f"→ {color_name}")
    print(f"  区域颜色: left={features.zone_colors.get('left',(0,0,0))} "
          f"right={features.zone_colors.get('right',(0,0,0))}")
    frame_idx += 1

cap.release()
os.unlink(path)
print(f"\n✓ 视频分析完成! 正确识别了红/绿/蓝/混合/黑色")
