"""
File-upload utilities backed by the Gemini Files API.

Both the concurrency semaphore AND the Gemini client are constructed *inside*
the public coroutines (not at module scope) so they bind to the currently
running event loop. This is required when the same Python process drives
multiple `asyncio.run()` invocations — e.g. inside a Streamlit app where each
"Run" click spins up a fresh loop. Module-level asyncio primitives die on the
second invocation with "bound to a different event loop".

`upload_files` and `delete_files` accept an optional `client` so callers
running multiple operations in the same loop can share one client.
"""
from __future__ import annotations

import asyncio
import sys as _sys
from pathlib import Path as _Path

from google.genai import types

# See run.py for rationale — keep absolute POC1.* imports robust against the
# module being loaded outside its package context.
_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from POC1.gemini_client import make_async_client

_MAX_CONCURRENT_UPLOADS = 20
_UPLOAD_RETRIES = 3


async def _upload_one_with_retry(
    client,
    semaphore: asyncio.Semaphore,
    path: str,
    max_retries: int = _UPLOAD_RETRIES,
) -> types.File:
    """Upload one file with capped retries and exponential backoff. The semaphore
    is shared with sibling uploads to bound concurrency."""
    async with semaphore:
        for attempt in range(max_retries):
            try:
                return await client.files.upload(
                    file=path, config={"display_name": path}
                )
            except Exception as e:  # noqa: BLE001
                if attempt == max_retries - 1:
                    print(f"Failed to upload {path} after {max_retries} attempts: {e}")
                    raise
                wait = 2 ** attempt  # 1s, 2s
                print(
                    f"Upload attempt {attempt + 1} failed for {path}: {e}. "
                    f"Retrying in {wait}s..."
                )
                await asyncio.sleep(wait)


async def upload_files(file_paths: list[str], *, client=None) -> list[types.File]:
    """Upload many files concurrently; preserves input order by display_name.

    Pass `client` to share one Gemini client across upload + generation calls
    inside the same `asyncio.run()`. If omitted, a fresh client is built
    bound to the current loop.
    """
    if client is None:
        client = make_async_client()
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_UPLOADS)
    uploaded = await asyncio.gather(*[
        _upload_one_with_retry(client, semaphore, p) for p in file_paths
    ])
    uploaded.sort(key=lambda f: file_paths.index(f.display_name))
    return uploaded


async def delete_files(files: list[types.File], *, client=None) -> None:
    """Best-effort cleanup — logs failures but never raises."""
    if not files:
        return
    if client is None:
        client = make_async_client()
    results = await asyncio.gather(
        *[client.files.delete(name=f.name) for f in files],
        return_exceptions=True,
    )
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Failed to delete {files[idx].name}: {result}")
