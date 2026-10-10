import { wsUrl } from './api.js'

const KIND_AUDIO = 1
const KIND_FRAME = 2

// One interview = one authenticated WebSocket. The first message carries the secret session token.
export class InterviewSocket {
  constructor(path, token, onMessage, onClose) {
    this.path = path
    this.token = token
    this.onMessage = onMessage
    this.onClose = onClose
    this.ws = null
    this.pingTimer = null
  }

  connect() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl(this.path))
      ws.binaryType = 'arraybuffer'
      this.ws = ws
      let ready = false
      ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token: this.token }))
      ws.onmessage = (ev) => {
        if (typeof ev.data !== 'string') return
        const msg = JSON.parse(ev.data)
        if (!ready) {
          if (msg.type === 'ready') { ready = true; this._startPing(); resolve(msg) }
          else if (msg.type === 'error') reject(new Error(msg.message))
          return
        }
        this.onMessage(msg)
      }
      ws.onerror = () => { if (!ready) reject(new Error('Could not reach the interview server.')) }
      ws.onclose = () => { clearInterval(this.pingTimer); this.onClose?.() }
    })
  }

  _startPing() {
    // keeps proxies (Render, Cloudflare) from idling the socket while the presenter is silent
    this.pingTimer = setInterval(() => this.json({ type: 'ping' }), 20000)
  }

  get open() { return this.ws && this.ws.readyState === WebSocket.OPEN }

  json(obj) { if (this.open) this.ws.send(JSON.stringify(obj)) }

  _binary(kind, arrayBuffer) {
    if (!this.open) return
    const out = new Uint8Array(arrayBuffer.byteLength + 1)
    out[0] = kind
    out.set(new Uint8Array(arrayBuffer), 1)
    this.ws.send(out)
  }

  sendAudio(wav) { this._binary(KIND_AUDIO, wav) }
  sendFrame(jpeg) { this._binary(KIND_FRAME, jpeg) }

  close() {
    clearInterval(this.pingTimer)
    try { this.ws?.close() } catch { /* already closed */ }
  }
}
