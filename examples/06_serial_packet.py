"""
示例6: 生成STM32的11字节协议帧。

运行命令:
  cd /d A:\BaiduNetdiskDownload\LIGHT-BELT
  .python\python.exe examples\06_serial_packet.py

预期结果:
  输出十六进制: 55 01 FF 80 00 20 50 03 E8 DB AA
  每个字节都有详细解释。
"""

import sys
sys.path.insert(0, ".")

from light_engine.outputs.serial_output import SerialPacket, FRAME_LENGTH, _compute_checksum

print("=" * 60)
print("  示例6: STM32 11字节协议 — 固定测试向量")
print("=" * 60)

# 创建冻结测试向量
p = SerialPacket(
    cmd=0x01,       # 命令
    r=255,          # 红色 255
    g=128,          # 绿色 128
    b=0,            # 蓝色 0
    w=32,           # 白色 32
    brightness=80,  # 亮度 80%
    fade_ms=1000,   # 渐变时间 1000毫秒
)

raw = p.encode()
hex_str = " ".join(f"{b:02X}" for b in raw)

print(f"\n编码结果 ({len(raw)}字节):")
print(f"  {hex_str}")

# 逐字节解释
print(f"\n逐字节解释:")
print(f"  字节0:  {raw[0]:02X}  ← 帧头 (固定 0x55)")
print(f"  字节1:  {raw[1]:02X}  ← 命令")
print(f"  字节2:  {raw[2]:02X}  ← 红色 (0-255)")
print(f"  字节3:  {raw[3]:02X}  ← 绿色 (0-255)")
print(f"  字节4:  {raw[4]:02X}  ← 蓝色 (0-255)")
print(f"  字节5:  {raw[5]:02X}  ← 白色 (0-255)")
print(f"  字节6:  {raw[6]:02X}  ← 亮度 (0-100, 80%)")
print(f"  字节7:  {raw[7]:02X}  ┐")
print(f"  字节8:  {raw[8]:02X}  ┘ 渐变时间 (大端序, 0x03E8=1000ms)")
print(f"  字节9:  {raw[9]:02X}  ← 校验和 (Byte1~8累加和取低8位)")
print(f"  字节10: {raw[10]:02X}  ← 帧尾 (固定 0xAA)")

# 校验和计算
body = bytes(raw[1:9])
cs = _compute_checksum(body)
print(f"\n校验和计算: sum({[hex(b) for b in body]}) & 0xFF = {cs:#04X}")

# 验证
expected = bytes([0x55, 0x01, 0xFF, 0x80, 0x00, 0x20, 0x50, 0x03, 0xE8, 0xDB, 0xAA])
assert raw == expected, f"测试向量不匹配!\n  实际: {hex_str}\n  预期: {' '.join(f'{b:02X}' for b in expected)}"
print(f"\n[OK] 测试向量匹配通过!")

# 解码验证
decoded = SerialPacket.decode(raw)
assert decoded is not None
assert decoded.r == 255 and decoded.g == 128 and decoded.b == 0 and decoded.w == 32
assert decoded.brightness == 80 and decoded.fade_ms == 1000
print(f"[OK] 解码验证通过!")
