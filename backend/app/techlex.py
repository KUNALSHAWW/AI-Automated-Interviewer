"""Deterministic technology lexicon and claim checking.

No LLM is involved here, so the "you said X but the repository has no trace of X" signal is
reproducible and unit-tested. It is deliberately conservative: absence from the repo is reported as
"not found in repository evidence" (a prompt to ask), never as "false".
"""
from __future__ import annotations

import re

# canonical name -> regex alternatives matched on word-ish boundaries, case-insensitive
_LEX: dict[str, list[str]] = {
    "Python": [r"python"], "JavaScript": [r"javascript", r"\.js\b"], "TypeScript": [r"typescript", r"\.tsx?\b"],
    "Java": [r"java(?!script)"], "Go": [r"golang", r"go\.mod"], "Rust": [r"cargo\.toml"],
    "C++": [r"c\+\+", r"cpp"], "C#": [r"c#", r"csharp", r"\.csproj"], "PHP": [r"php", r"composer\.json"],
    "Kotlin": [r"kotlin"], "Swift": [r"swiftui"], "Dart": [r"pubspec\.yaml"], "Flutter": [r"flutter"],
    "React": [r"react-dom", r"reactjs", r"['\"]react['\"]"], "Next.js": [r"next\.?js"],
    "Vue": [r"vue(?:\.?js)?"], "Angular": [r"angular"], "Svelte": [r"svelte"], "Tailwind": [r"tailwind"],
    "Redux": [r"redux"], "Vite": [r"vite\b"],
    "Node.js": [r"node\.?js", r"\bnode\b", r"package\.json"], "Express": [r"express\.js"],
    "FastAPI": [r"fastapi", r"fast api"], "Flask": [r"flask"], "Django": [r"django"],
    "Spring Boot": [r"spring ?boot", r"springframework", r"spring-boot"], "Maven": [r"maven", r"pom\.xml"],
    "Gradle": [r"gradle"], "Laravel": [r"laravel"], "NestJS": [r"nest\.?js"],
    "PostgreSQL": [r"postgres(?:ql)?", r"psycopg", r"asyncpg", r"\bpg\b"], "MySQL": [r"mysql", r"mariadb"],
    "MongoDB": [r"mongo(?:db)?", r"mongoose", r"pymongo"], "SQLite": [r"sqlite"], "Redis": [r"redis"],
    "Elasticsearch": [r"elastic ?search", r"opensearch"], "Firebase": [r"firebase", r"firestore"],
    "Supabase": [r"supabase"], "Prisma": [r"prisma"], "SQLAlchemy": [r"sqlalchemy"], "Hibernate": [r"hibernate"],
    "Kafka": [r"kafka"], "RabbitMQ": [r"rabbit ?mq", r"\bamqp\b"], "Celery": [r"celery"],
    "Docker": [r"docker(?:file)?", r"docker-compose"], "Kubernetes": [r"kubernetes", r"\bk8s\b", r"kubectl", r"helm"],
    "AWS": [r"\baws\b", r"amazon web services", r"\bs3\b", r"\bec2\b", r"boto3"],
    "GCP": [r"\bgcp\b", r"google cloud"], "Azure": [r"azure"], "Vercel": [r"vercel"], "Render": [r"render\.yaml", r"render\.com"],
    "Nginx": [r"nginx"], "GitHub Actions": [r"github actions", r"\.github/workflows"], "CI/CD": [r"ci/cd", r"\bci\b", r"pipeline"],
    "Terraform": [r"terraform"],
    "TensorFlow": [r"tensorflow", r"\bkeras\b"], "PyTorch": [r"pytorch", r"\btorch\b"],
    "scikit-learn": [r"scikit-?learn", r"sklearn"], "OpenCV": [r"opencv", r"cv2"], "NumPy": [r"numpy"],
    "Pandas": [r"pandas"], "Hugging Face": [r"hugging ?face", r"transformers"], "LangChain": [r"langchain", r"langgraph"],
    "OpenAI API": [r"openai"], "Gemini": [r"gemini"], "Ollama": [r"ollama"], "Groq": [r"groq"],
    "RAG": [r"\brag\b", r"retrieval[- ]augmented", r"vector (?:db|database|store)", r"faiss", r"chroma(?:db)?", r"pinecone"],
    "REST API": [r"rest(?:ful)?(?: api)?\b"], "GraphQL": [r"graphql"], "WebSocket": [r"web ?sockets?"],
    "gRPC": [r"grpc"], "JWT": [r"\bjwt\b", r"json web token"], "OAuth": [r"oauth"],
    "Stripe": [r"stripe"], "Twilio": [r"twilio"],
    "Jest": [r"\bjest\b"], "pytest": [r"pytest"], "JUnit": [r"junit"], "Cypress": [r"cypress"],
    "Selenium": [r"selenium"], "Playwright": [r"playwright"],
    "Streamlit": [r"streamlit"], "Gradio": [r"gradio"], "Socket.IO": [r"socket\.?io"],
    "Blockchain": [r"blockchain", r"solidity", r"web3", r"ethereum"],
    "Arduino": [r"arduino"], "Raspberry Pi": [r"raspberry ?pi"], "MQTT": [r"mqtt"],
}

# Tools too generic to be a meaningful "claim": a repo almost always matches or a speaker says them in passing.
_WEAK = {"CI/CD", "REST API", "Node.js", "Render", "Go", "Java", "Swift", "Dart", "Rust"}

# Words that are also ordinary English verbs/nouns: only the capitalised form (how a transcript
# or README writes the tool) counts, in addition to the specific lowercase aliases above.
_CAPITALISED = {
    "React": r"React(?:JS|\.js)?", "Express": r"Express(?:JS)?", "Swift": r"Swift", "Rust": r"Rust",
    "Dart": r"Dart", "Go": r"Golang",
}

_WRAP = r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])"
_PATTERNS: dict[str, list[re.Pattern]] = {
    name: [re.compile(_WRAP % "|".join(alts), re.I)] for name, alts in _LEX.items()
}
for _name, _rx in _CAPITALISED.items():
    _PATTERNS[_name].append(re.compile(_WRAP % _rx))  # case-sensitive on purpose

_PERCENT = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d+)?)\s?(?:%|percent\b|per cent\b)", re.I)
_MULTIPLIER = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d+)?)\s?(?:x|times)\s+(?:faster|more|better|less|smaller|speed)", re.I)


def find_techs(text: str) -> set[str]:
    """Technologies mentioned in free text (a transcript segment, a README, a manifest)."""
    return {name for name, rxs in _PATTERNS.items() if any(rx.search(text) for rx in rxs)}


def find_metrics(text: str) -> set[str]:
    out = {f"{m.group(1)}%" for m in _PERCENT.finditer(text)}
    out |= {f"{m.group(1)}x" for m in _MULTIPLIER.finditer(text)}
    return out


def check_claims(spoken: str, repo_evidence: str, repo_techs: set[str], screen_text: str = "",
                 documented: set[str] | None = None) -> dict:
    """Compare what was said and shown with what the repository contains.

    `repo_techs` is what is BUILT (manifests, file paths, import statements). `documented` is what only the
    README claims. A technology that is only said, or only drawn on a slide, is reported as:
      * `documented_only` when the README names it but nothing in the code base backs it up, or
      * `not_found` when the repository evidence has no trace of it at all.
    Both are prompts to ask, not accusations. Numeric claims are supported by the README or by the screen the
    student chose to show.

    Returns {"supported", "documented_only", "not_found", "unverified_metrics", "unspoken"} (sorted lists).
    """
    documented = documented or set()
    said = find_techs(spoken)
    shown = find_techs(screen_text) if screen_text else set()
    mentioned = {t for t in (said | shown) if t not in _WEAK}
    supported = sorted(t for t in said if t in repo_techs)
    documented_only = sorted(t for t in mentioned if t not in repo_techs and t in documented)
    not_found = sorted(t for t in mentioned if t not in repo_techs and t not in documented)
    evidence_metrics = find_metrics(repo_evidence) | (find_metrics(screen_text) if screen_text else set())
    bad_metrics = sorted(m for m in find_metrics(spoken) if m not in evidence_metrics)
    return {
        "supported": supported,
        "documented_only": documented_only,
        "not_found": not_found,
        "unverified_metrics": bad_metrics,
        "unspoken": sorted(t for t in repo_techs if t not in said and t not in _WEAK),
    }


# Speech recognition splits or re-cases product names ("FAST API", "GIT Hub", "Postgres SQL"). Restoring the
# canonical spelling makes transcripts readable and keeps quote verification and claim checks consistent.
_RESPELL = {
    "FastAPI": r"fast[\s-]api", "GitHub": r"git[\s-]hub", "PostgreSQL": r"post[\s-]?gres[\s-]?(?:sql|ql)",
    "MongoDB": r"mongo[\s-]db", "GraphQL": r"graph[\s-]ql", "OpenAI": r"open[\s-]ai", "JavaScript": r"java[\s-]script",
    "TypeScript": r"type[\s-]script", "WebSocket": r"web[\s-]socket", "WebSockets": r"web[\s-]sockets",
    "Node.js": r"node[\s-]js", "Next.js": r"next[\s-]js", "PyTorch": r"pie[\s-]torch", "TensorFlow": r"tensor[\s-]flow",
    "scikit-learn": r"scikit[\s-]learn|sci[\s-]kit[\s-]learn", "LangChain": r"lang[\s-]chain", "NumPy": r"num[\s-]py",
    "Docker": r"dock[\s-]er", "Kubernetes": r"cuber?netes|kuber[\s-]netes", "Redis": r"re[\s-]dis(?=\s|\W|$)",
}
_RESPELL_RX = [(canon, re.compile(r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % rx, re.I)) for canon, rx in _RESPELL.items()]


def normalize_transcript(text: str) -> str:
    for canon, rx in _RESPELL_RX:
        text = rx.sub(canon, text)
    return text
