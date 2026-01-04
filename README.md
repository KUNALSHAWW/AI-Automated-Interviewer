<p align="center">
  <img src="https://img.shields.io/badge/AI-Powered-blueviolet?style=for-the-badge&logo=openai&logoColor=white" alt="AI Powered"/>
  <img src="https://img.shields.io/badge/Real--Time-WebSocket-green?style=for-the-badge&logo=websocket&logoColor=white" alt="Real-Time"/>
  <img src="https://img.shields.io/badge/React-18.2-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React"/>
  <img src="https://img.shields.io/badge/FastAPI-0.109-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
</p>

<h1 align="center">🎯 NavAI - AI Automated Interviewer</h1>

<p align="center">
  <strong>An intelligent, real-time AI interviewer for evaluating project presentations and technical demos</strong>
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-demo">Demo</a> •
  <a href="#️-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-api-reference">API</a> •
  <a href="#-tech-stack">Tech Stack</a>
</p>

---

## 🌟 Overview

**NavAI** is a cutting-edge AI-powered interviewer system designed to conduct real-time technical interviews and project presentations. It combines **speech recognition**, **computer vision**, and **large language models** to create an immersive, interactive interview experience that feels natural and human-like.

Built for hackathons, educational assessments, and technical evaluations, NavAI can:
- 🎤 **Listen** to presenters in real-time using Deepgram's Nova-2
- 👁️ **See** screen shares and analyze presentation content
- 🧠 **Think** and generate contextual follow-up questions
- 🗣️ **Speak** responses naturally using Edge TTS
- 📊 **Evaluate** presentations with comprehensive scoring

---

## ✨ Features

### 🎙️ Real-Time Voice Interaction
- **Live Speech Recognition** - Deepgram Nova-2 for accurate, low-latency transcription
- **Natural TTS Responses** - Microsoft Edge TTS with human-like voice synthesis
- **Barge-in Support** - Interrupt the AI mid-sentence, just like a real conversation

### 👁️ Intelligent Vision Processing
- **Screen Share Analysis** - Real-time capture and analysis of presentation slides
- **Smart Change Detection** - SSIM-based algorithm triggers analysis only when content changes
- **Multi-Content Support** - Handles code, diagrams, slides, terminals, and more

### 🧠 Adaptive Questioning Engine
- **Context-Aware Questions** - Questions based on both verbal explanation AND visual content
- **Conflict Detection** - Identifies inconsistencies between what's shown and what's said
- **One Question Per Slide** - Structured questioning that doesn't overwhelm presenters
- **Follow-up Logic** - Probes deeper when answers are unclear or incomplete

### 📊 Comprehensive Evaluation
- **10-Category Scoring System**:
  - Technical Depth
  - Clarity of Explanation
  - Originality & Innovation
  - Implementation Understanding
  - Presentation Formatting
  - Visual Aids Quality
  - Diagrams & Charts
  - Code Quality
  - Problem Solving
  - Communication Skills

### 📄 Professional Reporting
- **Detailed PDF Reports** - Downloadable interview summaries
- **Strengths & Weaknesses** - Specific feedback with examples
- **Visual Feedback** - Comments on slide design, diagrams, and formatting
- **Actionable Recommendations** - PASS / NEEDS_IMPROVEMENT / FAIL with reasoning

### 🔄 Session Management
- **Interview History** - Track all past interviews
- **Screen Reconnection** - 30-second grace period to reshare if disconnected
- **Report Generation Choice** - Generate detailed report or skip after interview

---

## 🎬 Demo

### Interview Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        START INTERVIEW                          │
├─────────────────────────────────────────────────────────────────┤
│  1. 🎤 AI Greets & Asks for Introduction                       │
│  2. 📺 User Shares Screen                                       │
│  3. 🗣️ User Presents Project                                   │
│  4. 👁️ AI Analyzes Screen Content                              │
│  5. 🧠 AI Asks Contextual Questions                            │
│  6. 📝 AI Scores Each Response                                 │
│  7. 🔄 Repeat for Each Slide                                   │
│  8. 📊 Generate Comprehensive Report                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                           FRONTEND                                  │
│                     React 18 + Vite + Tailwind                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Audio      │  │   Screen     │  │    UI        │              │
│  │   Capture    │  │   Share      │  │  Components  │              │
│  │  (PCM 16k)   │  │  (JPEG)      │  │              │              │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘              │
│         │                 │                                         │
│         └────────┬────────┘                                         │
│                  │ WebSocket                                        │
└──────────────────┼──────────────────────────────────────────────────┘
                   │
┌──────────────────┼──────────────────────────────────────────────────┐
│                  │            BACKEND                               │
│                  ▼         FastAPI + WebSocket                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    WebSocket Handler                           │ │
│  │              Manages real-time bidirectional comms             │ │
│  └───────────────────────────────────────────────────────────────┘ │
│         │                │                │                │        │
│         ▼                ▼                ▼                ▼        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │  Deepgram  │  │   Vision   │  │  Interview │  │    TTS     │   │
│  │   Client   │  │ Processor  │  │   Brain    │  │   Engine   │   │
│  │            │  │            │  │            │  │            │   │
│  │  Nova-2    │  │ Groq Llama │  │ Groq Llama │  │  Edge TTS  │   │
│  │   STT      │  │  4 Scout   │  │ 3.3 70B    │  │            │   │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    Interview Storage                          │ │
│  │                 JSON files in /interview_history              │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Module Breakdown

| Module | Purpose | Technology |
|--------|---------|------------|
| `server.py` | WebSocket server, session management | FastAPI, uvicorn |
| `interview_brain.py` | AI evaluation engine, question generation | Groq Llama 3.3 70B |
| `vision_processor.py` | Screen analysis with change detection | Groq Llama 4 Scout |
| `tts_engine.py` | Text-to-speech synthesis | Edge TTS / OpenAI |
| `deepgram_client.py` | Speech-to-text transcription | Deepgram Nova-2 |
| `config.py` | Centralized configuration | python-dotenv |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **API Keys** (all have free tiers):
  - [Groq](https://console.groq.com) - LLM & Vision (FREE, fast)
  - [Deepgram](https://console.deepgram.com) - Speech-to-Text (FREE tier)

### Installation

#### 1️⃣ Clone the Repository

```bash
git clone https://github.com/KUNALSHAWW/AI-Automated-Interviewer.git
cd AI-Automated-Interviewer
```

#### 2️⃣ Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.template .env
# Edit .env with your API keys
```

#### 3️⃣ Frontend Setup

```bash
cd frontend

# Install dependencies
npm install
```

#### 4️⃣ Configure API Keys

Edit `backend/.env`:

```env
# Required (both have FREE tiers)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx
DEEPGRAM_API_KEY=xxxxxxxxxxxxxxxxxxxxx

# Optional
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
```

### Running the Application

#### Option 1: Using Batch Scripts (Windows)

```bash
# Terminal 1 - Backend
start-backend.bat

# Terminal 2 - Frontend
start-frontend.bat
```

#### Option 2: Manual Start

```bash
# Terminal 1 - Backend
cd backend
python server.py

# Terminal 2 - Frontend
cd frontend
npm run dev
```

#### 5️⃣ Access the Application

Open your browser and navigate to:
```
http://localhost:3000
```

---

## 📖 API Reference

### WebSocket Endpoint

```
ws://localhost:8000/ws/interview
```

### Client → Server Messages

| Type | Payload | Description |
|------|---------|-------------|
| `audio` | `{data: base64, encoding: "linear16", sampleRate: 16000}` | Audio chunk from microphone |
| `video` | `{data: base64}` | Screen capture frame (JPEG) |
| `stop` | `{}` | End interview session |
| `generate_report` | `{}` | Request final report generation |
| `screen_share_lost` | `{}` | Notify screen share disconnected |
| `screen_share_restored` | `{}` | Notify screen share reconnected |

### Server → Client Messages

| Type | Payload | Description |
|------|---------|-------------|
| `status` | `{state: "listening" \| "thinking" \| "speaking"}` | Current AI state |
| `transcript_interim` | `{text: string}` | Partial transcription |
| `transcript_final` | `{text: string}` | Final transcription |
| `evaluation` | `{score: number, next_question: string, conflict_detected: boolean}` | AI evaluation |
| `audio_chunk` | `{audio: base64}` | TTS audio chunk (MP3) |
| `interview_complete` | `{summary: object, history: array}` | Final report |
| `interview_stopped` | `{session_id: string}` | Interview ended, prompt for report |

### REST Endpoints

```http
GET /api/interviews
```
Returns list of all past interviews.

```http
GET /api/interview/{session_id}
```
Returns specific interview details.

---

## 🛠️ Tech Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.10+ | Runtime |
| FastAPI | 0.109 | Web Framework |
| Groq | Latest | LLM Inference |
| Deepgram | Nova-2 | Speech Recognition |
| Edge TTS | 6.1.9 | Text-to-Speech |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.2 | UI Framework |
| Vite | 5.0 | Build Tool |
| Tailwind CSS | 3.4 | Styling |
| WebSocket | Native | Real-time Comms |

### AI Models

| Model | Provider | Purpose |
|-------|----------|---------|
| `llama-3.3-70b-versatile` | Groq | Evaluation & Questions |
| `llama-4-scout-17b-16e-instruct` | Groq | Vision/Screen Analysis |
| `nova-2` | Deepgram | Speech-to-Text |
| `en-US-GuyNeural` | Edge TTS | Text-to-Speech |

---

## 📁 Project Structure

```
AI-Automated-Interviewer/
├── 📁 backend/
│   ├── 📄 server.py              # FastAPI WebSocket server
│   ├── 📄 requirements.txt       # Python dependencies
│   ├── 📄 .env.template          # Environment template
│   ├── 📁 modules/
│   │   ├── 📄 config.py          # Configuration management
│   │   ├── 📄 interview_brain.py # AI evaluation engine
│   │   ├── 📄 vision_processor.py# Screen analysis
│   │   ├── 📄 tts_engine.py      # Text-to-speech
│   │   └── 📄 deepgram_client.py # Speech recognition
│   └── 📁 interview_history/     # Saved interviews (JSON)
│
├── 📁 frontend/
│   ├── 📄 package.json           # Node dependencies
│   ├── 📄 vite.config.js         # Vite configuration
│   ├── 📄 tailwind.config.js     # Tailwind configuration
│   ├── 📄 index.html             # Entry HTML
│   └── 📁 src/
│       ├── 📄 App.jsx            # Main React component
│       ├── 📄 main.jsx           # React entry point
│       └── 📄 index.css          # Global styles
│
├── 📄 start-backend.bat          # Windows backend launcher
├── 📄 start-frontend.bat         # Windows frontend launcher
└── 📄 README.md                  # This file
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | ✅ Yes | - | Groq API key for LLM |
| `DEEPGRAM_API_KEY` | ✅ Yes | - | Deepgram API key for STT |
| `OPENAI_API_KEY` | ❌ No | - | OpenAI key (better TTS) |
| `LLM_MODEL` | ❌ No | `llama-3.3-70b-versatile` | Evaluation model |
| `VISION_MODEL` | ❌ No | `meta-llama/llama-4-scout-17b-16e-instruct` | Vision model |
| `TTS_PROVIDER` | ❌ No | `edge` | TTS provider (`edge`/`openai`) |
| `EDGE_TTS_VOICE` | ❌ No | `en-US-GuyNeural` | Edge TTS voice |
| `VISION_CHANGE_THRESHOLD` | ❌ No | `0.10` | Frame change sensitivity |
| `VISION_MIN_INTERVAL` | ❌ No | `3.0` | Min seconds between vision calls |

---

## 🎯 Use Cases

### 🎓 Educational Assessment
- Evaluate student project presentations
- Provide instant feedback on technical understanding
- Track progress across multiple presentations

### 💼 Technical Interviews
- Screen coding candidates
- Assess system design explanations
- Evaluate communication skills

### 🏆 Hackathon Judging
- Automate initial project screening
- Consistent evaluation criteria
- Scale to multiple submissions

### 📝 Practice & Training
- Safe environment to practice presentations
- Immediate feedback for improvement
- Build confidence before real interviews

---

## 🔒 Security Considerations

- **API Keys**: Never commit `.env` files. Use `.env.template` as reference.
- **WebSocket**: Currently configured for localhost. Add authentication for production.
- **CORS**: Configured for localhost origins. Restrict in production.
- **Data Storage**: Interview history stored locally. Consider encryption for sensitive data.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Groq](https://groq.com) - Lightning-fast LLM inference
- [Deepgram](https://deepgram.com) - Best-in-class speech recognition
- [Microsoft Edge TTS](https://github.com/rany2/edge-tts) - High-quality free TTS
- [FastAPI](https://fastapi.tiangolo.com) - Modern Python web framework
- [React](https://react.dev) - UI library
- [Tailwind CSS](https://tailwindcss.com) - Utility-first CSS framework

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/KUNALSHAWW">Kunal Shaw</a>
</p>

<p align="center">
  <a href="https://github.com/KUNALSHAWW/AI-Automated-Interviewer">
    ⭐ Star this repo if you found it helpful!
  </a>
</p>
