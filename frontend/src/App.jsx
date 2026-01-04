/**
 * NavAI Real-Time Interview App - Premium Edition
 * Beautiful Zoom-inspired UI with advanced features
 */

import { useState, useRef, useCallback, useEffect } from 'react'

// ============================================
// Constants & Configuration
// ============================================
const GITHUB_REPO = "https://github.com/KUNALSHAWW/AI-Automated-Interviewer"
const BACKEND_URL = "http://localhost:8000"
const WS_URL = "ws://localhost:8000/ws/interview"

// ============================================
// Icons Components
// ============================================
const GitHubIcon = () => (
  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
    <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
  </svg>
)

const MicIcon = ({ active }) => (
  <svg className={`w-6 h-6 ${active ? 'text-red-500' : 'text-gray-400'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
  </svg>
)

// ============================================
// AI Avatar Component with Speaking Animation
// ============================================
const AIAvatar = ({ isSpeaking, name = "Nova" }) => {
  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        {/* Outer glow rings when speaking */}
        {isSpeaking && (
          <>
            <div className="absolute inset-0 rounded-full bg-blue-500/30 animate-ping" style={{ animationDuration: '1.5s' }} />
            <div className="absolute -inset-2 rounded-full bg-blue-400/20 animate-pulse" />
            <div className="absolute -inset-4 rounded-full bg-blue-300/10 animate-pulse" style={{ animationDelay: '0.2s' }} />
          </>
        )}
        
        {/* Avatar circle */}
        <div className={`relative w-20 h-20 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-xl ${isSpeaking ? 'ring-4 ring-blue-400/50' : ''}`}>
          {/* AI Face */}
          <div className="text-white">
            <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          
          {/* Speaking indicator */}
          {isSpeaking && (
            <div className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 flex gap-0.5">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="w-1.5 bg-blue-400 rounded-full animate-bounce"
                  style={{ 
                    height: `${8 + Math.random() * 8}px`,
                    animationDelay: `${i * 0.15}s`,
                    animationDuration: '0.6s'
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      <span className="mt-2 text-sm font-medium text-white/90">{name}</span>
      <span className="text-xs text-blue-300">AI Interviewer</span>
    </div>
  )
}

// ============================================
// Navigation Tab Button
// ============================================
const NavTab = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
      active 
        ? 'bg-white/20 text-white shadow-lg' 
        : 'text-white/70 hover:text-white hover:bg-white/10'
    }`}
  >
    <span>{icon}</span>
    <span>{label}</span>
  </button>
)

// ============================================
// Instructions Page Component
// ============================================
const InstructionsPage = () => {
  const tips = [
    { icon: "🎯", title: "Be Specific", desc: "Give detailed explanations with examples. Mention technologies, frameworks, and design decisions." },
    { icon: "📊", title: "Show Your Work", desc: "Walk through your code, diagrams, and architecture. Visual aids boost your score significantly." },
    { icon: "🗣️", title: "Speak Clearly", desc: "Maintain a steady pace. The AI listens for natural pauses before asking questions." },
    { icon: "💡", title: "Explain Why", desc: "Don't just show what you built. Explain WHY you made each decision." },
    { icon: "🔄", title: "Handle Questions Well", desc: "When asked a question, pause and think. It's okay to say 'Let me explain that better.'" },
    { icon: "⚡", title: "Keep It Flowing", desc: "The AI waits for slide changes or pauses. Keep presenting until you're ready for questions." },
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-bold text-white mb-3">How to Ace Your Interview</h2>
        <p className="text-blue-200">Follow these tips to maximize your score</p>
      </div>

      {/* Steps */}
      <div className="glass-card p-6 mb-8">
        <h3 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
          <span className="text-2xl">📋</span> Interview Steps
        </h3>
        <div className="grid md:grid-cols-4 gap-4">
          {[
            { step: 1, title: "Start Interview", desc: "Click the start button to begin" },
            { step: 2, title: "Share Screen", desc: "Share your presentation or code" },
            { step: 3, title: "Present", desc: "Explain your project naturally" },
            { step: 4, title: "Get Report", desc: "Receive detailed feedback" },
          ].map((item) => (
            <div key={item.step} className="bg-white/5 rounded-xl p-4 text-center">
              <div className="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center mx-auto mb-3 text-white font-bold">
                {item.step}
              </div>
              <h4 className="font-semibold text-white mb-1">{item.title}</h4>
              <p className="text-sm text-blue-200">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Tips Grid */}
      <div className="grid md:grid-cols-2 gap-4">
        {tips.map((tip, i) => (
          <div key={i} className="glass-card p-5 hover:bg-white/10 transition-colors">
            <div className="flex items-start gap-4">
              <span className="text-3xl">{tip.icon}</span>
              <div>
                <h4 className="font-semibold text-white mb-1">{tip.title}</h4>
                <p className="text-sm text-blue-200">{tip.desc}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Scoring Info */}
      <div className="glass-card p-6 mt-8">
        <h3 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
          <span className="text-2xl">📊</span> Scoring Categories
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {["Technical Depth", "Clarity", "Originality", "Visual Aids", "Problem Solving", "Code Quality", "Communication", "Implementation", "Formatting", "Diagrams"].map((cat) => (
            <div key={cat} className="bg-gradient-to-r from-blue-500/20 to-indigo-500/20 rounded-lg px-3 py-2 text-center text-sm text-white">
              {cat}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ============================================
// FAQ Page Component
// ============================================
const FAQPage = () => {
  const [openIndex, setOpenIndex] = useState(null)
  
  const faqs = [
    {
      category: "General",
      questions: [
        { q: "How does the AI interviewer work?", a: "NavAI uses advanced AI models to analyze your screen content and voice in real-time. It understands what you're presenting, evaluates your explanations, and asks relevant follow-up questions just like a human interviewer would." },
        { q: "How long should my presentation be?", a: "We recommend 5-15 minutes for optimal results. This gives enough time to demonstrate your project thoroughly while keeping the AI engaged." },
        { q: "Can I redo my interview?", a: "Absolutely! You can take as many interviews as you want. Each session is saved separately so you can track your improvement over time." },
      ]
    },
    {
      category: "Technical",
      questions: [
        { q: "What browsers are supported?", a: "NavAI works best on Chrome, Edge, and Firefox. Safari has limited WebRTC support which may cause issues with screen sharing." },
        { q: "Why isn't my microphone working?", a: "Make sure you've granted microphone permissions in your browser. Check that no other application is using the microphone. Try refreshing the page." },
        { q: "The AI keeps interrupting me. Why?", a: "The AI waits for natural pauses and slide changes. If it's interrupting, try speaking more continuously and changing slides after finishing your explanation." },
        { q: "What's the minimum internet speed required?", a: "We recommend at least 5 Mbps upload speed for smooth screen sharing and audio transmission." },
      ]
    },
    {
      category: "Scoring",
      questions: [
        { q: "How is my score calculated?", a: "Your score is based on 10 categories: Technical Depth, Clarity, Originality, Implementation Understanding, Presentation Formatting, Visual Aids, Diagrams, Code Quality, Problem Solving, and Communication. Each is weighted equally." },
        { q: "What score do I need to pass?", a: "Generally, 60+ is considered passing, 70+ is good, and 80+ is excellent. The AI also provides a PASS/NEEDS_IMPROVEMENT/FAIL recommendation." },
        { q: "Can I see my detailed feedback?", a: "Yes! After each interview, you receive a comprehensive report with scores, strengths, weaknesses, and specific suggestions for improvement." },
      ]
    }
  ]

  return (
    <div className="max-w-4xl mx-auto">
      <div className="text-center mb-10">
        <h2 className="text-3xl font-bold text-white mb-3">Frequently Asked Questions</h2>
        <p className="text-blue-200">Everything you need to know about NavAI</p>
      </div>

      {faqs.map((section, sectionIndex) => (
        <div key={section.category} className="mb-8">
          <h3 className="text-lg font-semibold text-blue-300 mb-4 flex items-center gap-2">
            <span>{section.category === "General" ? "📌" : section.category === "Technical" ? "⚙️" : "📊"}</span>
            {section.category}
          </h3>
          <div className="space-y-3">
            {section.questions.map((faq, i) => {
              const index = `${sectionIndex}-${i}`
              const isOpen = openIndex === index
              return (
                <div key={i} className="glass-card overflow-hidden">
                  <button
                    onClick={() => setOpenIndex(isOpen ? null : index)}
                    className="w-full p-4 text-left flex items-center justify-between hover:bg-white/5 transition-colors"
                  >
                    <span className="font-medium text-white">{faq.q}</span>
                    <span className={`text-blue-300 transition-transform ${isOpen ? 'rotate-180' : ''}`}>
                      ▼
                    </span>
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-4 text-blue-200 text-sm border-t border-white/10 pt-3">
                      {faq.a}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// ============================================
// History Page Component
// ============================================
const HistoryPage = ({ interviews, onRefresh }) => {
  const getScoreColor = (score) => {
    if (score >= 70) return 'text-green-400'
    if (score >= 50) return 'text-yellow-400'
    return 'text-red-400'
  }

  const getRecommendationBadge = (rec) => {
    if (!rec) return null
    const colors = {
      'PASS': 'bg-green-500/20 text-green-300 border-green-500/30',
      'NEEDS_IMPROVEMENT': 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
      'FAIL': 'bg-red-500/20 text-red-300 border-red-500/30'
    }
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs border ${colors[rec] || colors['NEEDS_IMPROVEMENT']}`}>
        {rec.replace('_', ' ')}
      </span>
    )
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-bold text-white mb-2">Interview History</h2>
          <p className="text-blue-200">Track your progress over time</p>
        </div>
        <button
          onClick={onRefresh}
          className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-colors flex items-center gap-2"
        >
          <span>🔄</span> Refresh
        </button>
      </div>

      {interviews.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <div className="text-6xl mb-4">📭</div>
          <h3 className="text-xl font-semibold text-white mb-2">No Interviews Yet</h3>
          <p className="text-blue-200">Complete your first interview to see it here</p>
        </div>
      ) : (
        <div className="space-y-4">
          {interviews.map((interview, i) => (
            <div key={i} className="glass-card p-6 hover:bg-white/10 transition-colors">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-white font-semibold">Session #{interview.session_id}</span>
                    {getRecommendationBadge(interview.summary?.recommendation)}
                  </div>
                  <p className="text-sm text-blue-300">
                    {new Date(interview.timestamp).toLocaleDateString('en-US', { 
                      weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
                      hour: '2-digit', minute: '2-digit'
                    })}
                  </p>
                </div>
                <div className={`text-4xl font-bold ${getScoreColor(interview.summary?.overall_score || 0)}`}>
                  {interview.summary?.overall_score || 0}
                  <span className="text-lg text-white/50">/100</span>
                </div>
              </div>

              {/* Stats */}
              <div className="grid grid-cols-4 gap-4 mb-4">
                {[
                  { label: "Questions", value: interview.total_questions || 0, icon: "❓" },
                  { label: "Duration", value: `${Math.round(interview.duration_minutes || 0)}m`, icon: "⏱️" },
                  { label: "Topics", value: interview.history?.length || 0, icon: "📑" },
                  { label: "Slides", value: interview.screen_contexts_count || 0, icon: "🖼️" },
                ].map((stat) => (
                  <div key={stat.label} className="bg-white/5 rounded-lg p-3 text-center">
                    <div className="text-lg">{stat.icon}</div>
                    <div className="text-xl font-bold text-white">{stat.value}</div>
                    <div className="text-xs text-blue-300">{stat.label}</div>
                  </div>
                ))}
              </div>

              {/* Summary */}
              {interview.summary?.summary && (
                <p className="text-sm text-blue-200 italic border-t border-white/10 pt-3">
                  "{interview.summary.summary}"
                </p>
              )}

              {/* Download button */}
              <div className="flex justify-end mt-4">
                <a
                  href={`${BACKEND_URL}/api/reports/${interview.session_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg text-white text-sm transition-colors flex items-center gap-2"
                >
                  📥 Download PDF
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================
// Real-Time Conversation Component
// ============================================
const ConversationPanel = ({ messages, isSpeaking }) => {
  const containerRef = useRef(null)

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div className="glass-card h-full flex flex-col">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <h3 className="font-semibold text-white flex items-center gap-2">
          <span>💬</span> Live Conversation
        </h3>
        {isSpeaking && (
          <span className="px-2 py-1 bg-blue-500/20 rounded-full text-xs text-blue-300 animate-pulse">
            AI Speaking...
          </span>
        )}
      </div>
      <div ref={containerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 ? (
          <div className="text-center text-blue-300/50 py-8">
            <div className="text-4xl mb-2">🎙️</div>
            <p>Conversation will appear here</p>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'ai' ? 'justify-start' : 'justify-end'}`}
            >
              <div className={`max-w-[85%] rounded-2xl px-4 py-2 ${
                msg.role === 'ai'
                  ? 'bg-blue-500/20 text-white rounded-tl-none'
                  : 'bg-white/20 text-white rounded-tr-none'
              }`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs opacity-70">
                    {msg.role === 'ai' ? '🤖 Nova' : '👤 You'}
                  </span>
                  <span className="text-xs opacity-50">{msg.timestamp}</span>
                  {msg.score !== undefined && (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      msg.score >= 7 ? 'bg-green-500/30 text-green-300' : 'bg-yellow-500/30 text-yellow-300'
                    }`}>
                      {msg.score}/10
                    </span>
                  )}
                </div>
                <p className="text-sm">{msg.text}</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

// ============================================
// Interview Report Modal
// ============================================
const ReportModal = ({ summary, onClose, sessionId }) => {
  if (!summary) return null

  const getScoreColor = (score) => {
    if (score >= 70) return 'text-green-400'
    if (score >= 50) return 'text-yellow-400'
    return 'text-red-400'
  }

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-hidden shadow-2xl border border-white/10">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">📊 Interview Report</h2>
              <p className="text-blue-200">Session: {sessionId}</p>
            </div>
            <button onClick={onClose} className="text-white/70 hover:text-white text-2xl">×</button>
          </div>
        </div>

        <div className="p-6 overflow-y-auto max-h-[60vh]">
          {/* Score */}
          <div className="text-center mb-8">
            <div className={`text-6xl font-bold ${getScoreColor(summary.overall_score)}`}>
              {summary.overall_score}
              <span className="text-2xl text-white/50">/100</span>
            </div>
            {summary.recommendation && (
              <span className={`inline-block mt-3 px-4 py-1.5 rounded-full text-sm font-semibold ${
                summary.recommendation === 'PASS' ? 'bg-green-500/20 text-green-300' :
                summary.recommendation === 'NEEDS_IMPROVEMENT' ? 'bg-yellow-500/20 text-yellow-300' :
                'bg-red-500/20 text-red-300'
              }`}>
                {summary.recommendation.replace('_', ' ')}
              </span>
            )}
          </div>

          {/* Category Scores */}
          {summary.category_scores && (
            <div className="grid grid-cols-5 gap-2 mb-6">
              {Object.entries(summary.category_scores).slice(0, 10).map(([key, value]) => (
                <div key={key} className="bg-white/5 rounded-lg p-2 text-center">
                  <div className={`text-lg font-bold ${getScoreColor(value)}`}>{value}</div>
                  <div className="text-xs text-blue-300 truncate">{key.replace(/_/g, ' ')}</div>
                </div>
              ))}
            </div>
          )}

          {/* Strengths & Weaknesses */}
          <div className="grid md:grid-cols-2 gap-4 mb-6">
            {summary.strengths?.length > 0 && (
              <div className="bg-green-500/10 rounded-xl p-4 border border-green-500/20">
                <h4 className="font-semibold text-green-400 mb-2">✅ Strengths</h4>
                <ul className="text-sm text-white/80 space-y-1">
                  {summary.strengths.map((s, i) => <li key={i}>• {s}</li>)}
                </ul>
              </div>
            )}
            {(summary.weaknesses?.length > 0 || summary.improvements?.length > 0) && (
              <div className="bg-yellow-500/10 rounded-xl p-4 border border-yellow-500/20">
                <h4 className="font-semibold text-yellow-400 mb-2">📈 To Improve</h4>
                <ul className="text-sm text-white/80 space-y-1">
                  {(summary.weaknesses || summary.improvements || []).map((s, i) => <li key={i}>• {s}</li>)}
                </ul>
              </div>
            )}
          </div>

          {/* Summary */}
          {summary.summary && (
            <p className="text-white/70 italic text-center border-t border-white/10 pt-4">
              "{summary.summary}"
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-colors"
          >
            Close
          </button>
          <a
            href={`${BACKEND_URL}/api/reports/${sessionId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg text-white transition-colors flex items-center gap-2"
          >
            📥 Download PDF
          </a>
        </div>
      </div>
    </div>
  )
}

// ============================================
// Main Interview View Component
// ============================================
const InterviewView = ({ 
  isActive, 
  status, 
  messages, 
  transcript, 
  interimTranscript,
  currentScore,
  onStart, 
  onStop,
  error,
  screenShareLost,
  reshareCountdown,
  onReshare
}) => {
  const isSpeaking = status === 'speaking'
  const isListening = status === 'listening'

  return (
    <div className="grid lg:grid-cols-3 gap-6 h-[calc(100vh-200px)]">
      {/* Left Panel - Main Interview Area */}
      <div className="lg:col-span-2 flex flex-col gap-6">
        {/* AI Avatar & Status */}
        <div className="glass-card p-6">
          <div className="flex items-center justify-between">
            <AIAvatar isSpeaking={isSpeaking} />
            
            <div className="flex-1 mx-8">
              {/* Status indicator */}
              <div className="flex items-center justify-center gap-4 mb-4">
                <div className={`px-4 py-2 rounded-full text-sm font-medium ${
                  status === 'listening' ? 'bg-red-500/20 text-red-300 animate-pulse' :
                  status === 'speaking' ? 'bg-blue-500/20 text-blue-300' :
                  status === 'thinking' ? 'bg-yellow-500/20 text-yellow-300 animate-pulse' :
                  'bg-gray-500/20 text-gray-300'
                }`}>
                  {status === 'listening' ? '🎤 Listening...' :
                   status === 'speaking' ? '🔊 AI Speaking' :
                   status === 'thinking' ? '🧠 Thinking...' :
                   '⏸️ Ready'}
                </div>
                {currentScore !== null && (
                  <div className="px-3 py-1 bg-white/10 rounded-full text-white">
                    Last Score: <span className="font-bold">{currentScore}/10</span>
                  </div>
                )}
              </div>
              
              {/* Control buttons */}
              {!isActive ? (
                <button
                  onClick={onStart}
                  className="w-full py-4 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl font-semibold text-lg hover:from-blue-600 hover:to-indigo-700 transition-all transform hover:scale-[1.02] shadow-lg text-white"
                >
                  🚀 Start Interview
                </button>
              ) : (
                <button
                  onClick={onStop}
                  className="w-full py-4 bg-gradient-to-r from-red-500 to-rose-600 rounded-xl font-semibold text-lg hover:from-red-600 hover:to-rose-700 transition-all shadow-lg text-white"
                >
                  ⏹️ End Interview
                </button>
              )}
            </div>

            {/* Mic indicator */}
            <div className="flex flex-col items-center">
              <div className={`w-16 h-16 rounded-full flex items-center justify-center ${
                isListening ? 'bg-red-500/20 ring-4 ring-red-500/30' : 'bg-white/10'
              }`}>
                <MicIcon active={isListening} />
              </div>
              <span className="text-xs text-blue-300 mt-2">
                {isListening ? 'Recording' : 'Mic Ready'}
              </span>
            </div>
          </div>

          {/* Error display */}
          {error && (
            <div className="mt-4 p-4 bg-red-500/20 border border-red-500/30 rounded-xl text-red-300">
              ⚠️ {error}
            </div>
          )}

          {/* Screen share lost warning */}
          {screenShareLost && isActive && (
            <div className="mt-4 p-4 bg-yellow-500/20 border border-yellow-500/30 rounded-xl">
              <div className="flex items-center justify-between mb-3">
                <span className="text-yellow-300 font-semibold">📺 Screen Share Lost</span>
                {reshareCountdown > 0 && (
                  <span className="text-yellow-400 font-mono">{reshareCountdown}s</span>
                )}
              </div>
              <button
                onClick={onReshare}
                className="w-full py-2 bg-green-500 hover:bg-green-600 rounded-lg text-white transition-colors"
              >
                🔄 Reshare Screen
              </button>
            </div>
          )}
        </div>

        {/* Live Transcript */}
        <div className="glass-card p-6 flex-1">
          <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
            <span>📝</span> Live Transcript
            {isListening && (
              <span className="flex gap-1 ml-2">
                {[...Array(3)].map((_, i) => (
                  <span key={i} className="w-1.5 h-1.5 bg-red-500 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </span>
            )}
          </h3>
          <div className="bg-black/30 rounded-xl p-4 min-h-[150px] font-mono text-sm">
            {transcript && <p className="text-green-400 mb-2">{transcript}</p>}
            {interimTranscript && (
              <p className="text-yellow-400 italic animate-pulse">🎤 {interimTranscript}</p>
            )}
            {!transcript && !interimTranscript && (
              <p className="text-blue-300/50">
                {isActive ? '🎤 Listening... Start presenting!' : 'Click "Start Interview" to begin'}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Right Panel - Conversation */}
      <div className="h-full">
        <ConversationPanel messages={messages} isSpeaking={isSpeaking} />
      </div>
    </div>
  )
}

// ============================================
// Main App Component
// ============================================
function App() {
  // Navigation state
  const [currentPage, setCurrentPage] = useState('interview')
  
  // Interview state
  const [isActive, setIsActive] = useState(false)
  const [status, setStatus] = useState('idle')
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [messages, setMessages] = useState([])
  const [currentScore, setCurrentScore] = useState(null)
  const [summary, setSummary] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const [error, setError] = useState(null)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  
  // Screen share state
  const [screenShareLost, setScreenShareLost] = useState(false)
  const [reshareCountdown, setReshareCountdown] = useState(null)
  
  // Report popup state
  const [showReportPopup, setShowReportPopup] = useState(false)
  const [showReportModal, setShowReportModal] = useState(false)
  const [generatingReport, setGeneratingReport] = useState(false)
  
  // Past interviews
  const [pastInterviews, setPastInterviews] = useState([])

  // Refs
  const wsRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const screenStreamRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioElementRef = useRef(null)
  const audioQueueRef = useRef([])
  const isPlayingRef = useRef(false)
  const canvasRef = useRef(null)
  const videoRef = useRef(null)
  const frameIntervalRef = useRef(null)

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((event) => {
    try {
      const message = JSON.parse(event.data)
      const { type, data } = message
      
      console.log('[WS] Received:', type, data)

      switch (type) {
        case 'status':
          setStatus(data.state)
          break

        case 'transcript_interim':
          setInterimTranscript(data.text)
          break

        case 'transcript_final':
          setTranscript(prev => (prev + ' ' + data.text).trim())
          setInterimTranscript('')
          setMessages(prev => [...prev, { role: 'user', text: data.text, timestamp: new Date().toLocaleTimeString() }])
          break

        case 'ai_message':
          setMessages(prev => [...prev, { role: 'ai', text: data.text, timestamp: new Date().toLocaleTimeString() }])
          break

        case 'evaluation':
          setCurrentScore(data.score)
          if (data.next_question) {
            setMessages(prev => [...prev, { 
              role: 'ai', 
              text: data.next_question,
              score: data.score,
              conflict: data.conflict_detected,
              timestamp: new Date().toLocaleTimeString()
            }])
          }
          break

        case 'audio_chunk':
          audioQueueRef.current.push(data.audio)
          if (!isPlayingRef.current) {
            playNextAudioChunk()
          }
          break

        case 'audio_end':
          break

        case 'stop_audio':
          stopAudioPlayback()
          break

        case 'screen_update':
          break

        case 'interview_complete':
          setSummary(data.summary)
          setSessionId(data.session_id)
          setIsActive(false)
          setStatus('idle')
          setScreenShareLost(false)
          setReshareCountdown(null)
          setShowReportPopup(false)
          setGeneratingReport(false)
          setShowReportModal(true)
          fetchPastInterviews()
          break

        case 'interview_stopped':
          setShowReportPopup(true)
          setSessionId(data.session_id)
          setIsActive(false)
          setStatus('idle')
          setScreenShareLost(false)
          setReshareCountdown(null)
          break

        case 'screen_share_lost':
          setScreenShareLost(true)
          setReshareCountdown(30)
          break

        case 'screen_share_restored':
          setScreenShareLost(false)
          setReshareCountdown(null)
          break

        case 'report_ready':
          console.log('[Report] PDF ready at:', data.url)
          break

        case 'error':
          setError(data.message)
          break

        default:
          break
      }
    } catch (err) {
      console.error('[WS] Parse error:', err)
    }
  }, [])

  // Fetch past interviews
  const fetchPastInterviews = useCallback(async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/interviews`)
      const data = await response.json()
      setPastInterviews(data.interviews || [])
    } catch (err) {
      console.error('[History] Failed to fetch:', err)
    }
  }, [])

  // Countdown timer
  useEffect(() => {
    if (reshareCountdown === null || reshareCountdown <= 0) return
    const timer = setTimeout(() => setReshareCountdown(prev => prev - 1), 1000)
    return () => clearTimeout(timer)
  }, [reshareCountdown])

  // Fetch past interviews on mount
  useEffect(() => {
    fetchPastInterviews()
  }, [fetchPastInterviews])

  // Audio playback
  const playNextAudioChunk = async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false
      return
    }
    isPlayingRef.current = true
    try {
      const audioBase64 = audioQueueRef.current.shift()
      if (!audioElementRef.current) {
        audioElementRef.current = new Audio()
        audioElementRef.current.onended = () => playNextAudioChunk()
        audioElementRef.current.onerror = () => playNextAudioChunk()
      }
      audioElementRef.current.src = `data:audio/mp3;base64,${audioBase64}`
      await audioElementRef.current.play()
    } catch (err) {
      isPlayingRef.current = false
      playNextAudioChunk()
    }
  }

  const stopAudioPlayback = () => {
    audioQueueRef.current = []
    isPlayingRef.current = false
    if (audioElementRef.current) {
      audioElementRef.current.pause()
      audioElementRef.current.currentTime = 0
    }
  }

  // Connect to WebSocket
  const connectWebSocket = useCallback(() => {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(WS_URL)
      ws.onopen = () => {
        setConnectionStatus('connected')
        wsRef.current = ws
        resolve(ws)
      }
      ws.onerror = () => {
        setConnectionStatus('error')
        reject(new Error('WebSocket connection failed. Is the backend running?'))
      }
      ws.onclose = () => {
        setConnectionStatus('disconnected')
        wsRef.current = null
      }
      ws.onmessage = handleWebSocketMessage
    })
  }, [handleWebSocketMessage])

  // Start screen capture
  const startScreenCapture = async () => {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: 'always', displaySurface: 'monitor' },
      audio: false
    })
    screenStreamRef.current = stream
    const video = document.createElement('video')
    video.srcObject = stream
    video.muted = true
    videoRef.current = video
    await video.play()
    const canvas = document.createElement('canvas')
    canvasRef.current = canvas
    await new Promise(resolve => setTimeout(resolve, 500))
    canvas.width = Math.min(video.videoWidth, 1280)
    canvas.height = Math.min(video.videoHeight, 720)

    frameIntervalRef.current = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
      if (!video.videoWidth) return
      try {
        const ctx = canvas.getContext('2d')
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
        const frameData = canvas.toDataURL('image/jpeg', 0.6).split(',')[1]
        wsRef.current.send(JSON.stringify({ type: 'video', data: frameData }))
      } catch (err) {}
    }, 2000)

    stream.getVideoTracks()[0].onended = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'screen_share_lost' }))
      }
      setScreenShareLost(true)
      setReshareCountdown(30)
      screenStreamRef.current = null
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current)
        frameIntervalRef.current = null
      }
    }
    return stream
  }

  // Start audio capture
  const startAudioCapture = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    })
    mediaStreamRef.current = stream
    const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 })
    const source = audioContext.createMediaStreamSource(stream)
    const processor = audioContext.createScriptProcessor(4096, 1, 1)
    
    processor.onaudioprocess = (e) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
      const inputData = e.inputBuffer.getChannelData(0)
      const pcm16 = new Int16Array(inputData.length)
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]))
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
      }
      const uint8Array = new Uint8Array(pcm16.buffer)
      let binary = ''
      for (let i = 0; i < uint8Array.length; i++) {
        binary += String.fromCharCode(uint8Array[i])
      }
      wsRef.current.send(JSON.stringify({ type: 'audio', data: btoa(binary), encoding: 'linear16', sampleRate: 16000 }))
    }
    
    source.connect(processor)
    processor.connect(audioContext.destination)
    mediaRecorderRef.current = { audioContext, processor, source }
    return stream
  }

  // Start interview
  const startInterview = async () => {
    try {
      setError(null)
      setStatus('connecting')
      setMessages([])
      setTranscript('')
      setSummary(null)
      setCurrentScore(null)
      setScreenShareLost(false)
      setReshareCountdown(null)
      setCurrentPage('interview')

      await connectWebSocket()
      await startScreenCapture()
      await startAudioCapture()

      setIsActive(true)
      setStatus('listening')
    } catch (err) {
      setError(err.message)
      setStatus('error')
      stopInterview()
    }
  }

  // Reshare screen
  const reshareScreen = async () => {
    try {
      setError(null)
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current)
        frameIntervalRef.current = null
      }
      
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: 'always', displaySurface: 'monitor' },
        audio: false
      })
      screenStreamRef.current = stream
      const video = document.createElement('video')
      video.srcObject = stream
      video.muted = true
      videoRef.current = video
      await video.play()
      const canvas = canvasRef.current || document.createElement('canvas')
      canvasRef.current = canvas
      await new Promise(resolve => setTimeout(resolve, 500))
      canvas.width = Math.min(video.videoWidth, 1280)
      canvas.height = Math.min(video.videoHeight, 720)

      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'screen_share_restored' }))
      }
      setScreenShareLost(false)
      setReshareCountdown(null)

      frameIntervalRef.current = setInterval(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
        if (!video.videoWidth) return
        try {
          const ctx = canvas.getContext('2d')
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          const frameData = canvas.toDataURL('image/jpeg', 0.6).split(',')[1]
          wsRef.current.send(JSON.stringify({ type: 'video', data: frameData }))
        } catch (err) {}
      }, 2000)

      stream.getVideoTracks()[0].onended = () => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'screen_share_lost' }))
        }
        setScreenShareLost(true)
        setReshareCountdown(30)
        screenStreamRef.current = null
        if (frameIntervalRef.current) {
          clearInterval(frameIntervalRef.current)
          frameIntervalRef.current = null
        }
      }
    } catch (err) {
      setError('Failed to reshare screen: ' + err.message)
    }
  }

  // Stop interview
  const stopInterview = useCallback(() => {
    setScreenShareLost(false)
    setReshareCountdown(null)
    
    if (mediaRecorderRef.current) {
      if (mediaRecorderRef.current.processor) {
        mediaRecorderRef.current.processor.disconnect()
        mediaRecorderRef.current.source.disconnect()
        mediaRecorderRef.current.audioContext.close()
      }
    }

    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }))
    }

    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach(track => track.stop())
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop())
    }
    if (frameIntervalRef.current) {
      clearInterval(frameIntervalRef.current)
    }
    stopAudioPlayback()
    setIsActive(false)
    setStatus('idle')
  }, [])

  // Request report
  const requestReport = useCallback(() => {
    setGeneratingReport(true)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'generate_report' }))
    }
  }, [])

  // Close without report
  const closeWithoutReport = useCallback(() => {
    setShowReportPopup(false)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close()
    }
    fetchPastInterviews()
  }, [fetchPastInterviews])

  useEffect(() => {
    return () => { stopInterview() }
  }, [stopInterview])

  return (
    <div className="min-h-screen premium-gradient text-white">
      {/* Navigation Header */}
      <header className="sticky top-0 z-40 backdrop-blur-xl bg-white/5 border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
                <span className="text-xl">🎯</span>
              </div>
              <div>
                <h1 className="text-xl font-bold">NavAI</h1>
                <p className="text-xs text-blue-300">AI Interviewer</p>
              </div>
            </div>

            {/* Navigation Tabs */}
            <nav className="flex items-center gap-2">
              <NavTab 
                active={currentPage === 'interview'} 
                onClick={() => setCurrentPage('interview')}
                icon="🎤"
                label="Interview"
              />
              <NavTab 
                active={currentPage === 'instructions'} 
                onClick={() => setCurrentPage('instructions')}
                icon="📋"
                label="Instructions"
              />
              <NavTab 
                active={currentPage === 'faq'} 
                onClick={() => setCurrentPage('faq')}
                icon="❓"
                label="FAQ"
              />
              <NavTab 
                active={currentPage === 'history'} 
                onClick={() => setCurrentPage('history')}
                icon="📚"
                label="History"
              />
            </nav>

            {/* Right side */}
            <div className="flex items-center gap-4">
              {/* Connection status */}
              <div className={`px-3 py-1.5 rounded-full text-xs font-medium ${
                connectionStatus === 'connected' ? 'bg-green-500/20 text-green-300' :
                connectionStatus === 'error' ? 'bg-red-500/20 text-red-300' :
                'bg-gray-500/20 text-gray-300'
              }`}>
                {connectionStatus === 'connected' ? '● Connected' :
                 connectionStatus === 'error' ? '● Error' : '○ Disconnected'}
              </div>
              
              {/* GitHub link */}
              <a
                href={GITHUB_REPO}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 hover:bg-white/10 rounded-lg transition-colors text-white/70 hover:text-white"
                title="View on GitHub"
              >
                <GitHubIcon />
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {currentPage === 'interview' && (
          <InterviewView
            isActive={isActive}
            status={status}
            messages={messages}
            transcript={transcript}
            interimTranscript={interimTranscript}
            currentScore={currentScore}
            onStart={startInterview}
            onStop={stopInterview}
            error={error}
            screenShareLost={screenShareLost}
            reshareCountdown={reshareCountdown}
            onReshare={reshareScreen}
          />
        )}
        {currentPage === 'instructions' && <InstructionsPage />}
        {currentPage === 'faq' && <FAQPage />}
        {currentPage === 'history' && (
          <HistoryPage interviews={pastInterviews} onRefresh={fetchPastInterviews} />
        )}
      </main>

      {/* Report Generation Popup */}
      {showReportPopup && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="glass-card max-w-md w-full p-8 text-center">
            <div className="text-6xl mb-4">📊</div>
            <h2 className="text-2xl font-bold text-white mb-2">Interview Complete!</h2>
            <p className="text-blue-200 mb-6">
              Would you like to generate a detailed report?
            </p>
            
            {generatingReport ? (
              <div className="py-4">
                <div className="animate-spin text-4xl mb-3">⏳</div>
                <p className="text-blue-300">Generating your report...</p>
              </div>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={requestReport}
                  className="flex-1 py-3 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-xl font-semibold hover:from-blue-600 hover:to-indigo-700 transition-all"
                >
                  ✨ Generate Report
                </button>
                <button
                  onClick={closeWithoutReport}
                  className="flex-1 py-3 bg-white/10 hover:bg-white/20 rounded-xl font-semibold transition-colors"
                >
                  Skip
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Report Modal */}
      {showReportModal && summary && (
        <ReportModal
          summary={summary}
          sessionId={sessionId}
          onClose={() => setShowReportModal(false)}
        />
      )}

      {/* Footer */}
      <footer className="border-t border-white/10 mt-12 py-6">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-between">
          <p className="text-sm text-blue-300/50">
            © 2026 NavAI Interviewer • Built for NavGurukul Hackathon
          </p>
          <a
            href={GITHUB_REPO}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-300/50 hover:text-blue-300 transition-colors flex items-center gap-2"
          >
            <GitHubIcon />
            View Source
          </a>
        </div>
      </footer>
    </div>
  )
}

export default App
