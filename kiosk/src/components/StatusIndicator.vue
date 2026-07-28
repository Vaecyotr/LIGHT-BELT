<template>
  <div class="status-indicator">
    <span class="dot" :class="connected ? 'dot--on' : 'dot--off'"></span>
    <span class="label">{{ connected ? 'Connected' : 'Disconnected' }}</span>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api.js'

const connected = ref(false)

async function check() {
  try {
    const res = await api.status()
    connected.value = !!res.ok
  } catch (_) {
    connected.value = false
  }
}

let timer = null
onMounted(() => { check(); timer = setInterval(check, 5000) })
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: #888;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot--on  { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
.dot--off { background: #ef4444; }
.label { user-select: none; }
</style>
