<template>
  <div class="volume-slider">
    <div class="volume-header">
      <span class="volume-label">Volume</span>
      <button class="mute-btn" :class="{ 'mute-btn--active': muted }" @click="$emit('toggleMute')">
        {{ muted ? '🔇' : '🔊' }}
      </button>
      <span class="volume-value">{{ muted ? 'Muted' : Math.round(modelValue * 100) + '%' }}</span>
    </div>
    <input
      type="range"
      min="0"
      max="1"
      step="0.01"
      :value="modelValue"
      :disabled="muted"
      @input="onInput"
      @change="onChange"
      class="slider"
      :class="{ 'slider--muted': muted }"
    />
  </div>
</template>

<script setup>
defineProps({ modelValue: { type: Number, default: 1.0 }, muted: { type: Boolean, default: false } })
const emit = defineEmits(['update:modelValue', 'commit', 'toggleMute'])

function onInput(e) { emit('update:modelValue', parseFloat(e.target.value)) }
function onChange(e) { emit('commit', parseFloat(e.target.value)) }
</script>

<style scoped>
.volume-slider { display: flex; flex-direction: column; gap: 8px; }
.volume-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.volume-label { font-size: 0.9rem; color: #888; flex: 1; }
.volume-value { font-size: 0.9rem; color: #38bdf8; font-variant-numeric: tabular-nums; min-width: 48px; text-align: right; }
.mute-btn {
  background: none;
  border: 1px solid #2a2a3a;
  border-radius: 6px;
  width: 32px;
  height: 28px;
  cursor: pointer;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.15s;
}
.mute-btn--active { border-color: #ef4444; }
.mute-btn:hover { border-color: #38bdf8; }
.slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  background: #2a2a3a;
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}
.slider--muted { opacity: 0.35; cursor: default; }
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #38bdf8;
  cursor: pointer;
  box-shadow: 0 0 6px rgba(56,189,248,0.5);
}
.slider::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #38bdf8;
  cursor: pointer;
  border: none;
}
</style>
