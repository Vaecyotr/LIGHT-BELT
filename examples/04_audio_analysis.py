"""
示例4: 生成音频并分析低中高频能量。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\04_audio_analysis.py

预期结果:
  低频(80Hz)段 → bass值最高
  中频(1000Hz)段 → mid值最高
  高频(8000Hz)段 → treble值最高
  静音段 → silence=True, beat=False
"""

import sys, math
sys.path.insert(0, ".")
import numpy as np
from light_engine.analysis.audio import AudioAnalyzer
from light_engine.config import Config

def make_sine(freq, duration, sr=44100):
    """生成指定频率的正弦波"""
    t = np.arange(int(duration * sr), dtype=np.float32) / sr
    return np.sin(2 * np.pi * freq * t).astype(np.float32)

print("=" * 60)
print("  示例4: 音频分析 — 低、中、高频识别")
print("=" * 60)

Config.reset()
analyzer = AudioAnalyzer(Config())

# === 测试1: 低频正弦 (80Hz) ===
print("\n--- 测试1: 80Hz低频正弦 ---")
bass_samples = make_sine(80, 0.1)
features = analyzer.analyze(bass_samples, 1.0)
print(f"  RMS: {features.rms:.3f}  静音: {features.silence}")
print(f"  bass(低): {features.bass:.3f}  ← 应该最高")
print(f"  mid(中):  {features.mid:.3f}")
print(f"  treble(高): {features.treble:.3f}")
assert features.bass > features.mid, "低频应该比中频强!"
assert features.bass > features.treble, "低频应该比高频强!"
print(f"  [OK] 低频识别正确!")

# === 测试2: 中频正弦 (1000Hz) ===
print("\n--- 测试2: 1000Hz中频正弦 ---")
mid_samples = make_sine(1000, 0.1)
features = analyzer.analyze(mid_samples, 2.0)
print(f"  bass(低):  {features.bass:.3f}")
print(f"  mid(中):   {features.mid:.3f}  ← 应该最高")
print(f"  treble(高): {features.treble:.3f}")
assert features.mid > features.bass, "中频应该比低频强!"
assert features.mid > features.treble, "中频应该比高频强!"
print(f"  [OK] 中频识别正确!")

# === 测试3: 高频正弦 (8000Hz) ===
print("\n--- 测试3: 8000Hz高频正弦 ---")
treble_samples = make_sine(8000, 0.1)
features = analyzer.analyze(treble_samples, 3.0)
print(f"  bass(低):   {features.bass:.3f}")
print(f"  mid(中):    {features.mid:.3f}")
print(f"  treble(高): {features.treble:.3f}  ← 应该最高")
assert features.treble > features.bass, "高频应该比低频强!"
assert features.treble > features.mid, "高频应该比中频强!"
print(f"  [OK] 高频识别正确!")

# === 测试4: 静音 ===
print("\n--- 测试4: 静音检测 ---")
silence_samples = np.zeros(4410, dtype=np.float32)
features = analyzer.analyze(silence_samples, 4.0)
print(f"  RMS: {features.rms:.3f}  静音: {features.silence}  节拍: {features.beat}")
assert features.silence, "全零应该被识别为静音!"
assert not features.beat, "静音不应该有节拍!"
print(f"  [OK] 静音检测正确!")

print(f"\n" + "=" * 60)
print(f"  全部4项测试通过! 音频分析工作正常。")
print(f"=" * 60)
