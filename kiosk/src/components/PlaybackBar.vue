<template>
  <div class="playback-bar">
    <div class="pb-left">
      <span class="pb-state" :class="`pb-state--${state}`">
        {{ stateLabel }}
      </span>
      <span v-if="show" class="pb-show">{{ show.name || show.show_id }}</span>
    </div>
    <div v-if="show && durationMs" class="pb-progress-wrap">
      <span class="pb-time">{{ formatMs(positionMs) }}</span>
      <div class="pb-bar">
        <div class="pb-fill" :style="{ width: (progress * 100) + '%' }"></div>
      </div>
      <span class="pb-time">{{ formatMs(durationMs) }}</span>
    </div>
    <div v-if="isActive" class="pb-controls">
      <button class="pb-btn" @click="$emit('pause')">
        {{ isPlaying ? '⏸' : '▶' }}
      </button>
      <button class="pb-btn pb-btn--stop" @click="$emit('stop')">&#9632;</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: String,
  show: Object,
  positionMs: Number,
  durationMs: Number,
  progress: Number,
  isPlaying: Boolean,
  isPaused: Boolean,
  isActive: Boolean,
})
defineEmits(['pause', 'stop'])

const stateLabel = computed(() => {
  if (props.state === 'playing') return 'Playing'
  if (props.state === 'paused') return 'Paused'
  return 'Idle'
})

function formatMs(ms) {
  const s = Math.floor((ms || 0) / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  if (h > 0) return `${h}:${String(m % 60).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`
  return `${m}:${String(s % 60).padStart(2,'0')}`
}
</script>

<style scoped>
.playback-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  background: #0e0e1a;
  border-top: 1px solid #1e1e2e;
  padding: 10px 24px;
  height: 56px;
  flex-shrink: 0;
}
.pb-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.pb-state {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}
.pb-state--playing { background: #14532d; color: #4ade80; }
.pb-state--paused  { background: #78350f; color: #fbbf24; }
.pb-state--idle    { background: #1e1e2e; color: #555; }
.pb-show {
  font-size: 0.9rem;
  color: #c0c0d0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pb-progress-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.pb-bar {
  flex: 1;
  height: 4px;
  background: #2a2a3a;
  border-radius: 2px;
  overflow: hidden;
}
.pb-fill {
  height: 100%;
  background: #5b7fff;
  transition: width 0.5s linear;
}
.pb-time {
  font-size: 0.8rem;
  color: #666;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.pb-controls { display: flex; gap: 8px; flex-shrink: 0; }
.pb-btn {
  background: #1e1e2e;
  border: 1px solid #2a2a3a;
  border-radius: 6px;
  color: #e0e0f0;
  font-size: 1rem;
  width: 36px;
  height: 36px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.pb-btn:hover { background: #2a2a3f; }
.pb-btn--stop { color: #ef4444; }
</style>
