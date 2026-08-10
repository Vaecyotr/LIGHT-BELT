#!/bin/sh
# LIGHT-BELT 开机设置 HDMI 显示模式。
#
# 背景：X 启动时抢在显示器 EDID 就绪之前，会退到 800x600 且不再重新探测。
# 内核 DRM 侧其实一直是好的（/sys/class/drm/.../edid 有 256 字节，
# modes 里 3840x2160 / 1920x1080 都在），只是 X 没拉进来。
#
# 做法：等 X 起来 → --auto 触发重新探测 → 显式设成目标模式。
# 目标模式不可用时退回显示器的首选模式，不会把屏幕搞黑。

export DISPLAY=:0
export XAUTHORITY=/home/topeet/.Xauthority

PREFERRED_MODE="1920x1080"      # 素材都是 1080p，分辨率对齐避免缩放
PREFERRED_RATE="60"

log() { echo "[hdmi-setup] $*"; }

# ── 1. 等 X 可用（最多 60 秒）──
i=0
while [ $i -lt 30 ]; do
    if xrandr --query >/dev/null 2>&1; then
        break
    fi
    i=$((i + 1))
    sleep 2
done
if ! xrandr --query >/dev/null 2>&1; then
    log "X 在 60 秒内没起来，放弃"
    exit 0
fi

# ── 2. 找到已连接的输出 ──
OUT=$(xrandr --query | awk '/ connected/ {print $1; exit}')
if [ -z "$OUT" ]; then
    log "没有已连接的显示输出"
    exit 0
fi
log "输出: $OUT"

# ── 3. 触发重新探测，把内核已识别的模式拉进 X ──
xrandr --output "$OUT" --auto 2>&1 | sed 's/^/[hdmi-setup] /'
sleep 2

# ── 4. 列出该输出当前可用的模式 ──
modes_for() {
    xrandr --query | awk -v out="$1" '
        $1 == out { f = 1; next }
        /^[^ \t]/ { f = 0 }
        f && NF { print $1 }'
}

MODES=$(modes_for "$OUT")
log "可用模式: $(echo "$MODES" | tr '\n' ' ')"

# ── 5. 显式设模式（--auto 之后当前模式可能仍是 800x600）──
if echo "$MODES" | grep -qx "$PREFERRED_MODE"; then
    if xrandr --output "$OUT" --mode "$PREFERRED_MODE" --rate "$PREFERRED_RATE" 2>/dev/null; then
        log "已设为 $PREFERRED_MODE @${PREFERRED_RATE}Hz"
    elif xrandr --output "$OUT" --mode "$PREFERRED_MODE" 2>/dev/null; then
        log "已设为 $PREFERRED_MODE（默认刷新率）"
    else
        log "设置 $PREFERRED_MODE 失败，保持 --auto 的结果"
    fi
else
    # 换了显示器、不支持 1080p 时走这里：用列表里第一个（EDID 首选模式）
    FALLBACK=$(echo "$MODES" | head -1)
    log "不支持 $PREFERRED_MODE，退回首选模式 $FALLBACK"
    [ -n "$FALLBACK" ] && xrandr --output "$OUT" --mode "$FALLBACK" 2>/dev/null
fi

# ── 6. 记录最终状态 ──
FINAL=$(xrandr --query | grep -A100 "^$OUT connected" | awk '/\*/ {print $1; exit}')
log "最终模式: ${FINAL:-未知}"
exit 0