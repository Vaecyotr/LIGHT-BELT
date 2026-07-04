"""
检查视频特征 — 分析视频文件并打印每帧的颜色数据。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\inspect_video.py --video 视频文件.mp4

如果无视频文件，会自动生成一个测试视频。
"""

import sys
sys.path.insert(0, ".")
import argparse, os, tempfile
import cv2
from light_engine.analysis.video import VideoAnalyzer
from light_engine.config import Config

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--video", "-v", default=None, help="视频文件路径")
    p.add_argument("--max-frames", "-n", type=int, default=10)
    args = p.parse_args()

    video_path = args.video
    tmp_path = None

    if video_path is None or not os.path.exists(video_path):
        # 生成测试视频
        tmp_path = os.path.join(tempfile.gettempdir(), "inspect_test.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 1.0, (320, 240))
        colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 255, 0)]
        for c in colors:
            frame = cv2.cvtColor(
                cv2.UMat(240, 320, cv2.CV_8UC3).get(),
                cv2.COLOR_BGR2RGB, dst=cv2.UMat(240, 320, cv2.CV_8UC3)).get()
        for c in colors:
            f = cv2.UMat(240, 320, cv2.CV_8UC3)
            cv2.rectangle(f, (0, 0), (320, 240), c, -1)
            out.write(f.get())
        out.release()
        video_path = tmp_path
        print(f"未提供视频文件，已生成测试视频: {video_path}\n")

    Config.reset()
    analyzer = VideoAnalyzer(Config())
    cap = cv2.VideoCapture(video_path)

    # Read actual video metadata
    raw_fps = cap.get(cv2.CAP_PROP_FPS)
    actual_fps = raw_fps if raw_fps > 0 else 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / actual_fps if actual_fps > 0 else 0.0

    print(f"Video: {video_path}")
    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {actual_fps:.2f} (raw={raw_fps})")
    print(f"  Total frames: {total_frames}")
    print(f"  Duration: {duration:.2f}s")
    print()

    frame_idx = 0

    print(f"{'帧':>4s} {'时间':>6s} {'平均R':>6s} {'平均G':>6s} {'平均B':>6s} "
          f"{'亮度':>6s} {'饱和度':>6s} {'场景变化':>8s}")
    print("-" * 75)

    while frame_idx < args.max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        timestamp = frame_idx / actual_fps
        f = analyzer.analyze(frame, timestamp)
        r, g, b = f.average_rgb
        print(f"{frame_idx:4d} {timestamp:6.2f} {r:6.3f} {g:6.3f} {b:6.3f} "
              f"{f.brightness:6.3f} {f.saturation:6.3f} {f.scene_change:8.4f}")
        if f.zone_colors:
            z = f.zone_colors
            for zname in ("left", "center", "right", "top", "bottom"):
                if zname in z:
                    zr, zg, zb = z[zname]
                    print(f"      {zname}: R={zr:.2f} G={zg:.2f} B={zb:.2f}")
        frame_idx += 1

    cap.release()
    if tmp_path:
        os.unlink(tmp_path)

if __name__ == "__main__":
    main()
