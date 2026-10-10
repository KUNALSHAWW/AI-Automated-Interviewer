import { useState } from 'react'
import { getSession } from '../lib/api.js'
import { forgetSession, listHistory } from '../lib/history.js'
import { Notice } from './ui.jsx'

export default function History({ onOpen }) {
  const [items, setItems] = useState(listHistory())
  const [error, setError] = useState('')

  async function open(it) {
    setError('')
    try {
      const s = await getSession(it.id, it.token)
      if (!s.report) {
        setError(`This session has no report (status: ${s.status}).`)
        return
      }
      onOpen({ id: it.id, token: it.token }, s.report)
    } catch (e) {
      if (e.status === 401) {
        forgetSession(it.id)
        setItems(listHistory())
        setError('That session no longer exists on the server (deleted, expired, or the free-tier server restarted).')
      } else {
        setError(e.message)
      }
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <h2 className="text-3xl font-bold">History</h2>
      <p className="text-sm text-blue-200">Sessions started from this browser. The secret token for each stays in this browser only.</p>
      {error && <Notice tone="warn">{error}</Notice>}
      {items.length === 0 && <div className="glass-card p-8 text-center text-white/60">No interviews yet.</div>}
      {items.map((it) => (
        <div key={it.id} className="glass-card p-4 flex items-center justify-between gap-3">
          <div>
            <div className="font-semibold">{it.title}</div>
            <div className="text-xs text-white/50">{new Date(it.created).toLocaleString()} · {it.rubric}{it.band ? ` · ${it.band}` : ''}</div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => open(it)} className="px-3 py-1.5 rounded-lg bg-blue-500 text-sm">Open</button>
            <button onClick={() => { forgetSession(it.id); setItems(listHistory()) }}
              className="px-3 py-1.5 rounded-lg bg-white/10 text-sm" title="Remove from this list (does not delete on the server)">Forget</button>
          </div>
        </div>
      ))}
    </div>
  )
}
