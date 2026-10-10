import { useState } from 'react'
import History from './components/History.jsx'
import HowItWorks from './components/HowItWorks.jsx'
import Interview from './components/Interview.jsx'
import ReportView from './components/ReportView.jsx'
import Setup from './components/Setup.jsx'
import { updateSession } from './lib/history.js'

const GITHUB_REPO = 'https://github.com/KUNALSHAWW/AI-Automated-Interviewer'

function NavTab({ active, onClick, children }) {
  return (
    <button onClick={onClick}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${active ? 'bg-white/20' : 'text-white/70 hover:bg-white/10'}`}>
      {children}
    </button>
  )
}

export default function App() {
  const [page, setPage] = useState('setup') // setup | interview | report | history | how
  const [session, setSession] = useState(null)
  const [report, setReport] = useState(null)

  const startNew = () => { setSession(null); setReport(null); setPage('setup') }

  function handleReport(r) {
    setReport(r)
    if (session) updateSession(session.id, { band: r.overall.band, score: r.overall.score })
    setPage('report')
  }

  return (
    <div className="min-h-screen premium-gradient text-white">
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-white/5 border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          <button onClick={startNew} className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center font-bold">N</span>
            <span className="text-left">
              <span className="block font-bold leading-tight">NavAI Viva</span>
              <span className="block text-xs text-blue-300 leading-tight">repo-grounded project defense</span>
            </span>
          </button>
          <nav className="flex gap-1">
            <NavTab active={page === 'setup' || page === 'interview'} onClick={startNew}>Interview</NavTab>
            <NavTab active={page === 'history'} onClick={() => setPage('history')}>History</NavTab>
            <NavTab active={page === 'how'} onClick={() => setPage('how')}>How it works</NavTab>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {page === 'setup' && <Setup onStart={(s) => { setSession(s); setPage('interview') }} />}
        {page === 'interview' && session && (
          <Interview session={session} onReport={handleReport} onAbort={startNew} />
        )}
        {page === 'report' && report && session && <ReportView report={report} session={session} onNew={startNew} />}
        {page === 'history' && (
          <History onOpen={(s, r) => { setSession(s); setReport(r); setPage('report') }} />
        )}
        {page === 'how' && <HowItWorks />}
      </main>

      <footer className="border-t border-white/10 mt-12 py-6 text-sm text-white/50">
        <div className="max-w-7xl mx-auto px-6 flex flex-wrap justify-between gap-2">
          <span>Advisory, AI-assisted feedback. Not a grading or hiring decision.</span>
          <a href={GITHUB_REPO} target="_blank" rel="noopener noreferrer" className="hover:text-white">Source on GitHub</a>
        </div>
      </footer>
    </div>
  )
}
