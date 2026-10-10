// Voice-activity segmentation. Pure JS, no browser APIs, unit-tested with node --test.
//
// Why this exists: the old client streamed fixed 3 s windows, so utterances were cut mid-word and
// "natural pause" detection did not exist. Here the *browser* finds where a spoken utterance starts and
// ends (energy VAD with an adaptive noise floor), so the server transcribes whole utterances and knows
// exactly when the presenter paused.

export class Resampler {
  // Box-filter decimation (good enough for speech, no aliasing hiss). Keeps state across chunks.
  constructor(inRate, outRate = 16000) {
    this.ratio = inRate / outRate
    this.acc = 0
    this.n = 0
    this.phase = 0
  }

  process(input) {
    if (this.ratio === 1) return input
    const out = []
    if (this.ratio < 1) {
      // upsampling (rare): repeat samples
      const rep = Math.round(1 / this.ratio)
      for (const x of input) for (let i = 0; i < rep; i++) out.push(x)
      return Float32Array.from(out)
    }
    for (let i = 0; i < input.length; i++) {
      this.acc += input[i]
      this.n += 1
      this.phase += 1
      if (this.phase >= this.ratio) {
        out.push(this.acc / this.n)
        this.acc = 0
        this.n = 0
        this.phase -= this.ratio
      }
    }
    return Float32Array.from(out)
  }
}

export function encodeWav(samples, sampleRate = 16000) {
  const buf = new ArrayBuffer(44 + samples.length * 2)
  const v = new DataView(buf)
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true)
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, samples.length * 2, true)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return buf
}

export class VadSegmenter {
  constructor(opts = {}) {
    this.sr = opts.sampleRate ?? 16000
    this.chunkMs = opts.chunkMs ?? 50
    this.startChunks = opts.startChunks ?? 2           // 100 ms of speech to open a segment
    this.hangoverMs = opts.hangoverMs ?? 1100          // silence that closes a segment
    this.minSpeechMs = opts.minSpeechMs ?? 400
    this.maxSegmentMs = opts.maxSegmentMs ?? 40000
    this.preRollMs = opts.preRollMs ?? 300
    this.minThreshold = opts.minThreshold ?? 0.012
    this.noiseMultiplier = opts.noiseMultiplier ?? 3
    this.frameLen = Math.round((this.sr * this.chunkMs) / 1000)
    this.noise = 0.004
    this.pending = new Float32Array(0)
    this.reset()
  }

  reset() {
    this.speaking = false
    this.speechRun = 0
    this.silenceMs = 0
    this.seg = []
    this.preRoll = []
  }

  /** Feed any number of 16 kHz samples; returns events: {type:'start'|'end'|'level', ...} */
  push(samples, muted = false) {
    const merged = new Float32Array(this.pending.length + samples.length)
    merged.set(this.pending, 0)
    merged.set(samples, this.pending.length)
    const events = []
    let o = 0
    while (merged.length - o >= this.frameLen) {
      this._frame(merged.subarray(o, o + this.frameLen), muted, events)
      o += this.frameLen
    }
    this.pending = merged.slice(o)
    return events
  }

  _frame(frame, muted, events) {
    let sum = 0
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i]
    const rms = Math.sqrt(sum / frame.length)
    events.push({ type: 'level', rms: muted ? 0 : rms, speaking: this.speaking })
    if (muted) {            // the AI is talking and barge-in is off: drop audio so it never hears itself
      if (this.speaking || this.speechRun) this.reset()
      return
    }
    const thr = Math.max(this.minThreshold, this.noise * this.noiseMultiplier)
    const isSpeech = rms > thr
    if (!this.speaking) {
      if (!isSpeech) this.noise = Math.max(0.0005, 0.95 * this.noise + 0.05 * rms)
      this.preRoll.push(frame.slice())
      const keep = Math.ceil(this.preRollMs / this.chunkMs)
      while (this.preRoll.length > keep) this.preRoll.shift()
      this.speechRun = isSpeech ? this.speechRun + 1 : 0
      if (this.speechRun >= this.startChunks) {
        this.speaking = true
        this.seg = this.preRoll
        this.preRoll = []
        this.silenceMs = 0
        events.push({ type: 'start' })
      }
      return
    }
    this.seg.push(frame.slice())
    this.silenceMs = isSpeech ? 0 : this.silenceMs + this.chunkMs
    if (this.silenceMs >= this.hangoverMs || this.seg.length * this.chunkMs >= this.maxSegmentMs) {
      this._finish(events)
    }
  }

  /** Close the open segment (also called when the user presses stop). */
  flush() {
    const events = []
    if (this.speaking) this._finish(events)
    return events
  }

  _finish(events) {
    const trimTail = Math.max(0, Math.floor((this.silenceMs - 300) / this.chunkMs))
    const frames = trimTail > 0 ? this.seg.slice(0, this.seg.length - trimTail) : this.seg
    const speechMs = (frames.length * this.chunkMs) - Math.min(this.silenceMs, 300)
    const total = frames.reduce((n, f) => n + f.length, 0)
    const out = new Float32Array(total)
    let o = 0
    for (const f of frames) { out.set(f, o); o += f.length }
    this.reset()
    if (speechMs >= this.minSpeechMs) {
      events.push({ type: 'end', samples: out, durationMs: Math.round((total / this.sr) * 1000) })
    }
  }
}
