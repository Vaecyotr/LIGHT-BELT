<template>
  <div class="kiosk-root">
    <!-- Header -->
    <header class="kiosk-header">
      <div class="brand">
        <span class="brand-icon">&#9650;</span>
        <span class="brand-name">LIGHT-BELT</span>
      </div>
      <StatusIndicator />
    </header>

    <!-- Main content -->
    <main class="kiosk-main">
      <!-- Shows column -->
      <section class="panel panel--shows">
        <h2 class="panel-title">Shows</h2>
        <div v-if="showsLoading" class="empty">Loading…</div>
        <div v-else class="scroll-list">
          <ShowCard
            v-for="show in (shows.length ? shows : [DEMO_SHOW])"
            :key="show.show_id"
            :show="show"
            :disabled="!show.duration_ms"
            @play="show.duration_ms ? startPlay(show.show_id) : null"
          />
        </div>
      </section>

      <!-- Right column: Brightness + Volume -->
      <section class="panel panel--right">
        <div class="panel panel--control">
          <h2 class="panel-title">Brightness</h2>
          <BrightnessSlider
            v-model="brightnessScale"
            @commit="setBrightness"
          />
        </div>

        <div class="panel panel--control panel--volume">
          <h2 class="panel-title">Volume</h2>
          <VolumeSlider
            v-model="volume"
            :muted="muted"
            @commit="setVolume"
            @toggleMute="toggleMute"
          />
        </div>
      </section>
    </main>

    <!-- Playback bar -->
    <PlaybackBar
      :state="state"
      :show="show"
      :position-ms="positionMs"
      :duration-ms="durationMs"
      :progress="progress"
      :is-playing="isPlaying"
      :is-paused="isPaused"
      :is-active="isActive"
      @pause="pause"
      @stop="stop"
    />

    <!-- Playback HUD overlay (auto-hides after 3s) -->
    <Transition name="hud-fade">
      <div v-if="isActive && hudVisible" class="hud">
        <div class="hud-inner">
          <div class="hud-show">{{ show?.name || show?.show_id }}</div>
          <div v-if="durationMs" class="hud-progress-row">
            <span class="hud-time">{{ formatMs(positionMs) }}</span>
            <div class="hud-bar"><div class="hud-fill" :style="{ width: (progress * 100) + '%' }"></div></div>
            <span class="hud-time">{{ formatMs(durationMs) }}</span>
          </div>
          <div class="hud-btns">
            <button class="hud-btn" @click="pause">{{ isPlaying ? '⏸ Pause' : '▶ Resume' }}</button>
            <button class="hud-btn hud-btn--stop" @click="stop">&#9632; Stop</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { watch } from 'vue'
import StatusIndicator from './components/StatusIndicator.vue'
import ShowCard from './components/ShowCard.vue'
import BrightnessSlider from './components/BrightnessSlider.vue'
import VolumeSlider from './components/VolumeSlider.vue'
import PlaybackBar from './components/PlaybackBar.vue'
import { usePlayback } from './composables/usePlayback.js'
import { useShows } from './composables/useShows.js'
import { useVolume } from './composables/useVolume.js'
import { useKeyboard } from './composables/useKeyboard.js'

const { state, show, positionMs, durationMs, brightnessScale, progress, isPlaying, isPaused, isActive, play, pause, stop, setBrightness } = usePlayback()
const { shows, loading: showsLoading, DEMO_SHOW } = useShows()
const { volume, muted, setVolume, toggleMute } = useVolume()

// HUD auto-hide
import { ref } from 'vue'
const hudVisible = ref(false)
let hudTimer = null

function showHud() {
  hudVisible.value = true
  resetHudTimer()
}

function resetHudTimer() {
  hudVisible.value = true
  clearTimeout(hudTimer)
  hudTimer = setTimeout(() => { hudVisible.value = false }, 3000)
}

watch(isActive, (v) => { if (v) showHud(); else hudVisible.value = false })

if (typeof window !== 'undefined') {
  window.addEventListener('mousemove', () => { if (isActive.value) resetHudTimer() })
}

async function startPlay(show_id) {
  await play(show_id)
  showHud()
}

function formatMs(ms) {
  const s = Math.floor((ms || 0) / 1000)
  const m = Math.floor(s / 60)
  const h = Math.floor(m / 60)
  if (h > 0) return `${h}:${String(m % 60).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`
  return `${m}:${String(s % 60).padStart(2,'0')}`
}

// Keyboard shortcuts (active when Chromium has focus)
useKeyboard({
  onSpace: () => pause(),
  onEscape: () => stop(),
  onBrightnessUp: () => {
    const v = Math.min(1.0, Math.round((brightnessScale.value + 0.1) * 10) / 10)
    brightnessScale.value = v
    setBrightness(v)
  },
  onBrightnessDown: () => {
    const v = Math.max(0.0, Math.round((brightnessScale.value - 0.1) * 10) / 10)
    brightnessScale.value = v
    setBrightness(v)
  },
})
</script>

<style>
.kiosk-root {
  display: flex;
  flex-direction: column;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #0a0a0f;
  color: #e0e0e0;
}

/* ── Header ── */
.kiosk-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  height: 60px;
  background: #0d0d18;
  border-bottom: 1px solid #1a1a2e;
  flex-shrink: 0;
}
.brand { display: flex; align-items: center; gap: 10px; }
.brand-icon { font-size: 1.4rem; color: #5b7fff; }
.brand-name { font-size: 1.4rem; font-weight: 800; letter-spacing: 0.12em; color: #e8e8ff; }

/* ── Main layout ── */
.kiosk-main {
  display: flex;
  flex: 1;
  min-height: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  min-height: 0;
}
.panel--shows {
  flex: 1.4;
  border-right: 1px solid #1a1a2e;
}
.panel--right {
  flex: 1;
  padding: 0;
  gap: 0;
}
.panel--control {
  padding: 24px 24px;
  border-bottom: 1px solid #1a1a2e;
  flex-shrink: 0;
}
.panel--volume {
  border-bottom: none;
}

.panel-title {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #555;
  margin-bottom: 14px;
}

.scroll-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 0;
  padding-right: 4px;
}
.scroll-list::-webkit-scrollbar { width: 4px; }
.scroll-list::-webkit-scrollbar-thumb { background: #2a2a3a; border-radius: 2px; }

.empty { color: #444; font-size: 0.9rem; padding: 8px 0; }

/* ── HUD overlay ── */
.hud {
  position: fixed;
  bottom: 72px;
  right: 24px;
  z-index: 1000;
}
.hud-inner {
  background: rgba(10, 10, 20, 0.88);
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  padding: 16px 20px;
  backdrop-filter: blur(8px);
  min-width: 280px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hud-show { font-size: 0.95rem; font-weight: 600; color: #e0e0f0; }
.hud-progress-row { display: flex; align-items: center; gap: 8px; }
.hud-bar { flex: 1; height: 3px; background: #2a2a3a; border-radius: 2px; overflow: hidden; }
.hud-fill { height: 100%; background: #5b7fff; transition: width 0.5s linear; }
.hud-time { font-size: 0.75rem; color: #666; font-variant-numeric: tabular-nums; }
.hud-btns { display: flex; gap: 8px; }
.hud-btn {
  background: #1a1a2e;
  border: 1px solid #2a2a3a;
  border-radius: 6px;
  color: #e0e0f0;
  font-size: 0.85rem;
  padding: 6px 14px;
  cursor: pointer;
  transition: background 0.15s;
  flex: 1;
}
.hud-btn:hover { background: #252540; }
.hud-btn--stop { color: #ef4444; }

.hud-fade-enter-active, .hud-fade-leave-active { transition: opacity 0.3s; }
.hud-fade-enter-from, .hud-fade-leave-to { opacity: 0; }
</style>
