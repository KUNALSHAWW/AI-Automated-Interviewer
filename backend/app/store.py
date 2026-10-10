"""SQLite session store. Every session is saved when it ends (even if no report is requested), is only
readable with its secret token, and can be deleted. Thumbnails/PDFs live next to the row on disk."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import shutil
import sqlite3
import threading
import time
from pathlib import Path


class Store:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.dir / "navai.sqlite3", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,"
                "status TEXT NOT NULL, meta TEXT NOT NULL, state TEXT, report TEXT)")

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def session_dir(self, sid: str) -> Path:
        if not sid.replace("-", "").replace("_", "").isalnum():
            raise ValueError("bad session id")
        p = self.dir / "sessions" / sid
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ----------------------------------------------------------------- CRUD
    def create(self, meta: dict) -> tuple[str, str]:
        sid, token = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b"), secrets.token_urlsafe(24)
        now = time.time()
        with self._lock, self._db:
            self._db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,NULL,NULL)",
                             (sid, self._hash(token), now, now, "created", json.dumps(meta)))
        return sid, token

    def check_token(self, sid: str, token: str) -> bool:
        with self._lock:
            row = self._db.execute("SELECT token_hash FROM sessions WHERE id=?", (sid,)).fetchone()
        return bool(row) and hmac.compare_digest(row["token_hash"], self._hash(token or ""))

    def get(self, sid: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "created": row["created"], "updated": row["updated"], "status": row["status"],
                "meta": json.loads(row["meta"]), "state": json.loads(row["state"]) if row["state"] else None,
                "report": json.loads(row["report"]) if row["report"] else None}

    def update(self, sid: str, *, status: str | None = None, meta: dict | None = None,
               state: dict | None = None, report: dict | None = None) -> None:
        sets, vals = ["updated=?"], [time.time()]
        for col, val in (("status", status), ("meta", meta), ("state", state), ("report", report)):
            if val is not None:
                sets.append(f"{col}=?")
                vals.append(val if isinstance(val, str) else json.dumps(val, default=str))
        vals.append(sid)
        with self._lock, self._db:
            self._db.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", vals)

    def delete(self, sid: str) -> bool:
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM sessions WHERE id=?", (sid,))
        shutil.rmtree(self.dir / "sessions" / sid, ignore_errors=True)
        return cur.rowcount > 0

    def purge_older_than(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = time.time() - days * 86400
        with self._lock:
            ids = [r["id"] for r in self._db.execute("SELECT id FROM sessions WHERE created<?", (cutoff,))]
        for sid in ids:
            self.delete(sid)
        return len(ids)

    def close(self) -> None:
        with self._lock:
            self._db.close()
