/**
 * NavAI Real-Time Interview App - FIXED VERSION
 * React frontend with WebSocket communication
 */

import { useState, useRef, useCallback, useEffect } from 'react'

// Status badge component
const StatusBadge = ({ status }) => {
  const statusConfig = {
    idle: { bg: 'bg-gray-600', text: 'Ready', icon: '⏸️' },
    connecting: { bg: 'bg-yellow-500', text: 'Connecting...', icon: '🔄' },
    listening: { bg: 'bg-red-500 animate-pulse', text: 'Listening', icon: '🎤' },
    thinking: { bg: 'bg-yellow-500 animate-pulse', text: 'Thinking...', icon: '🧠' },
    speaking: { bg: 'bg-green-500', text: 'Speaking', icon: '🔊' },
    interrupted: { bg: 'bg-orange-500', text: 'Interrupted', icon: '✋' },
    error: { bg: 'bg-red-700', text: 'Error', icon: '❌' },
  }

  const config = statusConfig[status] || statusConfig.idle

  return (
    <div className={`${config.bg} px-4 py-2 rounded-full text-white font-semibold flex items-center gap-2`}>
      <span>{config.icon}</span>
      <span>{config.text}</span>
    </div>
  )
}

// Score display component
const ScoreCard = ({ score, label }) => {
  const getScoreColor = (score) => {
    if (score >= 8) return 'text-green-400'
    if (score >= 6) return 'text-yellow-400'
    return 'text-red-400'
  }

  return (
    <div className="bg-gray-800/50 rounded-xl p-4 text-center">
      <div className={`text-4xl font-bold ${getScoreColor(score)}`}>{score}/10</div>
      <div className="text-gray-400 text-sm mt-1">{label}</div>
    </div>
  )
}

// Audio visualizer component
const AudioVisualizer = ({ isActive }) => {
  if (!isActive) return null

  return (
    <div className="flex items-center justify-center gap-1 h-10">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="w-2 bg-gradient-to-t from-purple-500 to-pink-500 rounded-full animate-pulse"
          style={{ 
            height: `${10 + Math.random() * 20}px`,
            animationDelay: `${i * 0.1}s`
          }}
        />
      ))}
    </div>
  )
}

// Main App component
function App() {
  // State
  const [isActive, setIsActive] = useState(false)
  const [status, setStatus] = useState('idle')
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const [messages, setMessages] = useState([])
  const [currentScore, setCurrentScore] = useState(null)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  
  // Screen share state
  const [screenShareLost, setScreenShareLost] = useState(false)
  const [reshareCountdown, setReshareCountdown] = useState(null)
  
  // Report popup state
  const [showReportPopup, setShowReportPopup] = useState(false)
  const [generatingReport, setGeneratingReport] = useState(false)
  
  // Past interviews
  const [pastInterviews, setPastInterviews] = useState([])
  const [showHistory, setShowHistory] = useState(false)

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
          console.log('[Audio] Playback ended')
          break

        case 'stop_audio':
          stopAudioPlayback()
          break

        case 'screen_update':
          console.log('[Screen] Context updated')
          break

        case 'interview_complete':
          setSummary(data.summary)
          setIsActive(false)
          setStatus('idle')
          setScreenShareLost(false)
          setReshareCountdown(null)
          setShowReportPopup(false)
          setGeneratingReport(false)
          // Refresh past interviews list
          fetchPastInterviews()
          break

        case 'interview_stopped':
          // Show popup to ask if user wants a report
          setShowReportPopup(true)
          setIsActive(false)
          setStatus('idle')
          setScreenShareLost(false)
          setReshareCountdown(null)
          break

        case 'screen_share_lost':
          console.log('[Screen] Share lost - prompting reshare')
          setScreenShareLost(true)
          setReshareCountdown(30) // 30 second countdown
          break

        case 'screen_share_restored':
          console.log('[Screen] Share restored')
          setScreenShareLost(false)
          setReshareCountdown(null)
          break

        case 'error':
          console.error('[WS] Error:', data.message)
          setError(data.message)
          break

        default:
          console.log('[WS] Unknown message type:', type)
      }
    } catch (err) {
      console.error('[WS] Parse error:', err)
    }
  }, [])

  // Fetch past interviews
  const fetchPastInterviews = useCallback(async () => {
    try {
      const response = await fetch('http://localhost:8000/api/interviews')
      const data = await response.json()
      setPastInterviews(data.interviews || [])
    } catch (err) {
      console.error('[History] Failed to fetch:', err)
    }
  }, [])

  // Countdown timer for screen reshare
  useEffect(() => {
    if (reshareCountdown === null || reshareCountdown <= 0) return
    
    const timer = setTimeout(() => {
      setReshareCountdown(prev => prev - 1)
    }, 1000)
    
    return () => clearTimeout(timer)
  }, [reshareCountdown])

  // Fetch past interviews on mount
  useEffect(() => {
    fetchPastInterviews()
  }, [fetchPastInterviews])

  // Audio playback using HTML5 Audio element
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
        audioElementRef.current.onended = () => {
          playNextAudioChunk()
        }
        audioElementRef.current.onerror = (e) => {
          console.error('[Audio] Playback error:', e)
          playNextAudioChunk()
        }
      }

      audioElementRef.current.src = `data:audio/mp3;base64,${audioBase64}`
      await audioElementRef.current.play()
    } catch (err) {
      console.error('[Audio] Error:', err)
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
      const wsUrl = `ws://localhost:8000/ws/interview`
      console.log('[WS] Connecting to:', wsUrl)
      
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        console.log('[WS] Connected')
        setConnectionStatus('connected')
        wsRef.current = ws
        resolve(ws)
      }

      ws.onerror = (err) => {
        console.error('[WS] Error:', err)
        setConnectionStatus('error')
        reject(new Error('WebSocket connection failed. Make sure backend is running.'))
      }

      ws.onclose = () => {
        console.log('[WS] Disconnected')
        setConnectionStatus('disconnected')
        wsRef.current = null
      }

      ws.onmessage = handleWebSocketMessage
    })
  }, [handleWebSocketMessage])

  // Start screen capture
  const startScreenCapture = async () => {
    try {
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

      console.log('[Screen] Capture started:', canvas.width, 'x', canvas.height)

      frameIntervalRef.current = setInterval(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
        if (!video.videoWidth) return

        try {
          const ctx = canvas.getContext('2d')
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          
          const frameData = canvas.toDataURL('image/jpeg', 0.6).split(',')[1]
          
          wsRef.current.send(JSON.stringify({
            type: 'video',
            data: frameData
          }))
        } catch (err) {
          console.error('[Screen] Frame capture error:', err)
        }
      }, 2000)

      stream.getVideoTracks()[0].onended = () => {
        console.log('[Screen] Share ended by user')
        // Don't stop interview - notify backend and allow reshare
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'screen_share_lost' }))
        }
        setScreenShareLost(true)
        setReshareCountdown(30)
        // Clear screen stream but don't stop interview
        screenStreamRef.current = null
        if (frameIntervalRef.current) {
          clearInterval(frameIntervalRef.current)
          frameIntervalRef.current = null
        }
      }

      return stream
    } catch (err) {
      console.error('[Screen] Capture error:', err)
      throw new Error('Screen sharing is required for the interview')
    }
  }

  // Start audio capture using AudioWorklet for raw PCM
  const startAudioCapture = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      })

      mediaStreamRef.current = stream
      console.log('[Audio] Mic access granted')

      // Use AudioContext to get raw PCM data
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      })
      
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      
      processor.onaudioprocess = (e) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
        
        const inputData = e.inputBuffer.getChannelData(0)
        
        // Convert float32 to int16 PCM
        const pcm16 = new Int16Array(inputData.length)
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]))
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        
        // Convert to base64
        const uint8Array = new Uint8Array(pcm16.buffer)
        let binary = ''
        for (let i = 0; i < uint8Array.length; i++) {
          binary += String.fromCharCode(uint8Array[i])
        }
        const base64 = btoa(binary)
        
        wsRef.current.send(JSON.stringify({
          type: 'audio',
          data: base64,
          encoding: 'linear16',
          sampleRate: 16000
        }))
      }
      
      source.connect(processor)
      processor.connect(audioContext.destination)
      
      // Store for cleanup
      mediaRecorderRef.current = { audioContext, processor, source }
      
      console.log('[Audio] PCM recording started')

      return stream
    } catch (err) {
      console.error('[Audio] Capture error:', err)
      throw new Error('Microphone access is required for the interview')
    }
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

      await connectWebSocket()
      await startScreenCapture()
      await startAudioCapture()

      setIsActive(true)
      setStatus('listening')
    } catch (err) {
      console.error('[Interview] Start error:', err)
      setError(err.message)
      setStatus('error')
      stopInterview()
    }
  }

  // Reshare screen during interview
  const reshareScreen = async () => {
    try {
      setError(null)
      console.log('[Screen] Attempting to reshare...')
      
      // Stop old interval if any
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current)
        frameIntervalRef.current = null
      }
      
      // Start new screen capture
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

      console.log('[Screen] Reshare started:', canvas.width, 'x', canvas.height)

      // Notify backend
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'screen_share_restored' }))
      }

      // Reset state
      setScreenShareLost(false)
      setReshareCountdown(null)

      // Start frame capture again
      frameIntervalRef.current = setInterval(() => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
        if (!video.videoWidth) return

        try {
          const ctx = canvas.getContext('2d')
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
          
          const frameData = canvas.toDataURL('image/jpeg', 0.6).split(',')[1]
          
          wsRef.current.send(JSON.stringify({
            type: 'video',
            data: frameData
          }))
        } catch (err) {
          console.error('[Screen] Frame capture error:', err)
        }
      }, 2000)

      // Handle if they stop sharing again
      stream.getVideoTracks()[0].onended = () => {
        console.log('[Screen] Share ended by user again')
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
      console.error('[Screen] Reshare error:', err)
      setError('Failed to reshare screen: ' + err.message)
    }
  }

  // Stop interview
  const stopInterview = useCallback(() => {
    console.log('[Interview] Stopping...')
    
    // Clear screen share state
    setScreenShareLost(false)
    setReshareCountdown(null)
    
    // Stop audio processor
    if (mediaRecorderRef.current) {
      if (mediaRecorderRef.current.processor) {
        mediaRecorderRef.current.processor.disconnect()
        mediaRecorderRef.current.source.disconnect()
        mediaRecorderRef.current.audioContext.close()
      } else if (mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
      }
    }

    // Send stop message but don't close WebSocket yet (wait for popup response)
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

  // Request report generation
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

  // Download report as PDF
  const downloadPDF = useCallback(() => {
    if (!summary) return
    
    // Create a printable HTML content
    const reportContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>Interview Report</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
          h1 { color: #6B46C1; border-bottom: 2px solid #6B46C1; padding-bottom: 10px; }
          h2 { color: #4A5568; margin-top: 30px; }
          .score-box { background: #F7FAFC; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0; }
          .score { font-size: 48px; font-weight: bold; color: #6B46C1; }
          .recommendation { display: inline-block; padding: 8px 16px; border-radius: 20px; font-weight: bold; margin-top: 10px; }
          .pass { background: #C6F6D5; color: #276749; }
          .needs { background: #FEFCBF; color: #975A16; }
          .fail { background: #FED7D7; color: #C53030; }
          .categories { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
          .cat-item { background: #EDF2F7; padding: 15px; border-radius: 8px; text-align: center; }
          .cat-score { font-size: 24px; font-weight: bold; color: #4A5568; }
          .cat-label { font-size: 12px; color: #718096; }
          .section { margin: 20px 0; }
          .section ul { list-style: disc; padding-left: 20px; }
          .section li { margin: 5px 0; }
          .feedback-box { background: #F7FAFC; padding: 15px; border-radius: 8px; margin: 10px 0; }
          .summary { font-style: italic; color: #4A5568; border-left: 4px solid #6B46C1; padding-left: 15px; margin-top: 30px; }
          .footer { margin-top: 40px; text-align: center; color: #A0AEC0; font-size: 12px; }
        </style>
      </head>
      <body>
        <h1>🎯 NavAI Interview Report</h1>
        
        <div class="score-box">
          <div class="score">${summary.overall_score}/100</div>
          <div>Overall Score</div>
          ${summary.recommendation ? `<div class="recommendation ${summary.recommendation === 'PASS' ? 'pass' : summary.recommendation === 'NEEDS_IMPROVEMENT' ? 'needs' : 'fail'}">${summary.recommendation}</div>` : ''}
        </div>

        ${summary.category_scores ? `
        <h2>📊 Category Scores</h2>
        <div class="categories">
          <div class="cat-item"><div class="cat-score">${summary.category_scores.technical_depth || 0}</div><div class="cat-label">Technical Depth</div></div>
          <div class="cat-item"><div class="cat-score">${summary.category_scores.clarity_of_explanation || 0}</div><div class="cat-label">Clarity</div></div>
          <div class="cat-item"><div class="cat-score">${summary.category_scores.originality || 0}</div><div class="cat-label">Originality</div></div>
          <div class="cat-item"><div class="cat-score">${summary.category_scores.implementation_understanding || 0}</div><div class="cat-label">Understanding</div></div>
          <div class="cat-item"><div class="cat-score">${summary.category_scores.visual_aids_quality || 0}</div><div class="cat-label">Visual Aids</div></div>
          <div class="cat-item"><div class="cat-score">${summary.category_scores.presentation_formatting || 0}</div><div class="cat-label">Formatting</div></div>
        </div>
        ` : ''}

        ${summary.strengths?.length > 0 ? `
        <div class="section">
          <h2>✅ Strengths</h2>
          <ul>${summary.strengths.map(s => `<li>${s}</li>`).join('')}</ul>
        </div>
        ` : ''}

        ${(summary.weaknesses?.length > 0 || summary.improvements?.length > 0) ? `
        <div class="section">
          <h2>📈 Areas to Improve</h2>
          <ul>${(summary.weaknesses || summary.improvements || []).map(s => `<li>${s}</li>`).join('')}</ul>
        </div>
        ` : ''}

        ${summary.visual_feedback ? `
        <div class="section">
          <h2>🎨 Visual & Presentation Feedback</h2>
          <div class="feedback-box">
            ${summary.visual_feedback.slide_design ? `<p><strong>Slides:</strong> ${summary.visual_feedback.slide_design}</p>` : ''}
            ${summary.visual_feedback.diagrams ? `<p><strong>Diagrams:</strong> ${summary.visual_feedback.diagrams}</p>` : ''}
            ${summary.visual_feedback.suggestions ? `<p><strong>Suggestions:</strong> ${summary.visual_feedback.suggestions}</p>` : ''}
          </div>
        </div>
        ` : ''}

        ${summary.content_feedback ? `
        <div class="section">
          <h2>📝 Content Feedback</h2>
          <div class="feedback-box">
            ${summary.content_feedback.structure ? `<p><strong>Structure:</strong> ${summary.content_feedback.structure}</p>` : ''}
            ${summary.content_feedback.depth ? `<p><strong>Depth:</strong> ${summary.content_feedback.depth}</p>` : ''}
            ${summary.content_feedback.missing_topics && summary.content_feedback.missing_topics !== "None identified" ? `<p><strong>Missing:</strong> ${summary.content_feedback.missing_topics}</p>` : ''}
          </div>
        </div>
        ` : ''}

        ${summary.summary ? `<p class="summary">"${summary.summary}"</p>` : ''}

        <div class="footer">
          Generated by NavAI Interviewer • ${new Date().toLocaleString()}
        </div>
      </body>
      </html>
    `
    
    // Open print dialog
    const printWindow = window.open('', '_blank')
    printWindow.document.write(reportContent)
    printWindow.document.close()
    printWindow.onload = () => {
      printWindow.print()
    }
  }, [summary])

  useEffect(() => {
    return () => { stopInterview() }
  }, [stopInterview])

  return (
    <div className="min-h-screen text-white p-6">
      {/* Header */}
      <header className="max-w-6xl mx-auto mb-8">
        <div className="bg-gradient-to-r from-purple-600 to-pink-600 rounded-2xl p-6 shadow-xl">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">🎯 NavAI Interviewer</h1>
              <p className="text-purple-200 mt-1">AI-Driven Technical Interview System</p>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="px-3 py-1 rounded-full text-xs bg-purple-500/50 hover:bg-purple-500/70 transition-colors"
              >
                📚 History ({pastInterviews.length})
              </button>
              <div className={`px-3 py-1 rounded-full text-xs ${
                connectionStatus === 'connected' ? 'bg-green-500' : 
                connectionStatus === 'error' ? 'bg-red-500' : 'bg-gray-500'
              }`}>
                {connectionStatus === 'connected' ? '🟢 Connected' : 
                 connectionStatus === 'error' ? '🔴 Error' : '⚪ Disconnected'}
              </div>
              <StatusBadge status={status} />
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Panel */}
        <div className="lg:col-span-2 space-y-6">
          {/* Control Panel */}
          <div className="bg-gray-800/50 rounded-2xl p-6 backdrop-blur">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-semibold">Interview Control</h2>
              {currentScore !== null && <ScoreCard score={currentScore} label="Last Score" />}
            </div>

            {!isActive ? (
              <button
                onClick={startInterview}
                className="w-full py-4 bg-gradient-to-r from-green-500 to-emerald-600 rounded-xl font-semibold text-lg hover:from-green-600 hover:to-emerald-700 transition-all transform hover:scale-[1.02] shadow-lg"
              >
                🚀 Start Interview
              </button>
            ) : (
              <button
                onClick={stopInterview}
                className="w-full py-4 bg-gradient-to-r from-red-500 to-rose-600 rounded-xl font-semibold text-lg hover:from-red-600 hover:to-rose-700 transition-all transform hover:scale-[1.02] shadow-lg"
              >
                ⏹️ End Interview
              </button>
            )}

            {error && (
              <div className="mt-4 p-4 bg-red-500/20 border border-red-500 rounded-xl text-red-300">
                ⚠️ {error}
              </div>
            )}

            {/* Screen Share Lost Modal */}
            {screenShareLost && isActive && (
              <div className="mt-4 p-4 bg-yellow-500/20 border border-yellow-500 rounded-xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 text-yellow-300">
                    <span className="text-2xl">📺</span>
                    <span className="font-semibold">Screen Share Lost</span>
                  </div>
                  {reshareCountdown > 0 && (
                    <span className="text-yellow-400 font-mono">
                      {reshareCountdown}s remaining
                    </span>
                  )}
                </div>
                <p className="text-gray-300 text-sm mb-4">
                  Your screen share was disconnected. Please reshare to continue the interview.
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={reshareScreen}
                    className="flex-1 py-2 bg-green-500 hover:bg-green-600 rounded-lg font-semibold transition-colors"
                  >
                    🔄 Reshare Screen
                  </button>
                  <button
                    onClick={stopInterview}
                    className="flex-1 py-2 bg-red-500 hover:bg-red-600 rounded-lg font-semibold transition-colors"
                  >
                    ⏹️ End Interview
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Live Transcript */}
          <div className="bg-gray-800/50 rounded-2xl p-6 backdrop-blur">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <span>📝 Live Transcript</span>
              <AudioVisualizer isActive={status === 'listening'} />
            </h2>
            <div className="bg-gray-900 rounded-xl p-4 min-h-[120px] font-mono text-sm">
              {transcript && <p className="text-green-400 mb-2">{transcript}</p>}
              {interimTranscript && (
                <p className="text-yellow-400 italic animate-pulse">🎤 {interimTranscript}</p>
              )}
              {!transcript && !interimTranscript && (
                <p className="text-gray-500">
                  {isActive ? '🎤 Listening... Start speaking!' : 'Click "Start Interview" to begin'}
                </p>
              )}
            </div>
          </div>

          {/* Conversation */}
          <div className="bg-gray-800/50 rounded-2xl p-6 backdrop-blur">
            <h2 className="text-xl font-semibold mb-4">💬 Conversation</h2>
            <div className="space-y-4 max-h-[400px] overflow-y-auto">
              {messages.length === 0 ? (
                <p className="text-gray-500 text-center py-8">
                  Start the interview to begin the conversation
                </p>
              ) : (
                messages.map((msg, i) => (
                  <div
                    key={i}
                    className={`p-4 rounded-xl ${
                      msg.role === 'ai'
                        ? 'bg-purple-500/20 border-l-4 border-purple-500'
                        : 'bg-gray-700/50 border-r-4 border-green-500 ml-8'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs text-gray-400">
                        {msg.role === 'ai' ? '🤖 AI Interviewer' : '👤 You'}
                      </span>
                      <span className="text-xs text-gray-500">{msg.timestamp}</span>
                      {msg.score !== undefined && (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          msg.score >= 7 ? 'bg-green-500/30 text-green-300' : 'bg-yellow-500/30 text-yellow-300'
                        }`}>
                          Score: {msg.score}/10
                        </span>
                      )}
                      {msg.conflict && (
                        <span className="text-xs px-2 py-0.5 rounded bg-red-500/30 text-red-300">
                          ⚠️ Conflict
                        </span>
                      )}
                    </div>
                    <p className="text-gray-200">{msg.text}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-6">
          {/* Instructions */}
          <div className="bg-gray-800/50 rounded-2xl p-6 backdrop-blur">
            <h2 className="text-xl font-semibold mb-4">📋 Instructions</h2>
            <ul className="space-y-3 text-gray-300 text-sm">
              <li className="flex items-start gap-2">
                <span className="text-green-400">1.</span>
                Click "Start Interview" to begin
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">2.</span>
                Share your screen when prompted
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">3.</span>
                Allow microphone access
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">4.</span>
                Present your project naturally
              </li>
              <li className="flex items-start gap-2">
                <span className="text-green-400">5.</span>
                The AI will ask questions in real-time
              </li>
            </ul>
          </div>

          {/* Summary Card */}
          {summary && (
            <div className="bg-gradient-to-br from-purple-800/50 to-pink-800/50 rounded-2xl p-6 backdrop-blur border border-purple-500/30">
              <h2 className="text-xl font-semibold mb-4">📊 Interview Report</h2>
              
              {/* Overall Score */}
              <div className="text-center mb-6">
                <div className="text-5xl font-bold text-purple-300">
                  {summary.overall_score}/100
                </div>
                <div className="text-gray-400">Overall Score</div>
                {summary.recommendation && (
                  <span className={`inline-block mt-2 px-3 py-1 rounded-full text-sm font-semibold ${
                    summary.recommendation === 'PASS' ? 'bg-green-500/30 text-green-300' :
                    summary.recommendation === 'NEEDS_IMPROVEMENT' ? 'bg-yellow-500/30 text-yellow-300' :
                    'bg-red-500/30 text-red-300'
                  }`}>
                    {summary.recommendation}
                  </span>
                )}
              </div>

              {/* Category Scores */}
              <div className="grid grid-cols-2 gap-2 mb-6">
                {summary.category_scores ? (
                  <>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-blue-400">{summary.category_scores.technical_depth || 0}</div>
                      <div className="text-xs text-gray-400">Technical Depth</div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-green-400">{summary.category_scores.clarity_of_explanation || 0}</div>
                      <div className="text-xs text-gray-400">Clarity</div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-yellow-400">{summary.category_scores.originality || 0}</div>
                      <div className="text-xs text-gray-400">Originality</div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-pink-400">{summary.category_scores.implementation_understanding || 0}</div>
                      <div className="text-xs text-gray-400">Understanding</div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-cyan-400">{summary.category_scores.visual_aids_quality || 0}</div>
                      <div className="text-xs text-gray-400">Visual Aids</div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-orange-400">{summary.category_scores.presentation_formatting || 0}</div>
                      <div className="text-xs text-gray-400">Formatting</div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-blue-400">{summary.technical_depth || 0}</div>
                      <div className="text-xs text-gray-400">Technical Depth</div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-2 text-center">
                      <div className="text-lg font-bold text-green-400">{summary.clarity || 0}</div>
                      <div className="text-xs text-gray-400">Clarity</div>
                    </div>
                  </>
                )}
              </div>

              {/* Strengths */}
              {summary.strengths?.length > 0 && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-green-400 mb-2">✅ Strengths</h3>
                  <ul className="text-sm text-gray-300 space-y-1">
                    {summary.strengths.map((s, i) => <li key={i}>• {s}</li>)}
                  </ul>
                </div>
              )}

              {/* Weaknesses */}
              {(summary.weaknesses?.length > 0 || summary.improvements?.length > 0) && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-yellow-400 mb-2">📈 Areas to Improve</h3>
                  <ul className="text-sm text-gray-300 space-y-1">
                    {(summary.weaknesses || summary.improvements || []).map((s, i) => <li key={i}>• {s}</li>)}
                  </ul>
                </div>
              )}

              {/* Visual Feedback */}
              {summary.visual_feedback && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-cyan-400 mb-2">🎨 Visual & Presentation Feedback</h3>
                  <div className="text-sm text-gray-300 space-y-1 bg-gray-800/30 rounded p-3">
                    {summary.visual_feedback.slide_design && (
                      <p><span className="text-gray-400">Slides:</span> {summary.visual_feedback.slide_design}</p>
                    )}
                    {summary.visual_feedback.diagrams && (
                      <p><span className="text-gray-400">Diagrams:</span> {summary.visual_feedback.diagrams}</p>
                    )}
                    {summary.visual_feedback.suggestions && (
                      <p><span className="text-gray-400">Suggestions:</span> {summary.visual_feedback.suggestions}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Content Feedback */}
              {summary.content_feedback && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-purple-400 mb-2">📝 Content Feedback</h3>
                  <div className="text-sm text-gray-300 space-y-1 bg-gray-800/30 rounded p-3">
                    {summary.content_feedback.structure && (
                      <p><span className="text-gray-400">Structure:</span> {summary.content_feedback.structure}</p>
                    )}
                    {summary.content_feedback.depth && (
                      <p><span className="text-gray-400">Depth:</span> {summary.content_feedback.depth}</p>
                    )}
                    {summary.content_feedback.missing_topics && summary.content_feedback.missing_topics !== "None identified" && (
                      <p><span className="text-gray-400">Missing:</span> {summary.content_feedback.missing_topics}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Summary */}
              {summary.summary && (
                <p className="mt-4 text-sm text-gray-300 italic border-t border-gray-700 pt-4">
                  "{summary.summary}"
                </p>
              )}

              {/* Download PDF Button */}
              <button
                onClick={downloadPDF}
                className="w-full mt-4 py-2 bg-gradient-to-r from-blue-500 to-cyan-500 rounded-lg font-semibold hover:from-blue-600 hover:to-cyan-600 transition-all flex items-center justify-center gap-2"
              >
                📥 Download PDF
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Report Generation Popup */}
      {showReportPopup && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-2xl max-w-md w-full p-6 text-center">
            <div className="text-5xl mb-4">📊</div>
            <h2 className="text-2xl font-bold mb-2">Interview Complete!</h2>
            <p className="text-gray-400 mb-6">
              Would you like to generate a detailed report of your presentation?
            </p>
            
            {generatingReport ? (
              <div className="py-4">
                <div className="animate-spin text-4xl mb-3">⏳</div>
                <p className="text-purple-400">Generating your report...</p>
              </div>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={requestReport}
                  className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl font-semibold hover:from-purple-600 hover:to-pink-600 transition-all"
                >
                  ✨ Generate Report
                </button>
                <button
                  onClick={closeWithoutReport}
                  className="flex-1 py-3 bg-gray-700 hover:bg-gray-600 rounded-xl font-semibold transition-colors"
                >
                  Skip
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Past Interviews History Modal */}
      {showHistory && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-6 border-b border-gray-700 flex items-center justify-between">
              <h2 className="text-xl font-semibold">📚 Past Interviews</h2>
              <button
                onClick={() => setShowHistory(false)}
                className="text-gray-400 hover:text-white text-2xl"
              >
                ×
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              {pastInterviews.length === 0 ? (
                <p className="text-gray-500 text-center py-8">
                  No past interviews yet. Complete an interview to see it here.
                </p>
              ) : (
                <div className="space-y-4">
                  {pastInterviews.map((interview, i) => (
                    <div
                      key={i}
                      className="bg-gray-800/50 rounded-xl p-4 border border-gray-700"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-purple-400 font-semibold">
                          Session: {interview.session_id}
                        </span>
                        <span className={`text-xs px-2 py-1 rounded ${
                          interview.auto_ended ? 'bg-yellow-500/30 text-yellow-300' : 'bg-green-500/30 text-green-300'
                        }`}>
                          {interview.auto_ended ? 'Auto-ended' : 'Completed'}
                        </span>
                      </div>
                      <div className="text-sm text-gray-400 mb-2">
                        {new Date(interview.timestamp).toLocaleString()}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="bg-gray-700/50 rounded p-2">
                          <div className="text-2xl font-bold text-purple-400">
                            {interview.summary?.overall_score || 0}
                          </div>
                          <div className="text-xs text-gray-400">Score</div>
                        </div>
                        <div className="bg-gray-700/50 rounded p-2">
                          <div className="text-2xl font-bold text-blue-400">
                            {interview.total_questions || 0}
                          </div>
                          <div className="text-xs text-gray-400">Questions</div>
                        </div>
                        <div className="bg-gray-700/50 rounded p-2">
                          <div className="text-2xl font-bold text-green-400">
                            {Math.round(interview.duration_minutes || 0)}
                          </div>
                          <div className="text-xs text-gray-400">Minutes</div>
                        </div>
                      </div>
                      {interview.summary?.summary && (
                        <p className="text-sm text-gray-300 mt-3 italic">
                          "{interview.summary.summary}"
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
