"""
index_codebase.py — Semantic code indexer for the han-solo repo.

Walks the repo, chunks files by semantic boundaries (AST for Python,
paragraphs for Markdown, blocks for JSON/YAML, tag blocks for HTML,
fixed windows for everything else), generates OpenAI embeddings, and
stores chunks in the code_chunks table.

Usage:
    python3 scripts/index_codebase.py [--repo-path PATH] [--dry-run]

    --repo-path PATH  Root of the repo to index (default: this script's parent parent)
    --dry-run         Parse and chunk without calling the embedding API or writing to DB

Triggered manually or via GitHub webhook (POST /api/code/reindex).
"""

import argparse
import ast
import json
import logging
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_PATH    = Path(__file__).parent.parent          # ~/Developer/han-solo
REPO_NAME    = "han-solo"
MCP_URL      = os.environ.get("MCP_URL", "https://han-solo-mcp.onrender.com")
MCP_TOKEN    = os.environ.get("MCP_TOKEN", "RHcpXjeAJlu_DzhYplsLaUOUSGVrU-gceamJQoXb81Q")
OPENAI_KEY   = os.environ.get("OPENAI_API_KEY", "")

EMBED_MODEL  = "text-embedding-3-small"
EMBED_BATCH  = 20          # chunks per embedding API call
WINDOW_LINES = 100         # fallback chunking window
WINDOW_STEP  = 80          # lines to advance per window (20-line overlap)

INDEX_EXTENSIONS = {".py", ".md", ".sh", ".yaml", ".yml", ".json", ".html"}

SKIP_PATHS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".env", "dist", "build", ".mypy_cache", ".pytest_cache",
}
SKIP_FILES = {".env", ".env.local", ".env.example"}

# Specific files to exclude — product docs, design artifacts, not infrastructure code
SKIP_SPECIFIC = {
    "docs/family-circle-overview.html",
    "docs/design/han-solo-design.html",
    "docs/kb-design.html",
}

# JSON/YAML files we care about — skip large data dumps
INDEX_JSON_PATTERNS = {
    "settings", "config", "schema", "template", "manifest",
    "claude", "pyproject", "package", "requirements",
}


# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------

def should_index(path: Path, repo_root: Path = REPO_PATH) -> bool:
    if path.is_symlink():
        return False
    try:
        rel = str(path.relative_to(repo_root))
        if rel in SKIP_SPECIFIC:
            return False
    except ValueError:
        pass
    if path.suffix.lower() not in INDEX_EXTENSIONS:
        return False
    for part in path.parts:
        if part in SKIP_PATHS or part.startswith("."):
            return False
    if path.name in SKIP_FILES:
        return False
    # For JSON, only index files whose name contains a known useful pattern
    if path.suffix.lower() == ".json":
        stem = path.stem.lower()
        if not any(pat in stem for pat in INDEX_JSON_PATTERNS):
            return False
    return True


def collect_files(repo_root: Path) -> list[Path]:
    files = []
    for p in sorted(repo_root.rglob("*")):
        if p.is_file() and should_index(p):
            files.append(p)
    return files


# ---------------------------------------------------------------------------
# Chunking — semantic boundaries per file type
# ---------------------------------------------------------------------------

def chunk_python(text: str) -> list[str]:
    """Split by top-level function/class definitions via AST. Fallback to windows."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return chunk_by_window(text)

    lines = text.splitlines()
    top_nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and getattr(n, "col_offset", 999) == 0
    ]
    if not top_nodes:
        return chunk_by_window(text)

    top_nodes.sort(key=lambda n: n.lineno)
    chunks = []

    # Include module-level preamble (imports, constants) before first node
    first_line = top_nodes[0].lineno - 1
    if first_line > 0:
        preamble = "\n".join(lines[:first_line]).strip()
        if preamble:
            chunks.append(preamble)

    for i, node in enumerate(top_nodes):
        start = node.lineno - 1
        end = top_nodes[i + 1].lineno - 1 if i + 1 < len(top_nodes) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append(body)

    return chunks or chunk_by_window(text)


def chunk_markdown(text: str) -> list[str]:
    """Split on H2/H3 headings; group smaller paragraphs together."""
    import re
    sections = re.split(r"(?m)^(#{1,3} .+)$", text)
    chunks, current = [], ""
    for part in sections:
        if re.match(r"^#{1,3} ", part):
            if current.strip():
                chunks.append(current.strip())
            current = part + "\n"
        else:
            current += part
    if current.strip():
        chunks.append(current.strip())
    # Merge very short sections (< 3 lines) with the next
    merged, i = [], 0
    while i < len(chunks):
        c = chunks[i]
        while i + 1 < len(chunks) and len(c.splitlines()) < 3:
            i += 1
            c += "\n\n" + chunks[i]
        merged.append(c)
        i += 1
    return merged or [text]


def chunk_json_yaml(text: str) -> list[str]:
    """Return the full file as a single chunk — these are usually small config blocks."""
    return [text.strip()] if text.strip() else []


def chunk_html(text: str) -> list[str]:
    """Split on top-level block tags. Fallback to window if parsing fails."""
    import re
    # Split on major structural tags as rough boundaries
    blocks = re.split(r"(?i)(?=<(?:section|article|main|header|footer|div|script|style)[^>]*>)", text)
    chunks = [b.strip() for b in blocks if b.strip()]
    # Merge tiny fragments
    merged, buf = [], ""
    for c in chunks:
        buf = (buf + "\n" + c).strip() if buf else c
        if len(buf.splitlines()) >= 15:
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)
    return merged or chunk_by_window(text)


def chunk_by_window(text: str, window: int = WINDOW_LINES, step: int = WINDOW_STEP) -> list[str]:
    lines = text.splitlines()
    if len(lines) <= window:
        return [text.strip()] if text.strip() else []
    chunks = []
    for start in range(0, len(lines), step):
        block = "\n".join(lines[start:start + window]).strip()
        if block:
            chunks.append(block)
    return chunks


def chunk_file(path: Path, text: str) -> list[str]:
    ext = path.suffix.lower()
    if ext == ".py":
        return chunk_python(text)
    elif ext == ".md":
        return chunk_markdown(text)
    elif ext in {".json", ".yaml", ".yml"}:
        return chunk_json_yaml(text)
    elif ext == ".html":
        return chunk_html(text)
    else:
        return chunk_by_window(text)


# ---------------------------------------------------------------------------
# Embeddings — OpenAI text-embedding-3-small
# ---------------------------------------------------------------------------

def embed_batch(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts. Returns list of vectors."""
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    # API returns results sorted by index
    return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]


def embed_chunks(chunks: list[str]) -> list[list[float]]:
    """Embed all chunks in batches."""
    embeddings = []
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i:i + EMBED_BATCH]
        embeddings.extend(embed_batch(batch))
    return embeddings


# ---------------------------------------------------------------------------
# MCP API — push chunks to DB via han-solo server
# ---------------------------------------------------------------------------

def post_chunks(file_path: str, file_type: str, chunks: list[dict]) -> bool:
    """POST indexed chunks to /api/code/chunks on the MCP server."""
    payload = json.dumps({
        "repo": REPO_NAME,
        "file_path": file_path,
        "file_type": file_type,
        "chunks": chunks,
    }).encode()
    req = urllib.request.Request(
        f"{MCP_URL}/api/code/chunks",
        data=payload,
        headers={
            "Authorization": f"Bearer {MCP_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        logger.error("POST /api/code/chunks failed %s: %s", e.code, e.read())
        return False


def post_log(commit_hash: str, files_indexed: int, chunks_created: int, trigger: str) -> None:
    """POST index completion log."""
    payload = json.dumps({
        "repo": REPO_NAME,
        "commit_hash": commit_hash,
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "trigger": trigger,
    }).encode()
    req = urllib.request.Request(
        f"{MCP_URL}/api/code/index-log",
        data=payload,
        headers={
            "Authorization": f"Bearer {MCP_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception as e:
        logger.warning("Failed to post index log: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def get_commit_hash(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def run(repo_root: Path, dry_run: bool) -> None:
    files = collect_files(repo_root)
    logger.info("Indexing %d files from %s", len(files), repo_root)

    commit_hash = get_commit_hash(repo_root)
    total_chunks = 0
    files_indexed = 0

    for path in files:
        rel = str(path.relative_to(repo_root))
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning("Cannot read %s: %s", rel, e)
            continue

        raw_chunks = chunk_file(path, text)
        if not raw_chunks:
            continue

        if dry_run:
            logger.info("  %s → %d chunks (dry run)", rel, len(raw_chunks))
            total_chunks += len(raw_chunks)
            files_indexed += 1
            continue

        try:
            vectors = embed_chunks(raw_chunks)
        except Exception as e:
            logger.error("Embedding failed for %s: %s", rel, e)
            continue

        chunk_records = [
            {"chunk_index": i, "chunk_text": text, "embedding": vec}
            for i, (text, vec) in enumerate(zip(raw_chunks, vectors))
        ]

        success = post_chunks(rel, path.suffix.lstrip("."), chunk_records)
        if success:
            logger.info("  %s → %d chunks", rel, len(chunk_records))
            total_chunks += len(chunk_records)
            files_indexed += 1
        else:
            logger.error("  %s → failed to store", rel)

    if not dry_run:
        post_log(commit_hash, files_indexed, total_chunks, "manual")

    logger.info("Done — %d files, %d chunks%s", files_indexed, total_chunks, " (dry run)" if dry_run else "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index han-solo codebase for semantic search")
    parser.add_argument("--repo-path", type=Path, default=REPO_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not OPENAI_KEY:
        logger.error("OPENAI_API_KEY not set. Use --dry-run to test chunking without embeddings.")
        sys.exit(1)

    run(args.repo_path, args.dry_run)
