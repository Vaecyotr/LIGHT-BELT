<template>
  <section v-if="enabled" class="audio-controls">
    <form v-if="enrollNeeded" @submit.prevent="enroll">
      <label>登记此控制屏 <input v-model="code" type="password" autocomplete="off" required></label>
      <button>登记</button>
    </form>
    <template v-else-if="state">
      <p v-if="state.preferences?.recovery_error" role="alert">部分控制设置已恢复。有效的灯光意图和静音设置已保留：{{ state.preferences.recovery_error }}</p>
      <p v-if="state.preferences?.persistence_error" role="alert">控制设置未能保存：{{ state.preferences.persistence_error }}</p>
      <p v-else-if="state.preferences?.saved === false" role="status">控制设置尚未保存</p>
      <p><b>扬声器</b> {{ speakerLabel }}</p>
      <small v-if="phone">手机音乐音量请在手机上调整。</small>
      <p><b>灯光来源</b> {{ sourceLabel }}</p>
      <button v-for="(label, mode) in modes" :key="mode" :disabled="busy || !fresh"
        :aria-pressed="state.analysis.mode === mode" @click="act('PUT','/analysis',{mode})">{{ label }}</button>
      <p><b>灯光</b> {{ intents[state.lighting.intent] }} · {{ lightStatus }}</p>
      <small v-if="state.lighting.intent === 'off'">关灯设置会在播放节目时保留。</small>
      <button v-if="state.lighting.intent !== 'follow'" :disabled="busy || !fresh"
        @click="lighting('follow')">恢复随播放</button>
      <button v-if="state.lighting.intent !== 'music'" :disabled="busy || !fresh" @click="lighting('music')">独立音乐灯效</button>
      <button v-if="state.lighting.intent !== 'off'" :disabled="busy || !fresh" @click="lighting('off')">关闭灯光</button>
      <button v-if="state.lighting.brightness === 0" :disabled="!fresh" @click="$emit('brightness')">亮度为 0 · 调整亮度</button>
      <details>
        <summary>蓝牙设备 · 已连接 {{ bt.connected_count || 0 }}/2<span v-if="bt.pending_count"> · 操作中 {{ bt.pending_count }}</span></summary>
        <p v-if="!bt.available">蓝牙适配器不可用</p>
        <fieldset :disabled="!bt.available || busy || !fresh">
          <button @click="act('POST','/bluetooth/scan')">搜索附近设备</button>
          <button :disabled="(bt.connected_count || 0) + (bt.pending_count || 0) >= 2" @click="act('POST','/bluetooth/add')">添加设备</button>
          <button v-if="bt.adding || bt.pairing_window_open || bt.pairable" @click="act('DELETE','/bluetooth/add')">结束添加</button>
          <article v-for="d in bt.devices" :key="d.id">
            <b>{{ d.name || d.id }}</b>
            <small>{{ d.paired ? '已配对' : '附近设备' }} · {{ d.connected ? '已连接' : '未连接' }}
              {{ phone && state.speaker.device === d.id ? ' · 扬声器路由已确认' : d.activity === 'transmitting' ? ' · 正在传输，等待播放权' : '' }}</small>
            <button v-if="!d.paired" :disabled="(bt.connected_count || 0) + (bt.pending_count || 0) >= 2" @click="device(d,'pair')">配对</button>
            <button v-if="d.paired && !d.connected" :disabled="(bt.connected_count || 0) + (bt.pending_count || 0) >= 2" @click="device(d,'connect')">连接</button>
            <template v-if="d.connected">
              <button @click="act('PUT','/speaker',{device:d.id})">选为播放者</button>
              <button @click="device(d,'disconnect')">断开</button>
            </template>
            <button v-if="d.paired" @click="forget(d)">忘记</button>
          </article>
          <button @click="act('PUT','/speaker',{device:null})">恢复自动分配播放权</button>
        </fieldset>
        <p v-for="(operation, id) in bt.operations || {}" :key="id" role="status">
          {{ deviceName(operation.device_id || operation.device) }} · {{ operationLabel(operation, operation.device_id || operation.device) }}
          {{ operation.reason || operation.error || '' }}
          <button v-if="['pending','running'].includes(operation.state)" :disabled="busy || !fresh"
            @click="act('POST','/bluetooth/pair/cancel',{operation_id:id})">取消配对</button>
        </p>
      </details>
      <div v-for="challenge in visibleChallenges" :key="challenge.id" role="alert">
        <strong>{{ deviceName(challenge.device_id) }} 请求配对</strong>
        <p>{{ challenge.value || '' }}</p>
        <input v-if="challengeInputRequired(challenge)" v-model="pins[challenge.id]" :inputmode="challenge.kind === 'passkey' ? 'numeric' : 'text'" autocomplete="off" placeholder="输入手机上的配对码">
        <template v-if="!challenge.display_only">
          <button :disabled="busy || !fresh || answering.has(challenge.id) || (challengeInputRequired(challenge) && !pins[challenge.id])" @click="answer(challenge,true)">确认</button>
          <button :disabled="busy || !fresh || answering.has(challenge.id)" @click="answer(challenge,false)">拒绝</button>
        </template>
      </div>
    </template>
    <p v-if="offline" role="alert">连接已中断，正在刷新设备状态。</p>
    <p v-if="state && !fresh" role="alert">设备状态已过期，正在重新核对；暂时不能操作或确认配对。</p>
    <p v-if="message" role="status">{{ message }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { control } from '../api.js'
import { challengeInputRequired, describeOperation, isControlSnapshotFresh, lightDescription, speakerDescription } from './audioControlState.js'
const emit = defineEmits(['available','brightness'])
const enabled = ref(false), enrollNeeded = ref(false), state = ref(null), capturedAt = ref(null), now = ref(Date.now())
const busy = ref(false), offline = ref(false), code = ref(''), pins = ref({}), message = ref('')
const answering = ref(new Set())
const modes = {auto:'设备音频（自动跟随）',mic:'环境麦克风'}
const intents = {follow:'随播放', music:'独立音乐', manual:'手动灯效', off:'保持关灯'}
const operationLabel = (operation, id) => describeOperation(operation,
  bt.value.devices?.find(device => device.id === id) || {})
const bt = computed(() => state.value?.bluetooth || {})
const phone = computed(() => state.value?.speaker.kind === 'phone')
const fresh = computed(() => !offline.value && isControlSnapshotFresh(capturedAt.value, now.value))
const visibleChallenges = computed(() => fresh.value ? bt.value.challenges || [] : [])
const deviceName = id => bt.value.devices?.find(d => d.id === id)?.name || id
const speakerLabel = computed(() => speakerDescription({
  ...state.value.speaker,
  name: deviceName(state.value.speaker.waiting_for || state.value.speaker.device),
  user_muted: state.value.video.user_muted,
}))
const sourceLabel = computed(() => {
  const a = state.value.analysis
  if (a.quality === 'stale' || a.phase === 'fault') return '输入异常，等待恢复'
  if (['warming','unavailable'].includes(a.quality) || !a.effective) return '等待输入'
  if (a.silent) return a.effective === 'wled' ? '环境安静' : '设备音频安静'
  return {phone_pcm:'手机数字音乐',program_pcm:'节目音轨',file:'节目音轨',wled:'环境麦克风'}[a.effective] || '等待输入'
})
const lightStatus = computed(() => lightDescription(state.value.lighting))
let timer, clockTimer, closed = false, reading = false, refreshAgain = false
let commandGeneration = 0
async function refresh() {
  if (closed) return
  if (reading) { refreshAgain = true; return }
  reading = true
  const generation = commandGeneration
  const started = Date.now()
  try {
    const r = await fetch('/control/state', {cache:'no-store'})
    const result = await r.json()
    if (closed || generation !== commandGeneration) {
      refreshAgain = !closed
      return
    }
    if (result.error?.code === 'CONTROL_DISABLED') { emit('available',false); return }
    enabled.value = true
    emit('available',true)
    enrollNeeded.value = r.status === 401
    offline.value = !result.ok && !enrollNeeded.value
    if (result.ok) {
      state.value = result.data
      capturedAt.value = started
      now.value = Date.now()
      offline.value = false
      for (const id of Object.keys(pins.value)) {
        if (!(result.data.bluetooth?.challenges || []).some(challenge => challenge.id === id)) {
          delete pins.value[id]
          answering.value.delete(id)
        }
      }
    } else if (enrollNeeded.value) { state.value = null; capturedAt.value = null }
  } catch { offline.value = true } finally {
    reading = false
    if (refreshAgain) { refreshAgain = false; queueMicrotask(refresh) }
    else if (!closed && (enabled.value || offline.value)) {
      clearTimeout(timer)
      timer = setTimeout(refresh,offline.value ? 4000 : 1500)
    }
  }
}
async function act(method,path,body) {
  if (busy.value) return
  busy.value = true
  commandGeneration++
  try {
    const result = await control(method,path,body)
    commandGeneration++
    const pendingDeviceAction = path.startsWith('/bluetooth/') || path === '/speaker'
    message.value = result.ok ? (pendingDeviceAction ? '操作已提交，等待设备状态确认。' : '') : result.error?.message || '操作失败'
    if (result.ok && result.data?.bluetooth) {
      state.value = result.data
      capturedAt.value = Date.now()
      now.value = capturedAt.value
      offline.value = false
      await refresh()
    } else await refresh()
    return result.ok
  } finally { busy.value = false }
}
async function enroll() {
  if (await act('POST','/enroll',{code:code.value})) location.reload()
  code.value = ''
}
const lighting = intent => act('PUT','/lighting',{intent,if_intent:state.value.lighting.intent_token})
const device = (d,action) => act('POST','/bluetooth/devices/'+encodeURIComponent(d.id)+'/'+action)
function forget(d) {
  if (window.confirm('忘记 '+deviceName(d.id)+'？这会断开设备并移除配对。'))
    act('DELETE','/bluetooth/devices/'+encodeURIComponent(d.id))
}
function answer(c,accept) {
  if (!fresh.value || answering.value.has(c.id)) return
  answering.value.add(c.id)
  act('POST','/bluetooth/answer',{challenge:c.id,device:c.device_id,accept,value:pins.value[c.id] || null})
    .then(ok => { if (ok) delete pins.value[c.id] })
    .finally(() => answering.value.delete(c.id))
}
onMounted(() => {
  refresh()
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
  document.addEventListener('visibilitychange', refresh)
})
onUnmounted(() => {
  closed = true
  clearTimeout(timer)
  clearInterval(clockTimer)
  document.removeEventListener('visibilitychange',refresh)
})
</script>

<style scoped>
.audio-controls {overflow-y:auto; padding: 0 20px; min-height:0}
button,summary {min-height:42px; padding:8px; margin:3px; cursor:pointer}
button[aria-pressed=true] {outline:2px solid #7ddbc1}
small {display:block} fieldset {border:0; padding:0} article {padding:8px 0}
</style>
