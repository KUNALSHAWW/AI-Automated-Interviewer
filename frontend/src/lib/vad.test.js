import test from 'node:test'
import assert from 'node:assert/strict'
import { Resampler, VadSegmenter, encodeWav } from './vad.js'

const SR = 16000
const tone = (ms, amp = 0.2) => {
  const n = Math.round((SR * ms) / 1000)
  return Float32Array.from({ length: n }, (_, i) => amp * Math.sin((2 * Math.PI * 220 * i) / SR))
}
const silence = (ms, amp = 0.0005) => Float32Array.from({ length: Math.round((SR * ms) / 1000) }, () => (Math.random() - 0.5) * amp)
const concat = (...a) => { const o = new Float32Array(a.reduce((n, x) => n + x.length, 0)); let p = 0; for (const x of a) { o.set(x, p); p += x.length } return o }
const run = (v, audio, muted = false) => v.push(audio, muted).filter((e) => e.type !== 'level')

test('one utterance followed by a pause yields exactly one segment', () => {
  const v = new VadSegmenter()
  const ev = run(v, concat(silence(500), tone(2000), silence(1500)))
  assert.deepEqual(ev.map((e) => e.type), ['start', 'end'])
  const end = ev[1]
  assert.ok(end.durationMs > 1900 && end.durationMs < 3000, `duration ${end.durationMs}`)
})

test('a short pause inside a sentence does not split it (thinking time is not end of turn)', () => {
  const v = new VadSegmenter()
  const ev = run(v, concat(silence(300), tone(1500), silence(700), tone(1500), silence(1500)))
  assert.equal(ev.filter((e) => e.type === 'end').length, 1)
})

test('a 1.5 s pause between two utterances splits them', () => {
  const v = new VadSegmenter()
  const ev = run(v, concat(tone(1200), silence(1600), tone(1200), silence(1600)))
  assert.equal(ev.filter((e) => e.type === 'end').length, 2)
})

test('clicks and noise bursts shorter than 400 ms are discarded', () => {
  const v = new VadSegmenter()
  const ev = run(v, concat(silence(500), tone(120), silence(1500)))
  assert.equal(ev.filter((e) => e.type === 'end').length, 0)
})

test('muted audio (AI speaking, no barge-in) is never segmented', () => {
  const v = new VadSegmenter()
  const ev = run(v, concat(tone(3000), silence(1500)), true)
  assert.equal(ev.length, 0)
})

test('very long speech is cut at the maximum segment length', () => {
  const v = new VadSegmenter({ maxSegmentMs: 5000 })
  const ev = run(v, tone(12000))
  assert.ok(ev.filter((e) => e.type === 'end').length >= 2)
})

test('adaptive noise floor: constant background hum is not treated as speech', () => {
  const v = new VadSegmenter()
  const hum = Float32Array.from({ length: SR * 4 }, (_, i) => 0.006 * Math.sin((2 * Math.PI * 50 * i) / SR))
  assert.equal(run(v, hum).length, 0)
})

test('resampler 48 kHz -> 16 kHz keeps length and level', () => {
  const r = new Resampler(48000, 16000)
  const input = Float32Array.from({ length: 4800 }, () => 0.5)
  const out = r.process(input)
  assert.equal(out.length, 1600)
  assert.ok(Math.abs(out[100] - 0.5) < 1e-6)
})

test('wav encoder writes a valid 44-byte header', () => {
  const buf = encodeWav(new Float32Array(16000), 16000)
  const v = new DataView(buf)
  assert.equal(String.fromCharCode(v.getUint8(0), v.getUint8(1), v.getUint8(2), v.getUint8(3)), 'RIFF')
  assert.equal(v.getUint32(24, true), 16000)
  assert.equal(buf.byteLength, 44 + 32000)
})
