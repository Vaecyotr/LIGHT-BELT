<template>
  <button class="show-card" @click="$emit('play', show.show_id)">
    <div class="show-color" :style="{ background: cardColor }"></div>
    <div class="show-body">
      <div class="show-name">{{ show.name || show.show_id }}</div>
      <div v-if="show.description" class="show-desc">{{ show.description }}</div>
      <div class="show-duration">{{ formatDuration(show.duration_ms) }}</div>
    </div>
    <div class="show-play-icon">&#9654;</div>
  </button>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ show: Object })
defineEmits(['play'])

const PALETTE = [
  '#1e3a5f', '#2d1b4e', '#1a3d2b', '#3d1a1a', '#1a2d3d',
  '#3d2d1a', '#1a3d3d', '#3d1a3d', '#2d3d1a', '#1a1a3d',
]

const cardColor = computed(() => {
  const idx = (props.show.show_id || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length
  return PALETTE[idx]
})

function formatDuration(ms) {
  if (!ms) return '—'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  if (h > 0) return `${h}:${String(m % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
  return `${m}:${String(s % 60).padStart(2, '0')}`
}
</script>

<style scoped>
.show-card {
  display: flex;
  align-items: center;
  gap: 0;
  background: #16161f;
  border: 1px solid #2a2a3a;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.1s;
  text-align: left;
  width: 100%;
  min-height: 80px;
}
.show-card:hover {
  border-color: #5b7fff;
  transform: translateY(-1px);
}
.show-card:active { transform: scale(0.98); }
.show-color {
  width: 8px;
  align-self: stretch;
  flex-shrink: 0;
}
.show-body {
  flex: 1;
  padding: 14px 16px;
  min-width: 0;
}
.show-name {
  font-size: 1.05rem;
  font-weight: 600;
  color: #e8e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.show-desc {
  font-size: 0.8rem;
  color: #666;
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.show-duration {
  font-size: 0.8rem;
  color: #5b7fff;
  margin-top: 6px;
  font-variant-numeric: tabular-nums;
}
.show-play-icon {
  padding: 0 20px;
  font-size: 1.2rem;
  color: #5b7fff;
  opacity: 0.7;
}
.show-card:hover .show-play-icon { opacity: 1; }
</style>
