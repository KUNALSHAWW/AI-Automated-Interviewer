"""Launcher kept for the old `python server.py` workflow. Use `uvicorn app.main:app` in production."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                reload=os.getenv("RELOAD", "0") == "1", log_level="info")
