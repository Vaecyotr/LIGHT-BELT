<template>
  <div class="brightness-slider">
    <div class="brightness-header">
      <span class="brightness-label">Brightness</span>
      <span class="brightness-value">{{ Math.round(modelValue * 100) }}%</span>
    </div>
    <input
      type="range"
      min="0"
      max="1"
      step="0.01"
      :value="modelValue"
      @input="onInput"
      @change="onChange"
      class="slider"
    />
  </div>
</template>

<script setup>
const props = defineProps({ modelValue: { type: Number, default: 1.0 } })
const emit = defineEmits(['update:modelValue', 'commit'])

function onInput(e) {
  emit('update:modelValue', parseFloat(e.target.value))
}
function onChange(e) {
  emit('commit', parseFloat(e.target.value))
}
</script>

<style scoped>
.brightness-slider { display: flex; flex-direction: column; gap: 8px; }
.brightness-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.brightness-label { font-size: 0.9rem; color: #888; }
.brightness-value { font-size: 0.9rem; color: #fbbf24; font-variant-numeric: tabular-nums; }
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
.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fbbf24;
  cursor: pointer;
  box-shadow: 0 0 6px rgba(251,191,36,0.5);
}
.slider::-moz-range-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fbbf24;
  cursor: pointer;
  border: none;
}
</style>
