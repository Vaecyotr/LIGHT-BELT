import test from 'node:test'
import assert from 'node:assert/strict'
import {
  challengeInputRequired,
  describeOperation,
  isControlSnapshotFresh,
  lightDescription,
  speakerDescription,
} from '../src/components/audioControlState.js'

test('off intent, submitted request and confirmed device state are shown separately', () => {
  assert.equal(lightDescription({intent:'off', off_status:'requested'}), '等待设备确认')
  assert.equal(lightDescription({intent:'off', off_status:'unknown'}), '设备状态未知')
  assert.equal(lightDescription({intent:'off', off_status:'unknown', off_submitted:true}), '已发送关灯请求，设备状态未知')
  assert.equal(lightDescription({intent:'off', off_status:'confirmed'}), '设备已确认关闭')
})

test('routed speaker is reported only after route readback', () => {
  assert.equal(speakerDescription({status:'waiting', device:'b', name:'B', kind:'program'}), '节目原声 · 等待 B 开始播放')
  assert.equal(speakerDescription({status:'routed', device:'b', kind:'phone', name:'B'}), '手机 B 正在播放')
  assert.equal(speakerDescription({status:'fault', device:'b'}), '音响路由异常')
})

test('accepted operations remain pending until device facts confirm them', () => {
  assert.equal(describeOperation({state:'pending'}), '等待配对结果')
  assert.equal(describeOperation({state:'succeeded'}, {paired:false}), '配对请求已受理，等待设备确认')
  assert.equal(describeOperation({state:'succeeded'}, {paired:true}), '已配对')
  assert.equal(describeOperation({state:'failed',reason:'timeout'}), '配对失败：timeout')
})

test('PIN/passkey prompts require input and preserve text such as leading zeroes', () => {
  assert.equal(challengeInputRequired({kind:'pin'}), true)
  assert.equal(challengeInputRequired({kind:'passkey'}), true)
  assert.equal(challengeInputRequired({kind:'confirm'}), false)
})

test('snapshot freshness expires and future timestamps are rejected', () => {
  assert.equal(isControlSnapshotFresh(1000, 5999), true)
  assert.equal(isControlSnapshotFresh(1000, 6001), false)
  assert.equal(isControlSnapshotFresh(5000, 4999), false)
  assert.equal(isControlSnapshotFresh(null, 1000), false)
})
