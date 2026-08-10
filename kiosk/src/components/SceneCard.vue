<template>
  <button class="scene-card" :class="{ 'scene-card--busy': busy }" @click="$emit('apply', scene.scene_id)" :disabled="busy">
    <span class="scene-name">{{ scene.name || scene.scene_id }}</span>
    <span class="scene-apply">{{ busy ? '…' : 'Apply' }}</span>
  </button>
</template>

<script setup>
defineProps({ scene: Object, busy: Boolean })
defineEmits(['apply'])
</script>

<style scoped>
.scene-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #16161f;
  border: 1px solid #2a2a3a;
  border-radius: 8px;
  padding: 12px 16px;
  cursor: pointer;
  width: 100%;
  transition: border-color 0.15s;
  gap: 12px;
}
.scene-card:hover:not(:disabled) { border-color: #a78bfa; }
.scene-card:active:not(:disabled) { transform: scale(0.98); }
.scene-card--busy { opacity: 0.6; cursor: default; }
.scene-name {
  font-size: 0.95rem;
  color: #d0d0e0;
  flex: 1;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.scene-apply {
  font-size: 0.8rem;
  color: #a78bfa;
  font-weight: 600;
  flex-shrink: 0;
}
</style>
