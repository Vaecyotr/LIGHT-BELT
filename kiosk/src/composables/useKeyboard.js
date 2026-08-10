import { onMounted, onUnmounted } from 'vue'

export function useKeyboard({ onSpace, onEscape, onBrightnessUp, onBrightnessDown }) {
  function handler(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
    switch (e.code) {
      case 'Space':
        e.preventDefault()
        onSpace?.()
        break
      case 'Escape':
        e.preventDefault()
        onEscape?.()
        break
      case 'ArrowUp':
        e.preventDefault()
        onBrightnessUp?.()
        break
      case 'ArrowDown':
        e.preventDefault()
        onBrightnessDown?.()
        break
    }
  }

  onMounted(() => window.addEventListener('keydown', handler))
  onUnmounted(() => window.removeEventListener('keydown', handler))
}
