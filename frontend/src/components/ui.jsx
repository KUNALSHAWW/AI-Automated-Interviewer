export const BAND_STYLE = {
  Strong: 'bg-green-500/20 text-green-300 border-green-500/40',
  Proficient: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  Developing: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  Emerging: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  'Not enough evidence': 'bg-gray-500/20 text-gray-300 border-gray-500/40',
}

export function Band({ band, className = '' }) {
  return (
    <span className={`inline-block px-3 py-1 rounded-full border text-sm font-semibold ${BAND_STYLE[band] || BAND_STYLE['Not enough evidence']} ${className}`}>
      {band}
    </span>
  )
}

export function ScoreBar({ value, max = 4 }) {
  if (value === null || value === undefined) {
    return <div className="text-xs text-white/40 italic">not observed</div>
  }
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const color = value >= 3 ? 'bg-green-400' : value >= 2 ? 'bg-blue-400' : value >= 1 ? 'bg-yellow-400' : 'bg-orange-400'
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 rounded-full bg-white/10 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-semibold tabular-nums w-8 text-right">{value.toFixed(1)}</span>
    </div>
  )
}

export function mmss(sec) {
  const s = Math.max(0, Math.round(sec || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function Notice({ tone = 'warn', children }) {
  const cls = {
    warn: 'bg-yellow-500/10 border-yellow-500/30 text-yellow-200',
    error: 'bg-red-500/10 border-red-500/30 text-red-200',
    info: 'bg-blue-500/10 border-blue-500/30 text-blue-200',
  }[tone]
  return <div className={`rounded-xl border px-4 py-3 text-sm ${cls}`}>{children}</div>
}
