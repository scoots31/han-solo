CHAT_HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Han Solo</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg: #090806;
      --surface: #131110;
      --border: #2A2520;
      --text: #EDE8E0;
      --text-dim: #6A6058;
      --gold: #E8971C;
      --gold-dim: rgba(232,151,28,.10);
      --gold-border: rgba(232,151,28,.22);
      --scott: #4A90D9;
      --scott-dim: rgba(74,144,217,.10);
      --scott-border: rgba(74,144,217,.22);
      --ted: #5BA85A;
      --ted-dim: rgba(91,168,90,.10);
      --ted-border: rgba(91,168,90,.22);
      --input-bg: #1A1512;
      --send-bg: #E8971C;
      --send-text: #090806;
      --error: #D95040;
    }

    [data-theme="light"] {
      --bg: #F5F0EB;
      --surface: #EDE8E0;
      --border: #D0C8BE;
      --text: #1A1512;
      --text-dim: #9A8E82;
      --gold: #B87010;
      --gold-dim: rgba(184,112,16,.09);
      --gold-border: rgba(184,112,16,.22);
      --scott: #2568BE;
      --scott-dim: rgba(37,104,190,.09);
      --scott-border: rgba(37,104,190,.22);
      --ted: #2E822C;
      --ted-dim: rgba(46,130,44,.09);
      --ted-border: rgba(46,130,44,.22);
      --input-bg: #FFFFFF;
      --send-bg: #B87010;
      --send-text: #FFFFFF;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
      font-size: 15px;
      line-height: 1.55;
      height: 100dvh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* ── Header ─────────────────────────────────────────────────────────── */

    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 18px;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      flex-shrink: 0;
      gap: 12px;
    }

    .header-title {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: var(--gold);
      text-transform: uppercase;
    }

    .header-user {
      font-size: 12px;
      color: var(--text-dim);
      flex: 1;
    }

    .header-actions {
      display: flex;
      gap: 6px;
    }

    .icon-btn {
      background: none;
      border: 1px solid var(--border);
      color: var(--text-dim);
      cursor: pointer;
      padding: 5px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-family: inherit;
      transition: color .12s, border-color .12s;
      white-space: nowrap;
    }

    .icon-btn:hover {
      color: var(--text);
      border-color: var(--text-dim);
    }

    /* ── Layout ──────────────────────────────────────────────────────────── */

    .layout {
      display: flex;
      flex: 1;
      min-height: 0;
    }

    /* ── Chat area ───────────────────────────────────────────────────────── */

    .chat-area {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 20px 18px 8px;
      display: flex;
      flex-direction: column;
      gap: 0;
      scroll-behavior: smooth;
    }

    /* ── Message groups ──────────────────────────────────────────────────── */

    .msg-group {
      margin-bottom: 16px;
    }

    .msg-header {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin-bottom: 5px;
      padding: 0 2px;
    }

    .msg-header.ren   { color: var(--gold); }
    .msg-header.scott { color: var(--scott); }
    .msg-header.ted   { color: var(--ted); }

    .msg-bubbles {
      display: flex;
      flex-direction: column;
      gap: 3px;
    }

    .msg-bubble {
      padding: 9px 13px;
      border-radius: 10px;
      max-width: 74%;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 14px;
      line-height: 1.65;
    }

    /* Ren: left-aligned, gold tint, distinctive treatment */
    .msg-bubble.ren {
      background: var(--gold-dim);
      border: 1px solid var(--gold-border);
      align-self: flex-start;
      border-radius: 3px 10px 10px 10px;
    }

    /* Scott: right-aligned, blue tint */
    .msg-bubble.scott {
      background: var(--scott-dim);
      border: 1px solid var(--scott-border);
      align-self: flex-end;
      border-radius: 10px 3px 10px 10px;
    }

    /* Ted: left-aligned, green tint */
    .msg-bubble.ted {
      background: var(--ted-dim);
      border: 1px solid var(--ted-border);
      align-self: flex-start;
      border-radius: 3px 10px 10px 10px;
    }

    .msg-bubble.loading {
      color: var(--text-dim);
      font-style: italic;
      animation: pulse 1.4s ease-in-out infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: .6; }
      50%       { opacity: 1; }
    }

    /* ── Empty state ─────────────────────────────────────────────────────── */

    .empty-state {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--text-dim);
      gap: 6px;
      text-align: center;
      padding: 48px 32px;
    }

    .empty-glyph {
      font-size: 28px;
      margin-bottom: 4px;
      opacity: .5;
    }

    .empty-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--text);
    }

    .empty-sub {
      font-size: 13px;
    }

    /* ── Input area ──────────────────────────────────────────────────────── */

    .input-area {
      padding: 10px 18px 14px;
      border-top: 1px solid var(--border);
      background: var(--surface);
      display: flex;
      gap: 10px;
      align-items: flex-end;
      flex-shrink: 0;
    }

    .input-wrap {
      flex: 1;
      background: var(--input-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 13px;
      transition: border-color .15s;
    }

    .input-wrap:focus-within {
      border-color: var(--text-dim);
    }

    textarea {
      width: 100%;
      background: none;
      border: none;
      outline: none;
      color: var(--text);
      font-family: inherit;
      font-size: 14px;
      line-height: 1.5;
      resize: none;
      min-height: 21px;
      max-height: 160px;
    }

    textarea::placeholder { color: var(--text-dim); }

    .attach-btn {
      background: none;
      border: none;
      color: var(--text-dim);
      cursor: pointer;
      padding: 4px 6px;
      font-size: 16px;
      line-height: 1;
      flex-shrink: 0;
      display: flex;
      align-items: center;
    }
    .attach-btn:hover { color: var(--text); }

    .file-preview {
      display: none;
      align-items: center;
      gap: 8px;
      padding: 6px 18px;
      background: var(--surface);
      border-top: 1px solid var(--border);
      font-size: 12px;
      color: var(--text-dim);
    }
    .file-preview.visible { display: flex; }
    .file-preview-name { color: var(--text); font-weight: 600; }
    .file-preview-remove {
      background: none;
      border: none;
      color: var(--text-dim);
      cursor: pointer;
      font-size: 14px;
      padding: 0 4px;
      line-height: 1;
    }
    .file-preview-remove:hover { color: var(--text); }

    .send-btn {
      background: var(--send-bg);
      color: var(--send-text);
      border: none;
      border-radius: 8px;
      padding: 9px 18px;
      font-size: 13px;
      font-weight: 700;
      font-family: inherit;
      cursor: pointer;
      flex-shrink: 0;
      transition: opacity .12s;
      letter-spacing: 0.02em;
    }

    .send-btn:hover   { opacity: .88; }
    .send-btn:disabled { opacity: .38; cursor: not-allowed; }

    /* ── Memory panel ────────────────────────────────────────────────────── */

    .memory-panel {
      width: 300px;
      flex-shrink: 0;
      border-left: 1px solid var(--border);
      background: var(--surface);
      overflow-y: auto;
      padding: 16px;
      display: none;
      flex-direction: column;
      gap: 20px;
    }

    .memory-panel.open {
      display: flex;
    }

    .panel-section-title {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      color: var(--text-dim);
      margin-bottom: 6px;
    }

    .panel-block-label {
      font-size: 11px;
      color: var(--text-dim);
      margin-bottom: 4px;
    }

    .panel-block-content {
      font-size: 12px;
      line-height: 1.6;
      color: var(--text);
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 9px 11px;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 180px;
      overflow-y: auto;
    }

    /* ── Login overlay ───────────────────────────────────────────────────── */

    .login-overlay {
      position: fixed;
      inset: 0;
      background: var(--bg);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 200;
    }

    .login-box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 36px 32px;
      width: 360px;
      max-width: 92vw;
    }

    .login-title {
      font-size: 22px;
      font-weight: 700;
      color: var(--gold);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }

    .login-sub {
      font-size: 13px;
      color: var(--text-dim);
      margin-bottom: 24px;
      line-height: 1.5;
    }

    .login-input {
      width: 100%;
      background: var(--input-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 13px;
      color: var(--text);
      font-size: 13px;
      font-family: monospace;
      margin-bottom: 10px;
      outline: none;
      transition: border-color .12s;
    }

    .login-input:focus { border-color: var(--gold); }

    .login-btn {
      width: 100%;
      background: var(--send-bg);
      color: var(--send-text);
      border: none;
      border-radius: 8px;
      padding: 11px;
      font-size: 14px;
      font-weight: 700;
      font-family: inherit;
      cursor: pointer;
      transition: opacity .12s;
    }

    .login-btn:hover { opacity: .88; }

    .login-error {
      font-size: 13px;
      color: var(--error);
      margin-top: 10px;
      min-height: 18px;
    }

    /* ── Session divider ────────────────────────────────────────────────── */

    .session-divider {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 12px 0;
      color: var(--text-dim);
      font-size: 11px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .session-divider::before,
    .session-divider::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--border);
    }

    /* ── Scrollbar ───────────────────────────────────────────────────────── */

    ::-webkit-scrollbar       { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
  </style>
</head>
<body>

<!-- Login overlay -->
<div class="login-overlay" id="loginOverlay">
  <div class="login-box">
    <div class="login-title">Han Solo</div>
    <div class="login-sub">Enter your access token to continue.</div>
    <input type="password" class="login-input" id="tokenInput" placeholder="Bearer token" autocomplete="off" />
    <button class="login-btn" id="loginBtn">Connect</button>
    <div class="login-error" id="loginError"></div>
  </div>
</div>

<!-- App shell (hidden until logged in) -->
<div class="header" id="appShell" style="display:none">
  <div class="header-title">Han Solo</div>
  <div class="header-user" id="headerUser"></div>
  <div class="header-actions">
    <button class="icon-btn" id="newSessionBtn" title="Start a fresh session (memory is preserved)">New session</button>
    <button class="icon-btn" id="themeBtn" title="Toggle theme">Light</button>
    <button class="icon-btn" id="memoryBtn" title="Memory panel">Memory</button>
    <button class="icon-btn" id="logoutBtn" title="Sign out">Sign out</button>
  </div>
</div>

<div class="layout" id="appLayout" style="display:none">
  <div class="chat-area">
    <div class="messages" id="messages">
      <div class="empty-state" id="emptyState">
        <div class="empty-glyph">◈</div>
        <div class="empty-title">Good to see you.</div>
        <div class="empty-sub">Say hello to start your session with Ren.</div>
      </div>
    </div>
    <div class="file-preview" id="filePreview">
      <span>📄</span>
      <span class="file-preview-name" id="filePreviewName"></span>
      <span id="filePreviewSize"></span>
      <button class="file-preview-remove" id="fileRemoveBtn" title="Remove file">×</button>
    </div>
    <div class="input-area">
      <div class="input-wrap">
        <textarea id="msgInput" placeholder="Message Ren…" rows="1"></textarea>
      </div>
      <button class="attach-btn" id="attachBtn" title="Attach a file">📎</button>
      <input type="file" id="fileInput" accept=".txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.yaml,.yml,.html,.css,.sql,.sh,.csv,.toml,.env" style="display:none">
      <button class="send-btn" id="sendBtn">Send</button>
    </div>
  </div>

  <div class="memory-panel" id="memoryPanel">
    <div>
      <div class="panel-section-title">Active Context</div>
      <div class="panel-block-label">project_state</div>
      <div class="panel-block-content" id="panelProject">—</div>
    </div>
    <div>
      <div class="panel-section-title">Memory State</div>
      <div class="panel-block-label">always_loaded_core</div>
      <div class="panel-block-content" id="panelCore">—</div>
    </div>
    <div>
      <div class="panel-section-title">Pending Thoughts</div>
      <div class="panel-block-label">pending_thoughts</div>
      <div class="panel-block-content" id="panelPending">—</div>
    </div>
  </div>
</div>

<script>
'use strict';

// ── State ──────────────────────────────────────────────────────────────────

let token     = null;
let userName  = null;
let sending   = false;
let pollTimer = null;
let panelOpen = false;
let _msgs     = [];        // local copy of history
let _theme    = 'dark';

// ── DOM refs ───────────────────────────────────────────────────────────────

const $ = id => document.getElementById(id);

const loginOverlay  = $('loginOverlay');
const tokenInput    = $('tokenInput');
const loginBtn      = $('loginBtn');
const loginError    = $('loginError');
const appShell      = $('appShell');
const appLayout     = $('appLayout');
const headerUser    = $('headerUser');
const newSessionBtn = $('newSessionBtn');
const themeBtn      = $('themeBtn');
const memoryBtn     = $('memoryBtn');
const logoutBtn     = $('logoutBtn');
const messages      = $('messages');
const emptyState    = $('emptyState');
const msgInput      = $('msgInput');
const sendBtn       = $('sendBtn');
const memoryPanel   = $('memoryPanel');

// ── Init ───────────────────────────────────────────────────────────────────

(function applyTheme() {
  const saved = localStorage.getItem('hs_theme') || 'dark';
  _theme = saved;
  document.documentElement.setAttribute('data-theme', _theme);
  themeBtn.textContent = _theme === 'dark' ? 'Light' : 'Dark';
})();

async function init() {
  const saved = localStorage.getItem('hs_token');
  if (saved) {
    const ok = await tryConnect(saved);
    if (ok) return;
    localStorage.removeItem('hs_token');
  }
  loginOverlay.style.display = 'flex';
}

async function tryConnect(t) {
  try {
    const resp = await apiFetch('/api/me', { method: 'GET' }, t);
    if (!resp.ok) return false;
    const data = await resp.json();
    token    = t;
    userName = data.name;
    localStorage.setItem('hs_token', t);
    loginOverlay.style.display   = 'none';
    appShell.style.display       = 'flex';
    appLayout.style.display      = 'flex';
    headerUser.textContent       = userName;
    await loadHistory();
    startPolling();
    msgInput.focus();
    return true;
  } catch {
    return false;
  }
}

// ── Auth ───────────────────────────────────────────────────────────────────

async function doLogin() {
  const t = tokenInput.value.trim();
  loginError.textContent = '';
  if (!t) return;
  loginBtn.disabled = true;
  loginBtn.textContent = 'Connecting…';
  const ok = await tryConnect(t);
  if (!ok) {
    loginError.textContent = 'Invalid token. Check and try again.';
    loginBtn.disabled = false;
    loginBtn.textContent = 'Connect';
  }
}

function doLogout() {
  localStorage.removeItem('hs_token');
  stopPolling();
  location.reload();
}

loginBtn.addEventListener('click', doLogin);
tokenInput.addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
logoutBtn.addEventListener('click', doLogout);

// ── Session reset ──────────────────────────────────────────────────────────

function addSessionDivider(label = 'New session — memory intact') {
  const div = document.createElement('div');
  div.className = 'session-divider';
  div.textContent = label;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

async function newSession() {
  if (newSessionBtn.disabled) return;
  newSessionBtn.disabled = true;
  newSessionBtn.textContent = 'Resetting…';
  try {
    const resp = await apiFetch('/api/reset-session', { method: 'POST' });
    if (resp.ok) {
      _msgs = [];
      renderMessages();
      addSessionDivider();
    }
  } catch {}
  newSessionBtn.disabled = false;
  newSessionBtn.textContent = 'New session';
  msgInput.focus();
}

newSessionBtn.addEventListener('click', newSession);

// ── Theme ──────────────────────────────────────────────────────────────────

themeBtn.addEventListener('click', () => {
  _theme = _theme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', _theme);
  localStorage.setItem('hs_theme', _theme);
  themeBtn.textContent = _theme === 'dark' ? 'Light' : 'Dark';
});

// ── Fetch helper ───────────────────────────────────────────────────────────

function apiFetch(path, opts = {}, tok = token) {
  return fetch(path, {
    ...opts,
    headers: {
      'Authorization': `Bearer ${tok}`,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
}

// ── Message rendering ──────────────────────────────────────────────────────

function whoClass(name) {
  const n = name.toLowerCase();
  if (n === 'ren') return 'ren';
  if (n === 'scott') return 'scott';
  if (n === 'ted') return 'ted';
  return 'scott'; // fallback
}

function renderMessages() {
  // Clear everything below emptyState
  while (messages.lastChild && messages.lastChild !== emptyState) {
    messages.removeChild(messages.lastChild);
  }

  if (_msgs.length === 0) {
    emptyState.style.display = 'flex';
    return;
  }
  emptyState.style.display = 'none';

  // Group consecutive messages from the same sender
  const groups = [];
  let cur = null;
  for (const m of _msgs) {
    if (!cur || cur.name !== m.name) {
      cur = { name: m.name, cls: whoClass(m.name), texts: [] };
      groups.push(cur);
    }
    cur.texts.push(m.text);
  }

  for (const g of groups) {
    const group = document.createElement('div');
    group.className = 'msg-group';

    const header = document.createElement('div');
    header.className = `msg-header ${g.cls}`;
    header.textContent = g.name;
    group.appendChild(header);

    const bubblesWrap = document.createElement('div');
    bubblesWrap.className = 'msg-bubbles';

    for (const text of g.texts) {
      const bubble = document.createElement('div');
      bubble.className = `msg-bubble ${g.cls}`;
      bubble.textContent = text;
      bubblesWrap.appendChild(bubble);
    }

    group.appendChild(bubblesWrap);
    messages.appendChild(group);
  }

  messages.scrollTop = messages.scrollHeight;
}

// ── History ────────────────────────────────────────────────────────────────

async function loadHistory() {
  try {
    const resp = await apiFetch('/api/history');
    if (!resp.ok) return;
    const data = await resp.json();
    _msgs = data;
    renderMessages();
  } catch {}
}

function startPolling() {
  pollTimer = setInterval(async () => {
    if (sending) return;
    try {
      const resp = await apiFetch('/api/history');
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.length !== _msgs.length) {
        _msgs = data;
        renderMessages();
      }
    } catch {}
  }, 5000);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
}

// ── File attachment ─────────────────────────────────────────────────────────

const attachBtn     = $('attachBtn');
const fileInput     = $('fileInput');
const filePreview   = $('filePreview');
const filePreviewName = $('filePreviewName');
const filePreviewSize = $('filePreviewSize');
const fileRemoveBtn = $('fileRemoveBtn');

const MAX_FILE_BYTES = 100 * 1024; // 100 KB
let attachment = null; // { name, content } or null

function formatBytes(n) {
  return n < 1024 ? n + ' B' : (n / 1024).toFixed(1) + ' KB';
}

function clearAttachment() {
  attachment = null;
  fileInput.value = '';
  filePreview.classList.remove('visible');
}

attachBtn.addEventListener('click', () => fileInput.click());

fileRemoveBtn.addEventListener('click', clearAttachment);

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (!file) return;

  if (file.size > MAX_FILE_BYTES) {
    alert(`File too large (${formatBytes(file.size)}). Max 100 KB.`);
    fileInput.value = '';
    return;
  }

  const reader = new FileReader();
  reader.onload = e => {
    attachment = { name: file.name, content: e.target.result };
    filePreviewName.textContent = file.name;
    filePreviewSize.textContent = formatBytes(file.size);
    filePreview.classList.add('visible');
  };
  reader.readAsText(file);
});

// ── Send ───────────────────────────────────────────────────────────────────

async function sendMessage() {
  const text = msgInput.value.trim();
  if ((!text && !attachment) || sending) return;

  sending = true;
  sendBtn.disabled = true;
  msgInput.value = '';
  msgInput.style.height = 'auto';

  const currentAttachment = attachment;
  clearAttachment();

  // Optimistic: show user message (include filename if attached)
  const displayText = currentAttachment
    ? (text ? `${text}\n\n📄 ${currentAttachment.name}` : `📄 ${currentAttachment.name}`)
    : text;
  _msgs.push({ role: 'user', name: userName, text: displayText });
  renderMessages();

  // Loading indicator
  const loadId = 'loading-' + Date.now();
  addLoading(loadId);

  try {
    const body = { message: text };
    if (currentAttachment) body.attachment = currentAttachment;

    const resp = await apiFetch('/api/send', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    removeLoading(loadId);

    if (resp.ok) {
      const data = await resp.json();
      if (data.session_reset) {
        // Auto-rollover fired before this message — clear UI and show divider
        _msgs = [];
        renderMessages();
        addSessionDivider('Session refreshed — memory intact');
      }
      if (data.response) {
        _msgs.push({ role: 'assistant', name: 'Ren', text: data.response });
        renderMessages();
      }
    } else {
      _msgs.push({ role: 'assistant', name: 'Ren', text: '(Something went wrong — try again)' });
      renderMessages();
    }
  } catch {
    removeLoading(loadId);
    _msgs.push({ role: 'assistant', name: 'Ren', text: '(Connection error — try again)' });
    renderMessages();
  } finally {
    sending = false;
    sendBtn.disabled = false;
    msgInput.focus();
  }
}

function addLoading(id) {
  const group = document.createElement('div');
  group.className = 'msg-group';
  group.id = id;

  const header = document.createElement('div');
  header.className = 'msg-header ren';
  header.textContent = 'Ren';
  group.appendChild(header);

  const bubblesWrap = document.createElement('div');
  bubblesWrap.className = 'msg-bubbles';
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble ren loading';
  bubble.textContent = 'thinking…';
  bubblesWrap.appendChild(bubble);
  group.appendChild(bubblesWrap);

  messages.appendChild(group);
  messages.scrollTop = messages.scrollHeight;
}

function removeLoading(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

sendBtn.addEventListener('click', sendMessage);

msgInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

msgInput.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 160) + 'px';
});

// ── Memory panel ───────────────────────────────────────────────────────────

memoryBtn.addEventListener('click', async () => {
  panelOpen = !panelOpen;
  memoryPanel.classList.toggle('open', panelOpen);
  memoryBtn.textContent = panelOpen ? 'Close' : 'Memory';
  if (panelOpen) await loadMemoryPanel();
});

async function loadMemoryPanel() {
  try {
    const resp = await apiFetch('/api/memory-panel');
    if (!resp.ok) return;
    const data = await resp.json();
    const blocks = data.blocks || data;

    const find = label => {
      const b = blocks.find(b => b.label === label);
      return b ? b.value || '—' : '—';
    };

    $('panelProject').textContent = find('project_state');
    $('panelCore').textContent    = find('always_loaded_core');
    $('panelPending').textContent = find('pending_thoughts');
  } catch {
    $('panelCore').textContent = 'Error loading memory.';
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────

init();
</script>

</body>
</html>"""
