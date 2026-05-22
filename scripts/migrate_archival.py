"""One-shot script to copy archival passages from ren-v1 to ren-v2."""
import json, urllib.request, urllib.error, time, sys

import os

LETTA_URL = os.environ.get("LETTA_URL", 'https://han-solo-letta.onrender.com')
LETTA_API_KEY = os.environ["LETTA_API_KEY"]
OLD_ID = 'agent-44d4a28a-9d66-4aea-b327-2f77b23359ef'
NEW_ID = 'agent-fe4a3d5b-bb51-458e-92f1-6a1ee5b0ce94'

headers = {'Authorization': f'Bearer {LETTA_API_KEY}', 'Content-Type': 'application/json'}

def req(method, path, body=None, timeout=90):
    url = f'{LETTA_URL}{path}'
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307, 308):
            loc = e.headers.get('Location', '').replace('http://', 'https://', 1)
            r2 = urllib.request.Request(loc, data=data, method=method, headers=headers)
            with urllib.request.urlopen(r2, timeout=timeout) as resp:
                return json.loads(resp.read())
        print(f'HTTP {e.code}: {e.read().decode(errors="replace")[:300]}')
        raise

passages = []
limit = 50
after = None
page = 0
print('Fetching from ren-v1...')
while True:
    path = f'/v1/agents/{OLD_ID}/archival-memory?limit={limit}'
    if after:
        path += f'&after={after}'
    batch = req('GET', path)
    if isinstance(batch, dict):
        batch = batch.get('passages', [])
    if not batch:
        break
    passages.extend(batch)
    print(f'  Page {page}: {len(batch)} (total {len(passages)})')
    if len(batch) < limit:
        break
    after = batch[-1].get('id')
    page += 1

print(f'Total: {len(passages)} passages')
errors = 0
for i, p in enumerate(passages):
    text = p.get('text', '')
    if not text:
        continue
    try:
        req('POST', f'/v1/agents/{NEW_ID}/archival-memory', body={'text': text})
        if (i + 1) % 10 == 0:
            print(f'  Inserted {i+1}/{len(passages)}')
        time.sleep(0.4)
    except Exception as e:
        print(f'  Error on {i}: {e}', file=sys.stderr)
        errors += 1
        time.sleep(1)

print(f'Done: {len(passages) - errors}/{len(passages)} inserted, {errors} errors')
