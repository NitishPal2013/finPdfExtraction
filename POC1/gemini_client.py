"""
Gemini API client factory.

We expose a factory function rather than a module-level singleton because each
`asyncio.run()` call (Streamlit fires one per "Run extraction" click) creates
a fresh event loop — and the SDK's internal httpx async client binds to
whichever loop first uses it. Reusing a stale client across loops yields the
classic "<Semaphore> is bound to a different event loop" error or, worse,
silently leaks half-closed connections.

For one-shot CLI runs (single asyncio.run) this is overkill but harmless.
For the Streamlit app it is a correctness requirement.

Usage:
    from .gemini_client import make_async_client
    client = make_async_client()  # call once at the top of every async entry
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


def _resolve_api_key() -> str:
    load_dotenv()
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if key:
        return key
    # Manual fallback: walk up from this file looking for a .env
    for parent in Path(__file__).resolve().parents:
        env_path = parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                for var in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
                    if line.strip().startswith(f"{var}="):
                        return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "Gemini API key not found. Set GOOGLE_API_KEY (or GEMINI_API_KEY) in the "
        "environment, or place a .env file containing one of those at the project root."
    )


_API_KEY = _resolve_api_key()


def make_async_client():
    """Create a fresh Gemini async client bound to the calling event loop.

    Cheap to call: the SDK's internal httpx pool is initialised lazily on
    first use. Always invoke this at the top of an async entry point — never
    cache the returned object across `asyncio.run()` invocations.
    """
    return genai.Client(api_key=_API_KEY).aio
