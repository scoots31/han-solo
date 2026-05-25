"""
Codebase tool — semantic search across the han-solo codebase.

Lets Ren search the indexed repo by intent, not just keywords.
Embeddings stored in code_chunks; cosine similarity computed in-memory.
"""
import json
import math
import os
import urllib.request
from mcp.server.fastmcp import FastMCP

from .. import db

EMBED_MODEL = "text-embedding-3-small"
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY", "")
REPO_NAME   = "han-solo"


def _embed(text: str) -> list[float]:
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    payload = json.dumps({"model": EMBED_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["data"][0]["embedding"]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def register(server: FastMCP) -> None:

    @server.tool()
    async def search_code(query: str, limit: int = 5) -> str:
        """
        Search the han-solo codebase by intent using semantic similarity.

        Returns the most relevant code chunks with their file paths and content.
        Use this when you want to understand how something works, find where a
        behavior is implemented, or trace the impact of a change.

        query: Natural language question or description of what you're looking for.
        limit: Max results to return (default 5, max 10).
        """
        if not query.strip():
            return "Error: query is required"
        limit = min(max(1, limit), 10)

        try:
            query_vec = _embed(query)
        except Exception as e:
            return f"Error generating query embedding: {e}"

        chunks = await db.get_all_code_chunks(REPO_NAME)
        if not chunks:
            return "No code chunks indexed yet. Run scripts/index_codebase.py first."

        scored = []
        for chunk in chunks:
            emb = chunk.get("embedding")
            if not emb:
                continue
            score = _cosine(query_vec, emb)
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        if not top:
            return f"No results found for '{query}'"

        lines = [f"Top {len(top)} results for: {query}\n"]
        for score, chunk in top:
            lines.append(
                f"── {chunk['file_path']}  (chunk {chunk['chunk_index']}, score {score:.3f})\n"
                f"{chunk['chunk_text'][:800]}"
                + (" …" if len(chunk['chunk_text']) > 800 else "")
                + "\n"
            )
        return "\n".join(lines)
