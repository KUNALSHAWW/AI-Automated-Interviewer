import { Resampler, VadSegmenter, encodeWav } from './vad.js'

// Raw capture happens in an AudioWorklet (audio thread); VAD + resampling run on the main thread.
const WORKLET_SRC = `
class Tap extends AudioWorkletProcessor {
  constructor() { super(); this.buf = []; this.n = 0 }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (ch) {
      this.buf.push(new Float32Array(ch)); this.n += ch.length
      if (this.n >= 2048) {
        const out = new Float32Array(this.n); let o = 0
        for (const b of this.buf) { out.set(b, o); o += b.length }
        this.port.postMessage(out, [out.buffer]); this.buf = []; this.n = 0
      }
    }
    return true
  }
}
registerProcessor('navai-tap', Tap)
`

export async function startMic({ onSegment, onSpeechStart, onLevel }) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  // native sample rate on purpose: Firefox cannot connect a MediaStream to a 16 kHz AudioContext
  const ctx = new (window.AudioContext || window.webkitAudioContext)()
  const url = URL.createObjectURL(new Blob([WORKLET_SRC], { type: 'application/javascript' }))
  await ctx.audioWorklet.addModule(url)
  URL.revokeObjectURL(url)
  const source = ctx.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(ctx, 'navai-tap')
  const silent = ctx.createGain()
  silent.gain.value = 0
  source.connect(node)
  node.connect(silent).connect(ctx.destination) // some browsers only pull nodes that reach the destination

  const resampler = new Resampler(ctx.sampleRate, 16000)
  const vad = new VadSegmenter()
  let muted = false

  const handle = (events) => {
    for (const e of events) {
      if (e.type === 'start') onSpeechStart?.()
      else if (e.type === 'level') onLevel?.(e.rms)
      else if (e.type === 'end') onSegment(encodeWav(e.samples, 16000), e.durationMs)
    }
  }
  node.port.onmessage = (ev) => handle(vad.push(resampler.process(ev.data), muted))

  return {
    setMuted(m) { muted = m },
    stop() {
      handle(vad.flush())
      stream.getTracks().forEach((t) => t.stop())
      node.disconnect()
      ctx.close().catch(() => {})
    },
  }
}
