"""
示例7: 完整流水线 — 从合成特征到PixelFrame到模拟器输出。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\07_full_pipeline.py

预期结果:
  运行3帧，显示每帧的完整数据流:
  合成特征 → EffectContext → 灯效 → PixelFrame → 输出
"""

import sys
sys.path.insert(0, ".")
from light_engine.data.generators import SyntheticDataSource
from light_engine.effects import create_effect
from light_engine.models import EffectContext
from light_engine.outputs import SimulatorOutput

print("=" * 60)
print("  示例7: 完整流水线 — 3帧端到端演示")
print("=" * 60)

# 1. 创建合成数据源
source = SyntheticDataSource(seed=42)
print("1. 合成数据源已创建 (种子=42)")

# 2. 创建灯效
effect = create_effect("video_audio_fusion")
print(f"2. 灯效: {effect.name} (视频+音频融合)")

# 3. 创建输出
output = SimulatorOutput()
output.open()
print("3. 模拟器输出已打开")

# 4. 流水线: 3帧
strip_defs = [
    {"id": f"s{i}", "pixel_count": 10, "video_zone": z}
    for i, z in enumerate(["top", "top", "left", "right", "center", "center"])
]
zone_defs = [{"id": f"z{i}", "video_zone": z} for i, z in enumerate(["top", "top", "left", "right", "center", "center"])]

for frame_num in range(3):
    timestamp = frame_num * 0.033
    print(f"\n{'='*40}")
    print(f"  帧 {frame_num+1}/3 (时间={timestamp:.3f}s)")
    print(f"{'='*40}")

    # 获取合成特征
    video_f = source.get_video_features(timestamp)
    audio_f = source.get_audio_features(timestamp)

    print(f"  视频: 平均色=({video_f.average_rgb[0]:.2f},{video_f.average_rgb[1]:.2f},{video_f.average_rgb[2]:.2f}) "
          f"亮度={video_f.brightness:.2f}")
    print(f"  音频: RMS={audio_f.rms:.3f} bass={audio_f.bass:.3f} "
          f"mid={audio_f.mid:.3f} beat={'是' if audio_f.beat else '否'}")

    # 构建上下文
    ctx = EffectContext(
        timestamp=timestamp, delta_time=0.033, global_brightness=0.85,
        video_features=video_f, audio_features=audio_f,
        mode_parameters={"strip_defs": strip_defs, "zone_defs": zone_defs},
    )

    # 运行灯效
    frame = effect.process(ctx)

    # 发送到输出
    output.send_frame(frame)

    # 显示第一条灯带前5像素
    strip = frame.strips[0]
    for i in range(min(5, strip.pixel_count)):
        r, g, b = strip.to_uint8()[i]
        bar = "█" * (max(r, g, b) // 25)
        print(f"  灯带0-像素{i}: RGB({r:3d},{g:3d},{b:3d}) {bar}")

    print(f"  输出缓冲区帧数: {output.frame_count()}")

output.close()
print(f"\n{'='*60}")
print(f"  完整流水线演示完成!")
print(f"  3帧已处理: 合成数据 → 分析 → 融合灯效 → 模拟器输出")
print(f"{'='*60}")
