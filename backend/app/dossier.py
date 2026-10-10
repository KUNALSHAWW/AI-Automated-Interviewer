"""Repository dossier: what the student's repo actually contains.

Built once per session from the public GitHub API + raw files. Stack, structure and "probe topics"
are computed deterministically; an LLM only adds a short readable brief (best effort).
"""
from __future__ import annotations

import asyncio
import posixpath
import random
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import quote

import httpx

from .techlex import find_techs

GITHUB_RE = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]{1,39})/([A-Za-z0-9_.-]{1,100}?)(?:\.git)?(?:/.*)?/?$")

SKIP_DIRS = {"node_modules", "dist", "build", ".git", "vendor", "__pycache__", ".venv", "venv", "target",
             ".next", ".idea", ".vscode", "coverage", "site-packages", "bower_components"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".mp4", ".webp", ".lock", ".woff", ".woff2",
            ".ttf", ".zip", ".gz", ".jar", ".pyc", ".class", ".bin", ".onnx", ".pt", ".h5", ".csv", ".json.map"}
CODE_EXT = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
            ".java": "Java", ".go": "Go", ".rs": "Rust", ".cpp": "C++", ".cc": "C++", ".c": "C", ".cs": "C#",
            ".php": "PHP", ".rb": "Ruby", ".kt": "Kotlin", ".swift": "Swift", ".dart": "Dart", ".html": "HTML",
            ".css": "CSS", ".sql": "SQL", ".ipynb": "Jupyter", ".sh": "Shell", ".vue": "Vue", ".svelte": "Svelte"}
MANIFESTS = {"package.json", "requirements.txt", "pyproject.toml", "pipfile", "pom.xml", "build.gradle",
             "build.gradle.kts", "go.mod", "cargo.toml", "composer.json", "gemfile", "dockerfile",
             "docker-compose.yml", "docker-compose.yaml", "render.yaml", "vercel.json", ".env.example",
             "makefile", "environment.yml", "setup.py"}
ENTRY_HINTS = ("main", "app", "server", "index", "routes", "router", "views", "models", "schema", "api",
               "controller", "service", "handler", "core", "engine")
MAX_FILE_CHARS = 18000


class DossierError(Exception):
    """User-facing: the repo could not be analysed. The session can still run without it."""


@dataclass
class Dossier:
    repo: str = ""
    url: str = ""
    branch: str = ""
    description: str = ""
    languages: dict = field(default_factory=dict)
    techs: list = field(default_factory=list)            # built: manifests, paths, imports
    documented_techs: list = field(default_factory=list)  # only the README says so
    has_tests: bool = False
    has_ci: bool = False
    has_docker: bool = False
    file_count: int = 0
    tree_sample: list = field(default_factory=list)
    readme: str = ""
    manifests: dict = field(default_factory=dict)
    key_files: list = field(default_factory=list)
    probe_topics: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    brief: str = ""
    evidence_text: str = ""  # server-side only; stripped from API responses

    def public(self) -> dict:
        d = asdict(self)
        d.pop("evidence_text", None)
        d["readme"] = self.readme[:600]
        d["manifests"] = sorted(self.manifests)
        d["key_files"] = [k["path"] for k in self.key_files]
        return d

    def prompt_block(self, max_chars: int = 3500) -> str:
        """Compact text the interviewer model sees every turn."""
        langs = ", ".join(f"{k} ({v})" for k, v in list(self.languages.items())[:5])
        lines = [
            f"Repository: {self.repo} - {self.description or 'no description'}",
            f"Languages by file count: {langs or 'unknown'}",
            f"Technologies BUILT (found in manifests, file paths or import statements): {', '.join(self.techs) or 'none detected'}",
            f"Technologies only DOCUMENTED in the README (no dependency, path or import backs them up): "
            f"{', '.join(self.documented_techs) or 'none'}",
            f"Tests present: {self.has_tests}; CI workflow: {self.has_ci}; Docker: {self.has_docker}",
            f"Files: {self.file_count}. Sample paths: {', '.join(self.tree_sample[:25])}",
            "README excerpt:\n" + self.readme[:1500],
        ]
        for k in self.key_files[:3]:
            lines.append(f"Key file {k['path']} (comments stripped):\n{k['excerpt'][:700]}")
        return "\n".join(lines)[:max_chars]


def parse_repo_url(url: str) -> tuple[str, str]:
    m = GITHUB_RE.match((url or "").strip())
    if not m:
        raise DossierError("Only public github.com repository URLs are supported (https://github.com/owner/repo)")
    return m.group(1), m.group(2)


def strip_comments(text: str, ext: str) -> str:
    """Remove whole-line comments. AI-written code arrives pre-narrated; the viva should test the student, not the comments."""
    marks = ("#",) if ext in {".py", ".sh", ".rb"} else ("//", "/*", "*", "#" if ext in {".yml", ".yaml"} else "//")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#!"):
            out.append(line)
        elif s and any(s.startswith(m) for m in marks):
            continue
        else:
            out.append(line)
    return "\n".join(out)


_IMPORT_RE = re.compile(r"^\s*(?:import\b|from\s+\S+\s+import\b|using\b|use\b|require\b|#include\b|package\b)"
                        r"|\brequire\(|\bimport\(|\bimport\s+.*\bfrom\s+['\"]", re.M)


def import_lines(source: str) -> str:
    """Only the import/require lines of a source file (the part that proves a library is really used)."""
    return "\n".join(line for line in source.splitlines() if _IMPORT_RE.search(line))


def _useful(path: str) -> bool:
    parts = path.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return False
    name = parts[-1].lower()
    ext = posixpath.splitext(name)[1]
    if ext in SKIP_EXT or name.endswith("-lock.json") or name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
        return False
    return True


def _score_key_file(path: str) -> float:
    base = posixpath.basename(path).lower()
    stem, ext = posixpath.splitext(base)
    if ext not in CODE_EXT or ext in {".html", ".css", ".sql", ".ipynb"}:
        return -1
    if re.search(r"(^|/)(tests?|__tests__|spec|migrations?|examples?|docs?)/", path.lower()) or stem.startswith("test_"):
        return -1
    score = 5.0 - path.count("/") * 0.9
    if any(h in stem for h in ENTRY_HINTS):
        score += 3
    return score


def _is_test(path: str) -> bool:
    p = path.lower()
    return bool(re.search(r"(^|/)(tests?|__tests__|spec)/", p) or re.search(r"(^|/)test_[^/]+\.py$", p)
                or re.search(r"\.(test|spec)\.[jt]sx?$", p) or p.endswith("_test.go"))


def make_probe_topics(d: Dossier, seed: str) -> list[str]:
    rng = random.Random(seed)
    topics: list[str] = []
    techs = [t for t in d.techs if t not in {"CI/CD", "REST API", "Node.js", "Render", "Go", "Java"}]
    rng.shuffle(techs)
    for t in techs[:4]:
        topics.append(f"Why {t} was chosen and where exactly it is used in the code")
    keys = [k["path"] for k in d.key_files]
    rng.shuffle(keys)
    for p in keys[:2]:
        topics.append(f"Walk through what {p} does and what would break if it were removed")
    topics.append("How the student knows the project works (tests, manual checks, failure cases)" if d.has_tests
                  else "No automated tests were found: how is correctness verified?")
    if not d.has_ci and d.techs:
        topics.append("How the project is deployed or run by someone else")
    return topics[:8]


def deterministic_brief(d: Dossier) -> str:
    langs = ", ".join(list(d.languages)[:3]) or "unknown languages"
    stack = ", ".join(d.techs[:8]) or "no frameworks detected"
    flags = []
    flags.append("has tests" if d.has_tests else "no tests found")
    flags.append("CI workflow present" if d.has_ci else "no CI workflow")
    if d.has_docker:
        flags.append("Docker files present")
    desc = f" {d.description.strip()}." if d.description else ""
    return f"{d.repo}:{desc} Written mostly in {langs}. Stack evidence: {stack}. {'; '.join(flags).capitalize()}."


async def build_dossier(url: str, http: httpx.AsyncClient, *, token: str = "", seed: str = "") -> Dossier:
    owner, repo = parse_repo_url(url)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "navai-viva", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async def gh(path: str) -> httpx.Response:
        try:
            return await http.get(f"https://api.github.com{path}", headers=headers, timeout=15.0)
        except httpx.HTTPError as e:
            raise DossierError(f"Could not reach GitHub: {e.__class__.__name__}") from None

    r = await gh(f"/repos/{owner}/{repo}")
    if r.status_code == 404:
        raise DossierError("Repository not found, or it is private. Only public repositories can be analysed.")
    if r.status_code in (403, 429):
        raise DossierError("GitHub rate limit reached (60 requests/hour without a token). Try later or set GITHUB_TOKEN.")
    if r.status_code != 200:
        raise DossierError(f"GitHub returned HTTP {r.status_code}")
    meta = r.json()
    branch = meta.get("default_branch") or "main"

    t = await gh(f"/repos/{owner}/{repo}/git/trees/{quote(branch, safe='')}?recursive=1")
    if t.status_code != 200:
        raise DossierError(f"Could not read the file tree (HTTP {t.status_code})")
    tree = t.json()
    paths = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob" and _useful(e["path"])]

    d = Dossier(repo=f"{owner}/{repo}", url=f"https://github.com/{owner}/{repo}", branch=branch,
                description=(meta.get("description") or "")[:200], file_count=len(paths))
    if tree.get("truncated"):
        d.warnings.append("Repository tree was truncated by GitHub; very large repositories are only partly analysed.")
    if not paths:
        raise DossierError("The repository has no readable source files")

    langs: dict[str, int] = {}
    for p in paths:
        lang = CODE_EXT.get(posixpath.splitext(p)[1].lower())
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    d.languages = dict(sorted(langs.items(), key=lambda kv: -kv[1]))
    d.has_tests = any(_is_test(p) for p in paths)
    d.has_ci = any(p.startswith(".github/workflows/") for p in paths)
    d.has_docker = any(posixpath.basename(p).lower().startswith(("dockerfile", "docker-compose")) for p in paths)
    top = sorted({p.split("/")[0] + ("/" if "/" in p else "") for p in paths})
    d.tree_sample = (top + [p for p in paths if p.count("/") == 1][:30])[:60]

    readme_path = next((p for p in paths if p.lower() in {"readme.md", "readme.rst", "readme.txt", "readme"}), None) \
        or next((p for p in paths if posixpath.basename(p).lower().startswith("readme")), None)
    manifest_paths = [p for p in paths if posixpath.basename(p).lower() in MANIFESTS and p.count("/") <= 2][:8]
    key_paths = [p for p in sorted(paths, key=_score_key_file, reverse=True) if _score_key_file(p) > 0][:5]

    sem = asyncio.Semaphore(6)

    async def raw(path: str) -> tuple[str, str]:
        url_ = f"https://raw.githubusercontent.com/{owner}/{repo}/{quote(branch, safe='')}/{quote(path)}"
        async with sem:
            try:
                rr = await http.get(url_, headers={"User-Agent": "navai-viva"}, timeout=15.0)
                return path, rr.text[:MAX_FILE_CHARS] if rr.status_code == 200 else ""
            except httpx.HTTPError:
                return path, ""

    wanted = ([readme_path] if readme_path else []) + manifest_paths + key_paths
    fetched = dict(await asyncio.gather(*(raw(p) for p in wanted)))
    d.readme = fetched.get(readme_path, "") if readme_path else ""
    if not d.readme:
        d.warnings.append("No README found; claims in the README cannot be cross-checked.")
    d.manifests = {p: fetched.get(p, "") for p in manifest_paths if fetched.get(p)}
    for p in key_paths:
        txt = fetched.get(p, "")
        if txt:
            d.key_files.append({"path": p, "excerpt": strip_comments(txt, posixpath.splitext(p)[1].lower())[:2500]})

    d.evidence_text = "\n".join([d.readme, *d.manifests.values(), "\n".join(paths[:1500]),
                                 *(k["excerpt"] for k in d.key_files)])[:60000]
    # What is BUILT: dependency manifests, file paths and import statements. A tool name merely appearing in
    # source text (a lexicon, a comment, a string, a test fixture) is not evidence it is used.
    imports = "\n".join(import_lines(k["excerpt"]) for k in d.key_files)
    build_text = "\n".join([*d.manifests.values(), "\n".join(paths[:1500]), imports])
    d.techs = sorted(find_techs(build_text))
    # What is DOCUMENTED: the README names it but no manifest, path or import backs it up.
    d.documented_techs = sorted(find_techs(d.readme) - set(d.techs))
    d.probe_topics = make_probe_topics(d, seed or d.repo)
    d.brief = deterministic_brief(d)
    return d
