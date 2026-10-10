// The browser speaks the interviewer's words (no server TTS, no extra API, no audio over the socket).
// Playback start/end are reported back to the server so it knows when the AI is really talking.
let current = null

export const ttsAvailable = () => typeof window !== 'undefined' && 'speechSynthesis' in window

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices()
  const short = lang.slice(0, 2).toLowerCase()
  const pool = voices.filter((v) => v.lang.toLowerCase().startsWith(short))
  return pool.find((v) => /natural|online|neural/i.test(v.name)) || pool.find((v) => /google/i.test(v.name)) || pool[0] || null
}

export function speak(text, lang, { onStart, onEnd } = {}) {
  if (!ttsAvailable()) {
    onStart?.()
    setTimeout(() => onEnd?.(), Math.min(8000, 800 + text.length * 55))
    return
  }
  cancel(false)
  const u = new SpeechSynthesisUtterance(text)
  u.lang = lang
  const v = pickVoice(lang)
  if (v) u.voice = v
  u.rate = 1.0
  u.onstart = () => onStart?.()
  u.onend = () => { if (current === u) current = null; onEnd?.() }
  u.onerror = () => { if (current === u) current = null; onEnd?.() }
  current = u
  window.speechSynthesis.speak(u)
}

export function cancel(notify = true) {
  if (!ttsAvailable()) return
  const had = current
  current = null
  window.speechSynthesis.cancel()
  if (had && notify) had.onend?.()
}
