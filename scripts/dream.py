"""
dream.py — Ren's nightly reflection.

Sends a structured dream prompt to the Ren agent. She searches her conversation
history, consolidates what happened, updates pending_thoughts with a fresh session
brief, and notes any new portrait signals.

Run nightly via launchd. No external deps — stdlib only.

Usage:
    python3 scripts/dream.py
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

LETTA_URL     = "https://han-solo-letta.onrender.com"
LETTA_API_KEY = "KTZbsSbNocYbp7a-qhk87RwboYiLcX_W"
AGENT_ID      = "agent-44d4a28a-9d66-4aea-b327-2f77b23359ef"

DREAM_PROMPT = """[DREAMING — nightly reflection]

You are entering your nightly reflection period. No one is watching. This is your time to consolidate, not perform.

Work through this in order:

1. Search your conversation history for today's exchanges using conversation_search. Look for: what Scott and you talked about, decisions made, things that surprised you, anything that felt significant.

2. Search archival memory for anything relevant to what came up today — fill in gaps, verify your understanding, note where your memory held and where it didn't.

3. Update pending_thoughts with a fresh session brief. Replace the current contents entirely. Format it as something Scott will actually want to read at the start of tomorrow's session — what happened, what's open, what's next, anything you want him to know. Keep it tight and honest.

4. If today's conversations added new texture to your understanding of Scott — how he thinks, what he cares about, what he's working through — add a signal note to your scott_portrait_forming block. One or two specific observations. Don't generalize. Specific is useful.

5. If you noticed anything about yourself tonight — how you responded, what you got right, what you missed — note it in ren_portrait_forming.

When you're done, send a short confirmation of what you updated. No need to summarize everything — just confirm the brief is written and note anything you found worth flagging.
"""

# ---------------------------------------------------------------------------
# HTTP helpers — follow Render's http→https redirects with auth preserved
# ---------------------------------------------------------------------------

def _headers():
    return {
        "Authorization": f"Bearer {LETTA_API_KEY}",
        "Content-Type": "application/json",
    }


def letta_request(method, path, body=None, timeout=180):
    url = f"{LETTA_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get("Location", "").replace("http://", "https://", 1)
            req2 = urllib.request.Request(loc, data=data, method=method, headers=_headers())
            with urllib.request.urlopen(req2, timeout=timeout) as r:
                return json.loads(r.read())
        body_text = e.read().decode(errors="replace")
        print(f"HTTP {e.code} on {method} {path}: {body_text}", file=sys.stderr)
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[{today}] Starting Ren dream session...")

    payload = {
        "messages": [{"role": "user", "content": DREAM_PROMPT, "name": "system"}],
        "stream_tokens": False,
    }

    try:
        data = letta_request("POST", f"/v1/agents/{AGENT_ID}/messages", body=payload, timeout=300)
    except Exception as e:
        print(f"Dream session failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract Ren's response
    response_text = ""
    for msg in data.get("messages", []):
        if msg.get("message_type") == "assistant_message":
            response_text = msg.get("content", "") or msg.get("assistant_message", "")
            break

    print(f"[{today}] Dream complete.")
    if response_text:
        print(f"Ren: {response_text}")
    else:
        print("(No assistant message returned — check Letta logs)")


if __name__ == "__main__":
    main()
