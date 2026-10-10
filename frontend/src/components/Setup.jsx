import { useEffect, useState } from 'react'
import { createSession, health, rubrics as fetchRubrics } from '../lib/api.js'
import { rememberSession } from '../lib/history.js'
import { Notice } from './ui.jsx'

const LANGS = [
  ['en', 'English'],
  ['hi', 'Hindi (हिन्दी)'],
  ['auto', 'Auto-detect (English / Hinglish)'],
]

export default function Setup({ onStart }) {
  const [info, setInfo] = useState(null)
  const [rubrics, setRubrics] = useState([])
  const [repoUrl, setRepoUrl] = useState('')
  const [rubricId, setRubricId] = useState('project_viva')
  const [language, setLanguage] = useState('en')
  const [title, setTitle] = useState('')
  const [accessCode, setAccessCode] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    health().then(setInfo).catch((e) => setError(`Backend unreachable: ${e.message}`))
    fetchRubrics().then((r) => setRubrics(r.rubrics)).catch(() => {})
  }, [])

  const rubric = rubrics.find((r) => r.id === rubricId)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const s = await createSession({
        repo_url: repoUrl.trim() || null, rubric_id: rubricId, language, title, access_code: accessCode, consent,
      })
      rememberSession({ id: s.id, token: s.token, created: Date.now(), title: title || s.repo?.repo || 'Untitled',
        repo: s.repo?.repo || null, rubric: s.rubric.title })
      onStart(s)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="max-w-3xl mx-auto space-y-6">
      <div className="text-center">
        <h2 className="text-3xl font-bold">Defend your project</h2>
        <p className="text-blue-200 mt-2">
          Nova reads your repository first, then listens and watches while you present. Every score is tied to a quote you actually said.
        </p>
      </div>

      {info && !info.ready && <Notice tone="error">{info.problems.join(' ')}</Notice>}
      {info?.ready && info.problems.length > 0 && <Notice tone="warn">{info.problems.join(' ')}</Notice>}

      <div className="glass-card p-6 space-y-5">
        <label className="block">
          <span className="text-sm font-medium">GitHub repository (public, optional but recommended)</span>
          <input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/you/your-project"
            className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2 outline-none focus:border-blue-400" />
          <span className="text-xs text-white/50">With a repository Nova can check what you say and show against what you built.</span>
        </label>

        <div className="grid md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-sm font-medium">Rubric</span>
            <select value={rubricId} onChange={(e) => setRubricId(e.target.value)}
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2">
              {rubrics.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium">Language</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2">
              {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
        </div>

        {rubric && (
          <details className="text-sm text-blue-200">
            <summary className="cursor-pointer">What is scored ({rubric.dimensions.length} dimensions, 0 to 4)</summary>
            <ul className="mt-2 space-y-1">
              {rubric.dimensions.map((d) => (
                <li key={d.id}><b>{d.label}</b> <span className="text-white/50">({Math.round(d.weight * 100)}%)</span>
                  <div className="text-white/50">4 = {d.anchors['4']}</div></li>
              ))}
            </ul>
          </details>
        )}

        <div className="grid md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-sm font-medium">Title (optional)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80}
              className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2" />
          </label>
          {info?.access_code_required && (
            <label className="block">
              <span className="text-sm font-medium">Access code</span>
              <input value={accessCode} onChange={(e) => setAccessCode(e.target.value)} type="password"
                className="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2" />
            </label>
          )}
        </div>

        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1" />
          <span>
            I understand that my voice, shared screen and transcript are sent to AI providers (speech-to-text and language
            models) to run this interview, are stored on the server for up to {info?.retention_days ?? 30} days, and that I can delete them at any time.
            The result is advisory feedback, not a grading decision.
          </span>
        </label>

        {error && <Notice tone="error">{error}</Notice>}

        <button disabled={busy || !consent || (info && !info.ready)}
          className="w-full py-3 rounded-xl font-semibold bg-gradient-to-r from-blue-500 to-indigo-600 disabled:opacity-40">
          {busy ? 'Reading your repository...' : 'Continue'}
        </button>
      </div>
    </form>
  )
}
