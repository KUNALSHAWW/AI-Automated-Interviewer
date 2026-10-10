import { useMemo, useState } from 'react'
import { deleteSession, pdfUrl, thumbUrl } from '../lib/api.js'
import { forgetSession } from '../lib/history.js'
import { Band, Notice, ScoreBar, mmss } from './ui.jsx'

function Chip({ id, quotes }) {
  const q = quotes[id]
  return (
    <a href={`#ev-${id}`} title={q ? `"${q.quote}"` : id}
      className="inline-block px-1.5 py-0.5 mr-1 rounded bg-white/10 text-xs text-blue-300 hover:bg-white/20">{id}</a>
  )
}

export default function ReportView({ report, session, onNew }) {
  const [deleted, setDeleted] = useState(false)
  const [open, setOpen] = useState({})
  const quotes = useMemo(() => {
    const m = {}
    for (const d of report.dimensions) for (const e of d.evidence) m[e.id] = { ...e, dim: d.label }
    return m
  }, [report])

  const ov = report.overall
  const process = report.process

  async function remove() {
    if (!window.confirm('Delete this session and its report from the server? This cannot be undone.')) return
    try {
      await deleteSession(session.id, session.token)
      forgetSession(session.id)
      setDeleted(true)
    } catch (e) {
      window.alert(`Could not delete: ${e.message}`)
    }
  }

  if (deleted) {
    return (
      <div className="max-w-xl mx-auto glass-card p-8 text-center space-y-4">
        <p>Session deleted from the server.</p>
        <button onClick={onNew} className="px-4 py-2 rounded-lg bg-blue-500">Start another</button>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="glass-card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold">Your defense report</h2>
            <p className="text-sm text-blue-200">{report.rubric.title}{report.repo ? ` · ${report.repo.repo}` : ''}</p>
          </div>
          <div className="text-right">
            <Band band={ov.band} />
            <div className="text-4xl font-bold mt-2 tabular-nums">
              {ov.score === null ? 'n/a' : ov.score.toFixed(1)}<span className="text-lg text-white/50"> / 4</span>
            </div>
            <div className="text-xs text-white/50">rubric coverage {Math.round(ov.coverage * 100)}%</div>
          </div>
        </div>
        <p className="mt-4 text-xs text-white/50">{report.disclaimer}</p>
      </div>

      {report.review.needs_human_review && (
        <Notice tone="warn">
          <b>Human review recommended.</b>
          <ul className="list-disc ml-5 mt-1">{report.review.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </Notice>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {report.dimensions.map((d) => (
          <div key={d.id} className="glass-card p-4">
            <div className="flex justify-between items-baseline mb-2">
              <h3 className="font-semibold">{d.label}</h3>
              <span className="text-xs text-white/50">{Math.round(d.weight * 100)}% weight · {d.n_obs} quote{d.n_obs === 1 ? '' : 's'}</span>
            </div>
            <ScoreBar value={d.final} />
            {d.council_scores?.length > 0 && (
              <div className="text-xs text-white/50 mt-1">graders: {d.council_scores.join(' / ')}{d.spread >= 1.5 ? ' (disagree)' : ''}</div>
            )}
            {d.evidence.length > 0 && (
              <>
                <button onClick={() => setOpen((o) => ({ ...o, [d.id]: !o[d.id] }))} className="text-xs text-blue-300 mt-2 underline">
                  {open[d.id] ? 'Hide' : 'Show'} evidence
                </button>
                {open[d.id] && (
                  <ul className="mt-2 space-y-2">
                    {d.evidence.map((e) => (
                      <li key={e.id} id={`ev-${e.id}`} className="text-sm border-l-2 border-blue-400/60 pl-3">
                        <span className="italic">"{e.quote}"</span>
                        <div className="text-xs text-white/50">{e.id} · {mmss(e.t)} · {e.source} · score {e.score}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        ))}
      </div>

      {(report.strengths.length > 0 || report.growth.length > 0) && (
        <div className="grid md:grid-cols-2 gap-4">
          <div className="glass-card p-5">
            <h3 className="font-semibold text-green-300 mb-2">What went well</h3>
            <ul className="space-y-2 text-sm">
              {report.strengths.map((p, i) => (
                <li key={i}>{p.text} <span className="ml-1">{p.evidence.map((id) => <Chip key={id} id={id} quotes={quotes} />)}</span></li>
              ))}
            </ul>
          </div>
          <div className="glass-card p-5">
            <h3 className="font-semibold text-yellow-300 mb-2">What to work on</h3>
            <ul className="space-y-2 text-sm">
              {report.growth.map((p, i) => (
                <li key={i}>{p.text} <span className="ml-1">{p.evidence.map((id) => <Chip key={id} id={id} quotes={quotes} />)}</span></li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {process.narrative_status === 'unavailable' && (
        <Notice tone="info">The written feedback is unavailable because no grading model responded. The scores above are computed directly from the verified quotes.</Notice>
      )}

      {report.next_steps.length > 0 && (
        <div className="glass-card p-5">
          <h3 className="font-semibold mb-2">Next steps</h3>
          <ol className="list-decimal ml-5 text-sm space-y-1">{report.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
        </div>
      )}

      {report.repo && (
        <div className="glass-card p-5">
          <h3 className="font-semibold mb-2">What was said vs what is in the repository</h3>
          <div className="grid md:grid-cols-3 gap-3 text-sm">
            <div><div className="text-green-300 font-medium">Backed by the repo</div>{report.claims.supported?.join(', ') || 'none'}</div>
            <div><div className="text-yellow-300 font-medium">Not found in repository</div>{report.claims.not_found?.join(', ') || 'none'}</div>
            <div><div className="text-yellow-300 font-medium">Figures without support</div>{report.claims.unverified_metrics?.join(', ') || 'none'}</div>
          </div>
          <p className="text-xs text-white/40 mt-3">Automated checks are hints: Nova reads the manifests, file tree, README and a few key files, not every line.</p>
        </div>
      )}

      {report.screens.some((s) => s.thumb) && (
        <div className="glass-card p-5">
          <h3 className="font-semibold mb-3">Screens shown</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {report.screens.filter((s) => s.thumb).slice(0, 8).map((s) => (
              <figure key={s.id} className="text-xs">
                <img src={thumbUrl(session.id, s.thumb, session.token)} alt={s.title || 'screen'} className="rounded-lg border border-white/10" />
                <figcaption className="mt-1 text-white/60">{s.title || 'Screen'} · {mmss(s.t)}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      <div className="glass-card p-5 text-xs text-white/60 space-y-1">
        <div>
          {process.utterances} utterances · {process.questions} questions · {process.screens} screens · {process.observations} verified
          observations · {process.dropped_unverified} model claims discarded (quote not found) · duration {mmss(process.duration_s)}
        </div>
        <div>Graders: {process.council.join(', ') || 'none'}{process.council_agreement !== null ? ` · agreement ${Math.round(process.council_agreement * 100)}%` : ''}</div>
        <div>
          Usage: {report.usage.llm_calls} model calls, {report.usage.audio_seconds}s of audio, estimated speech-to-text cost
          ${report.usage.stt_cost_estimate_usd}
        </div>
      </div>

      <div className="flex flex-wrap gap-3 justify-end">
        <a href={pdfUrl(session.id, session.token)} target="_blank" rel="noopener noreferrer"
          className="px-4 py-2 rounded-lg bg-blue-500 hover:bg-blue-600">Download PDF</a>
        <button onClick={remove} className="px-4 py-2 rounded-lg bg-white/10 hover:bg-red-500/30">Delete from server</button>
        <button onClick={onNew} className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20">New interview</button>
      </div>
    </div>
  )
}
