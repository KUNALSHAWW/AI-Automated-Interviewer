import { useCallback, useEffect, useRef, useState } from 'react'
import { startMic } from '../lib/audio.js'
import { startScreen } from '../lib/screen.js'
import { InterviewSocket } from '../lib/socket.js'
import { speak, cancel as cancelSpeech, ttsAvailable } from '../lib/tts.js'
import { Notice, mmss } from './ui.jsx'

const STATUS = {
  idle: ['Ready', 'bg-gray-500/20 text-gray-300'],
  listening: ['Listening', 'bg-red-500/20 text-red-300'],
  transcribing: ['Transcribing', 'bg-yellow-500/20 text-yellow-300'],
  thinking: ['Thinking', 'bg-yellow-500/20 text-yellow-300 animate-pulse'],
  speaking: ['Nova is speaking', 'bg-blue-500/20 text-blue-300'],
}

export default function Interview({ session, onReport, onAbort }) {
  const [phase, setPhase] = useState('ready') // ready | connecting | live | ending
  const [status, setStatus] = useState('idle')
  const [feed, setFeed] = useState([])        // conversation: {role, text}
  const [evidence, setEvidence] = useState([])
  const [flags, setFlags] = useState([])
  const [claims, setClaims] = useState({ supported: [], not_found: [], unverified_metrics: [] })
  const [screens, setScreens] = useState([])
  const [warnings, setWarnings] = useState({})
  const [error, setError] = useState('')
  const [screenLost, setScreenLost] = useState(false)
  const [bargeIn, setBargeIn] = useState(false)
  const [typed, setTyped] = useState('')
  const [level, setLevel] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [noScreen, setNoScreen] = useState(false)

  const sockRef = useRef(null)
  const micRef = useRef(null)
  const screenRef = useRef(null)
  const speakingRef = useRef(false)
  const bargeRef = useRef(false)
  const langRef = useRef('en-US')
  const startedAt = useRef(0)

  bargeRef.current = bargeIn

  const applyMute = useCallback(() => {
    micRef.current?.setMuted(speakingRef.current && !bargeRef.current)
  }, [])

  useEffect(() => { applyMute() }, [bargeIn, applyMute])

  useEffect(() => {
    if (phase !== 'live') return undefined
    const t = setInterval(() => setElapsed((Date.now() - startedAt.current) / 1000), 1000)
    return () => clearInterval(t)
  }, [phase])

  const teardownMedia = useCallback(() => {
    micRef.current?.stop()
    screenRef.current?.stop()
    micRef.current = null
    screenRef.current = null
    cancelSpeech(false)
  }, [])

  useEffect(() => () => { teardownMedia(); sockRef.current?.close() }, [teardownMedia])

  const onMessage = useCallback((m) => {
    switch (m.type) {
      case 'status':
        if (m.state !== 'listening' || !speakingRef.current) setStatus(m.state)
        break
      case 'transcript':
        setFeed((f) => [...f, { role: 'you', text: m.text, at: m.at }])
        break
      case 'ai_say':
        setFeed((f) => [...f, { role: 'ai', text: m.text, kind: m.kind, at: m.t }])
        langRef.current = m.lang || 'en-US'
        speak(m.text, langRef.current, {
          onStart: () => { speakingRef.current = true; applyMute(); sockRef.current?.json({ type: 'playback', state: 'started' }); setStatus('speaking') },
          onEnd: () => { speakingRef.current = false; applyMute(); sockRef.current?.json({ type: 'playback', state: 'ended' }); setStatus('listening') },
        })
        break
      case 'evidence':
        setEvidence((e) => [...e, m])
        break
      case 'flag':
        setFlags((f) => [...f, m])
        break
      case 'claims':
        setClaims({ supported: m.supported, not_found: m.not_found, unverified_metrics: m.unverified_metrics })
        break
      case 'screen':
        setScreens((s) => [...s, m])
        break
      case 'warning':
        setWarnings((w) => ({ ...w, [m.code]: m.message }))
        break
      case 'screen_lost':
        setScreenLost(true)
        break
      case 'screen_restored':
        setScreenLost(false)
        break
      case 'ended':
        setPhase('ending')
        setStatus('idle')
        teardownMedia()
        break
      case 'report':
        sockRef.current?.close()
        onReport(m.report)
        break
      case 'report_error':
        setError(m.message)
        break
      case 'error':
        setError(m.message)
        break
      default:
        break
    }
  }, [applyMute, onReport, teardownMedia])

  async function begin() {
    setError('')
    setPhase('connecting')
    try {
      // Permissions first, inside the click, while the browser still grants user activation.
      let screen = null
      try {
        screen = await startScreen({
          onFrame: (buf) => sockRef.current?.sendFrame(buf),
          onEnded: () => { sockRef.current?.json({ type: 'screen_state', active: false }) },
        })
      } catch {
        setNoScreen(true) // the interview still works; slides just are not analysed
      }
      screenRef.current = screen
      const mic = await startMic({
        onSegment: (wav) => sockRef.current?.sendAudio(wav),
        onLevel: (rms) => setLevel(Math.min(1, rms * 8)),
        onSpeechStart: () => {
          if (speakingRef.current && bargeRef.current) {
            cancelSpeech(true)
            sockRef.current?.json({ type: 'interrupt' })
          }
        },
      })
      micRef.current = mic
      const sock = new InterviewSocket(session.ws_path, session.token, onMessage, () => {
        // The server keeps going after a dropped socket and stores the session, so nothing is lost.
        setPhase((p) => {
          if (p === 'live' || p === 'ending') {
            setError('The connection closed. The session is saved on the server; if the interview had ended, '
              + 'open its report from History in a minute.')
            return 'closed'
          }
          return p
        })
        micRef.current?.stop()
        screenRef.current?.stop()
        micRef.current = null
        screenRef.current = null
      })
      sockRef.current = sock
      await sock.connect()
      startedAt.current = Date.now()
      sock.json({ type: 'start' })
      setPhase('live')
      setStatus('thinking')
    } catch (e) {
      teardownMedia()
      sockRef.current?.close()
      setError(e.message || 'Could not start')
      setPhase('ready')
    }
  }

  async function reshare() {
    try {
      screenRef.current?.stop()
      screenRef.current = await startScreen({
        onFrame: (buf) => sockRef.current?.sendFrame(buf),
        onEnded: () => sockRef.current?.json({ type: 'screen_state', active: false }),
      })
      sockRef.current?.json({ type: 'screen_state', active: true })
    } catch (e) {
      setError(`Could not share the screen: ${e.message}`)
    }
  }

  function stop() {
    setPhase('ending')
    sockRef.current?.json({ type: 'stop' })
  }

  function sendTyped(e) {
    e.preventDefault()
    if (!typed.trim()) return
    sockRef.current?.json({ type: 'text', text: typed.trim() })
    setTyped('')
  }

  const [label, cls] = STATUS[status] || STATUS.idle
  const repo = session.repo
  const flagsAll = [
    ...flags.map((f) => ({ key: `f${f.t}${f.detail}`, text: f.detail, at: f.t })),
    ...claims.not_found.map((t) => ({ key: `c${t}`, text: `"${t}" was mentioned or shown, but no trace of it was found in the repository.`, at: null })),
    ...claims.unverified_metrics.map((t) => ({ key: `m${t}`, text: `The figure ${t} is not supported by the README or your screen.`, at: null })),
  ]

  return (
    <div className="grid lg:grid-cols-5 gap-6">
      <div className="lg:col-span-3 space-y-4">
        <div className="glass-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm text-blue-300">{repo ? repo.repo : 'No repository'} · {session.rubric.title}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${cls}`}>{label}</span>
                {phase === 'live' && <span className="text-sm text-white/60 tabular-nums">{mmss(elapsed)}</span>}
              </div>
            </div>
            {phase === 'ready' && (
              <button onClick={begin} className="px-6 py-3 rounded-xl font-semibold bg-gradient-to-r from-blue-500 to-indigo-600">
                Start (allow mic and screen)
              </button>
            )}
            {phase === 'connecting' && <span className="text-blue-200">Connecting...</span>}
            {phase === 'live' && (
              <button onClick={stop} className="px-6 py-3 rounded-xl font-semibold bg-gradient-to-r from-red-500 to-rose-600">
                End interview
              </button>
            )}
            {phase === 'ending' && <span className="text-blue-200 animate-pulse">Preparing your feedback (this can take up to a minute)...</span>}
          </div>

          {phase === 'live' && (
            <div className="mt-4 flex items-center gap-4">
              <div className="h-2 flex-1 rounded-full bg-white/10 overflow-hidden" title="microphone level">
                <div className="h-full bg-red-400 transition-all" style={{ width: `${Math.round(level * 100)}%` }} />
              </div>
              <label className="text-xs text-white/70 flex items-center gap-2" title="Let me interrupt Nova. Use headphones, otherwise Nova may hear itself.">
                <input type="checkbox" checked={bargeIn} onChange={(e) => setBargeIn(e.target.checked)} />
                Headphones mode (interrupt Nova)
              </label>
            </div>
          )}
          {!ttsAvailable() && <div className="mt-3"><Notice tone="warn">This browser cannot speak; read Nova's questions in the conversation.</Notice></div>}
        </div>

        {error && <Notice tone="error">{error}</Notice>}
        {noScreen && <Notice tone="warn">Screen sharing was not allowed. The interview continues, but slides and code on screen will not be analysed.</Notice>}
        {screenLost && (
          <Notice tone="warn">
            <div className="flex items-center justify-between gap-3">
              <span>Screen share lost. Share again or the interview will end.</span>
              <button onClick={reshare} className="px-3 py-1 rounded-lg bg-green-500 text-white">Reshare</button>
            </div>
          </Notice>
        )}
        {Object.entries(warnings).map(([k, v]) => <Notice key={k} tone="warn">{v}</Notice>)}

        <div className="glass-card p-5">
          <h3 className="font-semibold mb-3">Conversation</h3>
          <div className="space-y-2 max-h-[46vh] overflow-y-auto pr-1" aria-live="polite">
            {feed.length === 0 && <p className="text-white/40 text-sm">Nova's questions and your words appear here.</p>}
            {feed.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'ai' ? 'justify-start' : 'justify-end'}`}>
                <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${m.role === 'ai' ? 'bg-blue-500/20' : 'bg-white/15'}`}>
                  <div className="text-xs opacity-60 mb-0.5">{m.role === 'ai' ? 'Nova' : 'You'}</div>
                  {m.text}
                </div>
              </div>
            ))}
          </div>
          {phase === 'live' && (
            <form onSubmit={sendTyped} className="mt-3 flex gap-2">
              <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Or type your answer"
                className="flex-1 rounded-lg bg-black/30 border border-white/10 px-3 py-2 text-sm" />
              <button className="px-4 rounded-lg bg-white/10 text-sm">Send</button>
            </form>
          )}
        </div>
      </div>

      <div className="lg:col-span-2 space-y-4">
        <div className="glass-card p-5">
          <h3 className="font-semibold">Evidence so far</h3>
          <p className="text-xs text-white/50 mb-3">Only quotes the server verified in your transcript are kept.</p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {evidence.length === 0 && <p className="text-white/40 text-sm">Nothing scored yet.</p>}
            {evidence.map((e) => (
              <div key={e.id} className="rounded-lg bg-black/20 border border-white/10 p-2 text-sm">
                <div className="flex justify-between text-xs text-blue-300">
                  <span>{e.label}</span><span>{e.score}/4 · {mmss(e.at)}</span>
                </div>
                <div className="italic text-white/80">"{e.quote}"</div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-card p-5">
          <h3 className="font-semibold mb-2">Said vs shown vs built</h3>
          {repo ? (
            <>
              <div className="text-xs text-white/50 mb-2">Repository stack: {repo.techs.slice(0, 10).join(', ') || 'none detected'}</div>
              {claims.supported.length > 0 && <div className="text-sm text-green-300 mb-1">Backed by the repo: {claims.supported.join(', ')}</div>}
              {flagsAll.length === 0 ? <p className="text-white/40 text-sm">No mismatches so far.</p> : (
                <ul className="space-y-1 text-sm text-yellow-200">{flagsAll.map((f) => <li key={f.key}>• {f.text}</li>)}</ul>
              )}
            </>
          ) : <p className="text-white/40 text-sm">No repository linked, so claims cannot be cross-checked.</p>}
        </div>

        <div className="glass-card p-5">
          <h3 className="font-semibold mb-2">Screens seen ({screens.length})</h3>
          <ul className="space-y-1 text-sm max-h-40 overflow-y-auto">
            {screens.length === 0 && <li className="text-white/40">None yet.</li>}
            {screens.map((s) => (
              <li key={s.id} className="text-white/80">
                <b>{s.title || 'Screen'}</b> <span className="text-white/50">{s.analysis === 'ok' ? s.summary : `(${s.analysis})`}</span>
              </li>
            ))}
          </ul>
        </div>

        {onAbort && phase === 'ready' && (
          <button onClick={onAbort} className="text-sm text-white/50 underline">Back</button>
        )}
      </div>
    </div>
  )
}
