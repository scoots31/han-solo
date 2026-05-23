APP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Han Solo</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }

    body {
      --bg: #ffffff;
      --sidebar-bg: #e8e8e8;
      --sidebar-border: #dedede;
      --divider: #ebebeb;
      --accent: #bd8c7d;
      --accent-light: #f7efed;
      --gold: #d1bfa7;
      --onyx: #49494b;
      --silver: #8e8e90;
      --text-primary: #111111;
      --text-secondary: #555555;
      --text-meta: #aaaaaa;
      --card-bg: #f9f9f9;
      --card-border: #e8e8e8;
      --msg-ren-bg: rgba(189,140,125,.10);
      --msg-ren-border: rgba(189,140,125,.28);
      --msg-scott-bg: #f4f4f4;
      --msg-scott-border: #e0e0e0;
      --input-bg: #f4f4f4;
      --input-border: #e8e8e8;
      --error: #d0453a;
      font-family: 'Space Grotesk', sans-serif;
      background: var(--bg);
      color: var(--text-primary);
      height: 100dvh;
      overflow: hidden;
    }

    /* ── APP SHELL ── */
    .app { display: flex; height: 100dvh; overflow: hidden; }

    /* ── SIDEBAR ── */
    .sidebar {
      width: 220px; min-width: 220px;
      background: var(--sidebar-bg);
      border-right: 1px solid var(--sidebar-border);
      display: flex; flex-direction: column;
    }
    .sidebar-logo {
      padding: 20px 18px 16px;
      border-bottom: 1px solid var(--sidebar-border);
      display: flex; align-items: center; gap: 9px;
      flex-shrink: 0;
    }
    .logo-badge {
      width: 26px; height: 26px; background: #111; border-radius: 6px;
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .logo-badge span { font-size: 9px; font-weight: 700; color: #fff; }
    .logo-name { font-size: 13px; font-weight: 600; color: var(--text-primary); letter-spacing: -.01em; }

    .sidebar-nav { flex: 1; padding: 10px 0; overflow-y: auto; }
    .nav-section { margin-bottom: 2px; }
    .nav-section-label {
      padding: 8px 18px 3px;
      font-size: 9.5px; font-weight: 700; letter-spacing: .14em;
      text-transform: uppercase;
    }
    .nav-section:nth-child(1) .nav-section-label { color: var(--accent); }
    .nav-section:nth-child(2) .nav-section-label { color: var(--onyx); }
    .nav-section:nth-child(3) .nav-section-label { color: var(--silver); }
    .nav-section:nth-child(4) .nav-section-label { color: #b5a090; }

    .nav-item {
      display: flex; align-items: center; gap: 8px;
      padding: 7px 12px; margin: 0 6px; border-radius: 6px;
      cursor: pointer; transition: background .12s;
    }
    .nav-item:hover { background: rgba(0,0,0,.05); }
    .nav-item.active { background: var(--accent-light); }
    .nav-item.disabled { opacity: .38; pointer-events: none; }
    .nav-icon { width: 14px; height: 14px; color: var(--text-meta); flex-shrink: 0; display: flex; align-items: center; }
    .nav-item.active .nav-icon { color: var(--accent); }
    .nav-label { font-size: 12.5px; color: var(--text-secondary); }
    .nav-item.active .nav-label { color: var(--accent); font-weight: 500; }
    .nav-soon { margin-left: auto; font-size: 9px; color: var(--text-meta); font-weight: 600; letter-spacing: .04em; }

    .sidebar-footer {
      padding: 12px 18px;
      border-top: 1px solid var(--sidebar-border);
      flex-shrink: 0;
    }
    .user-row { display: flex; align-items: center; gap: 8px; }
    .user-avatar {
      width: 28px; height: 28px; border-radius: 50%;
      background: var(--onyx); color: #fff;
      display: flex; align-items: center; justify-content: center;
      font-size: 11px; font-weight: 700; flex-shrink: 0;
    }
    .user-name { font-size: 12.5px; font-weight: 600; color: var(--text-primary); }
    .user-meta { font-size: 11px; color: var(--text-meta); }
    .logout-btn {
      margin-left: auto; font-size: 13px; color: var(--text-meta);
      background: none; border: none; cursor: pointer; padding: 2px 4px;
      line-height: 1;
    }
    .logout-btn:hover { color: var(--text-primary); }

    /* ── MAIN ── */
    .main { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }

    /* ── SCREENS ── */
    .screen { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
    .screen.hidden { display: none; }

    .screen-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 16px 22px 14px;
      border-bottom: 1px solid var(--divider);
      flex-shrink: 0;
    }
    .screen-title {
      font-size: 16px; font-weight: 600; color: var(--text-primary);
      border-left: 3px solid var(--accent); padding-left: 10px;
    }
    .screen-sub { font-size: 11px; color: var(--text-meta); margin-top: 2px; padding-left: 13px; }
    .screen-actions { display: flex; align-items: center; gap: 8px; }

    .btn-secondary {
      font-family: inherit; font-size: 11.5px; font-weight: 500;
      padding: 5px 12px; border-radius: 6px;
      border: 1px solid var(--card-border); background: var(--card-bg);
      color: var(--text-secondary); cursor: pointer; transition: all .12s;
    }
    .btn-secondary:hover { border-color: var(--accent); color: var(--accent); }

    /* ── CHAT ── */
    .messages {
      flex: 1; overflow-y: auto;
      padding: 20px 22px 10px;
      display: flex; flex-direction: column;
      scroll-behavior: smooth;
    }
    .msg-group { margin-bottom: 14px; }
    .msg-header {
      font-size: 10.5px; font-weight: 700; letter-spacing: .08em;
      text-transform: uppercase; margin-bottom: 5px; padding: 0 2px;
    }
    .msg-header.ren   { color: var(--accent); }
    .msg-header.scott { color: var(--onyx); }
    .msg-header.ted   { color: var(--silver); }
    .msg-bubbles { display: flex; flex-direction: column; gap: 3px; }
    .msg-bubble {
      padding: 9px 13px; border-radius: 10px;
      max-width: 74%; white-space: pre-wrap; word-break: break-word;
      font-size: 13.5px; line-height: 1.65;
    }
    .msg-bubble.ren {
      background: var(--msg-ren-bg); border: 1px solid var(--msg-ren-border);
      align-self: flex-start; border-radius: 3px 10px 10px 10px;
    }
    .msg-bubble.scott {
      background: var(--msg-scott-bg); border: 1px solid var(--msg-scott-border);
      align-self: flex-end; border-radius: 10px 3px 10px 10px;
    }
    .msg-bubble.ted {
      background: rgba(142,142,144,.1); border: 1px solid rgba(142,142,144,.25);
      align-self: flex-start; border-radius: 3px 10px 10px 10px;
    }
    .msg-bubble.loading {
      color: var(--text-meta); font-style: italic;
      animation: pulse 1.4s ease-in-out infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }

    .session-divider {
      display: flex; align-items: center; gap: 10px;
      margin: 10px 0; color: var(--text-meta);
      font-size: 10.5px; letter-spacing: .07em; text-transform: uppercase;
    }
    .session-divider::before, .session-divider::after {
      content: ''; flex: 1; height: 1px; background: var(--divider);
    }
    .empty-state {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      color: var(--text-meta); gap: 6px; text-align: center; padding: 48px 32px;
    }
    .empty-glyph { font-size: 26px; margin-bottom: 4px; opacity: .4; }
    .empty-title { font-size: 15px; font-weight: 600; color: var(--text-secondary); }
    .empty-sub { font-size: 13px; }

    .file-preview {
      display: none; align-items: center; gap: 8px;
      padding: 8px 22px; border-top: 1px solid var(--divider);
      font-size: 12px; color: var(--text-meta); background: var(--card-bg);
    }
    .file-preview.visible { display: flex; }
    .file-preview-name { color: var(--text-primary); font-weight: 500; }
    .file-remove { background: none; border: none; color: var(--text-meta); cursor: pointer; font-size: 14px; padding: 0 4px; }
    .file-remove:hover { color: var(--text-primary); }

    .input-area {
      padding: 10px 22px 16px;
      border-top: 1px solid var(--divider);
      display: flex; gap: 10px; align-items: flex-end; flex-shrink: 0;
    }
    .input-wrap {
      flex: 1; background: var(--input-bg);
      border: 1px solid var(--input-border); border-radius: 10px;
      padding: 9px 13px; transition: border-color .15s;
    }
    .input-wrap:focus-within { border-color: var(--accent); }
    textarea {
      width: 100%; background: none; border: none; outline: none;
      color: var(--text-primary); font-family: inherit;
      font-size: 13.5px; line-height: 1.5; resize: none;
      min-height: 21px; max-height: 140px;
    }
    textarea::placeholder { color: var(--text-meta); }
    .attach-btn {
      background: none; border: none; color: var(--text-meta);
      cursor: pointer; padding: 4px 6px; font-size: 16px;
      flex-shrink: 0; display: flex; align-items: center;
    }
    .attach-btn:hover { color: var(--text-secondary); }
    .mic-btn {
      background: none; border: none; color: var(--text-meta);
      cursor: pointer; padding: 4px 6px; font-size: 16px;
      flex-shrink: 0; display: flex; align-items: center; transition: color .15s;
    }
    .mic-btn:hover { color: var(--text-secondary); }
    .mic-btn.listening { color: #e05555; animation: mic-pulse 1s infinite; }
    @keyframes mic-pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    .speak-btn {
      background: none; border: none; color: var(--text-meta);
      cursor: pointer; font-size: 11px; padding: 2px 4px; margin-left: 5px;
      opacity: 0; transition: opacity .15s; vertical-align: middle; flex-shrink: 0;
    }
    .msg-bubble:hover .speak-btn { opacity: 1; }
    .speak-btn.playing { color: var(--accent); opacity: 1; }
    .btn-secondary.voice-on { color: var(--accent); border-color: var(--accent); }
    .send-btn {
      background: var(--accent); color: #fff; border: none;
      border-radius: 8px; padding: 9px 18px;
      font-size: 13px; font-weight: 600; font-family: inherit;
      cursor: pointer; flex-shrink: 0; transition: opacity .12s;
    }
    .send-btn:hover { opacity: .88; }
    .send-btn:disabled { opacity: .38; cursor: not-allowed; }

    /* ── MEMORY SCREEN ── */
    .memory-body {
      flex: 1; overflow-y: auto;
      padding: 20px 22px; display: flex; flex-direction: column; gap: 16px;
    }
    .mem-block {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 8px; padding: 16px;
    }
    .mem-block-label {
      font-size: 10px; font-weight: 700; letter-spacing: .12em;
      text-transform: uppercase; color: var(--text-meta); margin-bottom: 10px;
    }
    .mem-block-content {
      font-size: 12.5px; line-height: 1.65; color: var(--text-primary);
      white-space: pre-wrap; word-break: break-word;
      max-height: 220px; overflow-y: auto;
    }
    .mem-state { font-size: 12.5px; color: var(--text-meta); font-style: italic; }

    .jobs-row { display: flex; align-items: center; gap: 10px; }
    .jobs-status {
      font-size: 11.5px; font-weight: 600; padding: 3px 10px; border-radius: 20px;
    }
    .jobs-status.running { background: rgba(189,140,125,.15); color: var(--accent); }
    .jobs-status.paused  { background: rgba(142,142,144,.15); color: var(--silver); }
    .jobs-toggle {
      font-family: inherit; font-size: 11px; font-weight: 600;
      padding: 4px 12px; border-radius: 5px;
      border: 1px solid var(--card-border); background: var(--bg);
      color: var(--text-secondary); cursor: pointer; transition: all .12s;
    }
    .jobs-toggle:hover { border-color: var(--accent); color: var(--accent); }
    .jobs-toggle:disabled { opacity: .5; cursor: not-allowed; }

    /* ── NOTECARDS SCREEN ── */
    .nc-filter-bar {
      display: flex; gap: 6px; padding: 12px 22px;
      border-bottom: 1px solid var(--divider); flex-shrink: 0;
    }
    .nc-filter-btn {
      font-family: inherit; font-size: 11.5px; font-weight: 500;
      padding: 4px 12px; border-radius: 20px;
      border: 1px solid var(--card-border); background: var(--card-bg);
      color: var(--text-secondary); cursor: pointer; transition: all .12s;
    }
    .nc-filter-btn:hover { border-color: var(--accent); color: var(--accent); }
    .nc-filter-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
    .nc-filter-btn.active.archived { background: var(--silver); border-color: var(--silver); }

    .nc-list { flex: 1; overflow-y: auto; padding: 12px 22px; display: flex; flex-direction: column; gap: 8px; }
    .nc-empty { padding: 48px 0; text-align: center; color: var(--text-meta); font-size: 13px; }

    .nc-card {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 8px; padding: 13px 15px;
      display: flex; flex-direction: column; gap: 8px;
    }
    .nc-card-top { display: flex; align-items: flex-start; gap: 10px; }
    .nc-creator {
      width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center;
      font-size: 9px; font-weight: 700; margin-top: 1px;
    }
    .nc-creator.scott { background: var(--onyx); color: #fff; }
    .nc-creator.ren   { background: var(--accent); color: #fff; }
    .nc-creator.ted   { background: var(--silver); color: #fff; }
    .nc-text { font-size: 13px; line-height: 1.6; color: var(--text-primary); flex: 1; }
    .nc-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
    .nc-status {
      font-size: 10px; font-weight: 700; letter-spacing: .06em;
      text-transform: uppercase; padding: 2px 7px; border-radius: 3px;
    }
    .nc-status.active    { background: rgba(189,140,125,.15); color: var(--accent); }
    .nc-status.completed { background: rgba(73,73,75,.1);     color: var(--onyx); }
    .nc-status.archived  { background: rgba(142,142,144,.12); color: var(--silver); }

    .nc-card-footer { display: flex; align-items: center; justify-content: space-between; }
    .nc-date { font-size: 11px; color: var(--text-meta); }
    .nc-actions { display: flex; gap: 6px; }
    .nc-action-btn {
      font-family: inherit; font-size: 11px; font-weight: 500;
      padding: 3px 10px; border-radius: 4px;
      border: 1px solid var(--card-border); background: var(--bg);
      color: var(--text-secondary); cursor: pointer; transition: all .12s;
    }
    .nc-action-btn:hover { border-color: var(--accent); color: var(--accent); }

    /* ── NOTECARD PICKER (mid-chat) ── */
    .nc-picker-wrap { position: relative; flex-shrink: 0; }
    .nc-picker-btn {
      background: none; border: none; color: var(--text-meta);
      cursor: pointer; padding: 4px 6px; font-size: 15px; line-height: 1;
      display: flex; align-items: center;
    }
    .nc-picker-btn:hover { color: var(--accent); }
    .nc-picker {
      display: none; position: absolute; bottom: calc(100% + 8px); left: 0;
      width: 320px; max-height: 280px; overflow-y: auto;
      background: var(--bg); border: 1px solid var(--card-border);
      border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,.10);
      z-index: 50;
    }
    .nc-picker.open { display: block; }
    .nc-picker-header {
      padding: 10px 14px 8px; font-size: 10px; font-weight: 700;
      letter-spacing: .1em; text-transform: uppercase; color: var(--text-meta);
      border-bottom: 1px solid var(--divider);
    }
    .nc-picker-item {
      padding: 10px 14px; cursor: pointer; border-bottom: 1px solid var(--divider);
      transition: background .1s;
    }
    .nc-picker-item:last-child { border-bottom: none; }
    .nc-picker-item:hover { background: var(--accent-light); }
    .nc-picker-item-text { font-size: 12.5px; color: var(--text-primary); line-height: 1.5; }
    .nc-picker-item-meta { font-size: 10.5px; color: var(--text-meta); margin-top: 2px; }
    .nc-picker-empty { padding: 20px 14px; font-size: 12.5px; color: var(--text-meta); }

    /* ── SOLO BUILDER SCREEN ── */
    .sbf-section { display: flex; flex-direction: column; gap: 12px; }
    .sbf-section-label {
      font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
      color: var(--text-meta); padding-bottom: 2px;
      border-bottom: 1px solid var(--card-border);
    }
    .sbf-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
    .sbf-card {
      display: flex; align-items: flex-start; gap: 10px;
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 8px; padding: 14px; text-decoration: none;
      color: var(--text-primary); transition: border-color .15s, background .15s;
    }
    .sbf-card:hover { border-color: var(--accent); background: var(--accent-light); }
    .sbf-card-icon { font-size: 18px; flex-shrink: 0; line-height: 1; margin-top: 1px; }
    .sbf-card-title { font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.3; }
    .sbf-card-sub { font-size: 11.5px; color: var(--text-meta); margin-top: 3px; line-height: 1.4; }
    .sbf-card-phase { align-items: center; }
    .sbf-phase-badge {
      flex-shrink: 0; width: 28px; height: 28px; border-radius: 6px;
      background: var(--accent-light); border: 1px solid var(--accent);
      color: var(--accent); font-size: 11px; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
    }

    /* ── PLACEHOLDER ── */
    .placeholder-body {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      color: var(--text-meta); gap: 8px; text-align: center; padding: 48px 32px;
    }
    .placeholder-icon { font-size: 28px; opacity: .3; margin-bottom: 4px; }
    .placeholder-title { font-size: 15px; font-weight: 600; color: var(--text-secondary); }
    .placeholder-sub { font-size: 13px; max-width: 320px; line-height: 1.6; }
    .placeholder-badge {
      font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
      padding: 4px 10px; border-radius: 4px;
      background: var(--card-bg); border: 1px solid var(--card-border);
      color: var(--text-meta); margin-top: 6px;
    }

    /* ── LOGIN ── */
    .login-overlay {
      position: fixed; inset: 0; background: var(--bg);
      display: flex; align-items: center; justify-content: center; z-index: 200;
    }
    .login-box {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 14px; padding: 36px 32px; width: 360px; max-width: 92vw;
    }
    .login-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
    .login-logo-badge {
      width: 32px; height: 32px; background: #111; border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
    }
    .login-logo-badge span { font-size: 11px; font-weight: 700; color: #fff; }
    .login-logo-name { font-size: 17px; font-weight: 600; color: var(--text-primary); }
    .login-sub { font-size: 13px; color: var(--text-meta); margin-bottom: 22px; line-height: 1.5; }
    .login-input {
      width: 100%; background: var(--bg);
      border: 1px solid var(--card-border); border-radius: 8px;
      padding: 10px 13px; color: var(--text-primary);
      font-size: 13px; font-family: monospace;
      margin-bottom: 10px; outline: none; transition: border-color .12s;
    }
    .login-input:focus { border-color: var(--accent); }
    .login-btn {
      width: 100%; background: var(--accent); color: #fff; border: none;
      border-radius: 8px; padding: 11px;
      font-size: 14px; font-weight: 600; font-family: inherit;
      cursor: pointer; transition: opacity .12s;
    }
    .login-btn:hover { opacity: .88; }
    .login-btn:disabled { opacity: .5; cursor: not-allowed; }
    .login-error { font-size: 12.5px; color: var(--error); margin-top: 10px; min-height: 18px; }

    /* ── SCROLLBAR ── */
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--card-border); border-radius: 2px; }
  </style>
</head>
<body>

<!-- Login -->
<div class="login-overlay" id="loginOverlay">
  <div class="login-box">
    <div class="login-logo">
      <div class="login-logo-badge"><span>HS</span></div>
      <div class="login-logo-name">Han Solo</div>
    </div>
    <div class="login-sub">Enter your access token to continue.</div>
    <input type="password" class="login-input" id="tokenInput" placeholder="Bearer token" autocomplete="off">
    <button class="login-btn" id="loginBtn">Connect</button>
    <div class="login-error" id="loginError"></div>
  </div>
</div>

<!-- App shell -->
<div class="app" id="appShell" style="display:none">

  <div class="sidebar">
    <div class="sidebar-logo">
      <div class="logo-badge"><span>HS</span></div>
      <div class="logo-name">Han Solo</div>
    </div>

    <nav class="sidebar-nav">
      <div class="nav-section">
        <div class="nav-section-label">Ren</div>
        <div class="nav-item active" onclick="showScreen('chat',this)">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2h10a1 1 0 011 1v6a1 1 0 01-1 1H5l-3 2V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg></div>
          <span class="nav-label">Chat</span>
        </div>
        <div class="nav-item" onclick="showScreen('memory',this)">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.4"/><path d="M7 4.5v2.75l2 1.1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></div>
          <span class="nav-label">Memory</span>
        </div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1v2M7 11v2M1 7h2M11 7h2M2.9 2.9l1.4 1.4M9.7 9.7l1.4 1.4M2.9 11.1l1.4-1.4M9.7 4.3l1.4-1.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></div>
          <span class="nav-label">Signals</span>
          <span class="nav-soon">SOON</span>
        </div>
      </div>

      <div class="nav-section" style="margin-top:8px">
        <div class="nav-section-label">Session</div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 3h10M2 6.5h6.5M2 10h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></div>
          <span class="nav-label">Threads</span>
          <span class="nav-soon">SOON</span>
        </div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M11 2L5 8M11 2H8M11 2V5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 2H3a1 1 0 00-1 1v7a1 1 0 001 1h7a1 1 0 001-1V8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg></div>
          <span class="nav-label">Decisions</span>
          <span class="nav-soon">SOON</span>
        </div>
        <div class="nav-item" onclick="showScreen('notecards',this)">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="2" y="2" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M4.5 5h5M4.5 7.5h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></div>
          <span class="nav-label">Notecards</span>
        </div>
      </div>

      <div class="nav-section" style="margin-top:8px">
        <div class="nav-section-label">Workspace</div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1.5" y="1.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="8.5" y="1.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="1.5" y="8.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="8.5" y="8.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/></svg></div>
          <span class="nav-label">Dashboard</span>
          <span class="nav-soon">SOON</span>
        </div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7a5 5 0 0110 0" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M2 11a9 9 0 0110 0" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="7" cy="3.5" r="1" fill="currentColor"/></svg></div>
          <span class="nav-label">Feed</span>
          <span class="nav-soon">SOON</span>
        </div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1.5" y="2" width="2.5" height="10" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="5.75" y="2" width="2.5" height="7" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="10" y="2" width="2.5" height="5" rx=".8" stroke="currentColor" stroke-width="1.3"/></svg></div>
          <span class="nav-label">Board</span>
          <span class="nav-soon">SOON</span>
        </div>
        <div class="nav-item disabled">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1.5 7.5L7 2l5.5 5.5M3 6.5V12h3V9h2v3h3V6.5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
          <span class="nav-label">Projects</span>
          <span class="nav-soon">SOON</span>
        </div>
      </div>

      <div class="nav-section" style="margin-top:8px">
        <div class="nav-section-label">Frameworks</div>
        <div class="nav-item" onclick="showScreen('solo-framework',this)">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1.5" y="1.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="8.5" y="1.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="1.5" y="8.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/><rect x="8.5" y="8.5" width="4" height="4" rx=".8" stroke="currentColor" stroke-width="1.3"/></svg></div>
          <span class="nav-label">Solo Builder</span>
        </div>
        <a class="nav-item" href="/docs/index.html" target="_blank">
          <div class="nav-icon"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.3"/><path d="M7 4v3l2 1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></div>
          <span class="nav-label">Han Solo Overview</span>
        </a>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="user-row">
        <div class="user-avatar" id="userAvatar">S</div>
        <div>
          <div class="user-name" id="userName">—</div>
          <div class="user-meta">Active session</div>
        </div>
        <button class="logout-btn" id="logoutBtn" title="Sign out">↩</button>
      </div>
    </div>
  </div>

  <div class="main">

    <!-- CHAT -->
    <div class="screen" id="screen-chat">
      <div class="screen-header">
        <div>
          <div class="screen-title">Chat</div>
          <div class="screen-sub">Session with Ren</div>
        </div>
        <div class="screen-actions">
          <button class="btn-secondary" id="voiceAutoBtn" title="Toggle auto-play voice">Voice: Off</button>
          <button class="btn-secondary" id="newSessionBtn">New session</button>
        </div>
      </div>
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
        <span id="filePreviewSize" style="color:var(--text-meta)"></span>
        <button class="file-remove" id="fileRemoveBtn">×</button>
      </div>
      <div class="input-area">
        <div class="input-wrap">
          <textarea id="msgInput" placeholder="Message Ren…" rows="1"></textarea>
        </div>
        <div class="nc-picker-wrap">
          <button class="nc-picker-btn" id="ncPickerBtn" title="Pull in a notecard" onclick="toggleNcPicker()">📌</button>
          <div class="nc-picker" id="ncPicker">
            <div class="nc-picker-header">Pull a notecard into chat</div>
            <div id="ncPickerList"></div>
          </div>
        </div>
        <button class="attach-btn" id="attachBtn" title="Attach a file">📎</button>
        <input type="file" id="fileInput" accept=".txt,.md,.py,.js,.ts,.jsx,.tsx,.json,.yaml,.yml,.html,.css,.sql,.sh,.csv,.toml,.env" style="display:none">
        <button class="mic-btn" id="micBtn" title="Speak your message">🎤</button>
        <button class="send-btn" id="sendBtn">Send</button>
      </div>
    </div>

    <!-- MEMORY -->
    <div class="screen hidden" id="screen-memory">
      <div class="screen-header">
        <div>
          <div class="screen-title">Memory</div>
          <div class="screen-sub">Ren's active context blocks</div>
        </div>
        <div class="screen-actions">
          <button class="btn-secondary" id="refreshMemoryBtn">↻ Refresh</button>
        </div>
      </div>
      <div class="memory-body" id="memoryBody">
        <div class="mem-state">Loading memory…</div>
      </div>
    </div>

    <!-- SIGNALS placeholder -->
    <div class="screen hidden" id="screen-signals">
      <div class="screen-header"><div><div class="screen-title">Signals</div><div class="screen-sub">Pattern observations across sessions</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">◎</div>
        <div class="placeholder-title">Signals coming soon</div>
        <div class="placeholder-sub">Texture, directional, and relational signals from ren-local will surface here.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- THREADS placeholder -->
    <div class="screen hidden" id="screen-threads">
      <div class="screen-header"><div><div class="screen-title">Threads</div><div class="screen-sub">Open action items and follow-ups</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">≡</div>
        <div class="placeholder-title">Threads coming soon</div>
        <div class="placeholder-sub">Open threads from ren-local will surface here, prioritized by urgency.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- DECISIONS placeholder -->
    <div class="screen hidden" id="screen-decisions">
      <div class="screen-header"><div><div class="screen-title">Decisions</div><div class="screen-sub">Framework and product decisions logged</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">↗</div>
        <div class="placeholder-title">Decisions coming soon</div>
        <div class="placeholder-sub">Logged decisions from ren-local will be browsable and searchable here.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- NOTECARDS -->
    <div class="screen hidden" id="screen-notecards">
      <div class="screen-header">
        <div>
          <div class="screen-title">Notecards</div>
          <div class="screen-sub" id="nc-screen-sub">Low-ceremony captures</div>
        </div>
        <div class="screen-actions">
          <button class="btn-secondary" onclick="openNewNotecard()">+ New</button>
        </div>
      </div>
      <div class="nc-filter-bar">
        <button class="nc-filter-btn active" onclick="ncSetFilter(this,'')">Active + Done</button>
        <button class="nc-filter-btn" onclick="ncSetFilter(this,'active')">Active</button>
        <button class="nc-filter-btn" onclick="ncSetFilter(this,'completed')">Completed</button>
        <button class="nc-filter-btn archived" onclick="ncSetFilter(this,'archived')">Archived</button>
      </div>
      <div class="nc-list" id="nc-list">
        <div class="nc-empty">Loading notecards…</div>
      </div>
    </div>

    <!-- DASHBOARD placeholder -->
    <div class="screen hidden" id="screen-dashboard">
      <div class="screen-header"><div><div class="screen-title">Dashboard</div><div class="screen-sub">Cross-project build health</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">⊞</div>
        <div class="placeholder-title">Dashboard coming soon</div>
        <div class="placeholder-sub">Real-time slice status, blocked items, and build health across all active projects.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- FEED placeholder -->
    <div class="screen hidden" id="screen-feed">
      <div class="screen-header"><div><div class="screen-title">Activity Feed</div><div class="screen-sub">Chronological events across all projects</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">◈</div>
        <div class="placeholder-title">Feed coming soon</div>
        <div class="placeholder-sub">A unified activity stream across projects, sessions, and decisions.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- BOARD placeholder -->
    <div class="screen hidden" id="screen-board">
      <div class="screen-header"><div><div class="screen-title">Board</div><div class="screen-sub">Kanban view of active slices</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">▦</div>
        <div class="placeholder-title">Board coming soon</div>
        <div class="placeholder-sub">Slice-level kanban across Ready → Build → Review → Done.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- PROJECTS placeholder -->
    <div class="screen hidden" id="screen-projects">
      <div class="screen-header"><div><div class="screen-title">Projects</div><div class="screen-sub">Active framework projects</div></div></div>
      <div class="placeholder-body">
        <div class="placeholder-icon">⌂</div>
        <div class="placeholder-title">Projects coming soon</div>
        <div class="placeholder-sub">All active Solo Builder projects with phase, health, and recent activity.</div>
        <div class="placeholder-badge">In design</div>
      </div>
    </div>

    <!-- SOLO BUILDER -->
    <div class="screen hidden" id="screen-solo-framework">
      <div class="screen-header">
        <div><div class="screen-title">Solo Builder</div><div class="screen-sub">The Framework · Documentation Library</div></div>
      </div>
      <div class="screen-body" style="overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:28px;">

        <!-- Overview -->
        <div class="sbf-section">
          <div class="sbf-section-label">Overview</div>
          <div class="sbf-grid">
            <a class="sbf-card" href="/docs/framework/process-map.html" target="_blank">
              <div class="sbf-card-icon">🗺️</div>
              <div class="sbf-card-title">Process Map</div>
              <div class="sbf-card-sub">Full swimlane — phases, gates, flows</div>
            </a>
            <a class="sbf-card" href="/docs/framework/framework-architecture.html" target="_blank">
              <div class="sbf-card-icon">⚡</div>
              <div class="sbf-card-title">Architecture</div>
              <div class="sbf-card-sub">Interactive flowchart of the full system</div>
            </a>
            <a class="sbf-card" href="/docs/framework/skills-reference.html" target="_blank">
              <div class="sbf-card-icon">📖</div>
              <div class="sbf-card-title">Skills Reference</div>
              <div class="sbf-card-sub">35 skills, modes, and supporting tools</div>
            </a>
            <a class="sbf-card" href="/docs/framework/backlog-status-reference.html" target="_blank">
              <div class="sbf-card-icon">📊</div>
              <div class="sbf-card-title">Backlog Status</div>
              <div class="sbf-card-sub">Slice, deliverable, and phase statuses</div>
            </a>
            <a class="sbf-card" href="/docs/framework/blog.html" target="_blank">
              <div class="sbf-card-icon">📝</div>
              <div class="sbf-card-title">Release Notes</div>
              <div class="sbf-card-sub">What changed and when</div>
            </a>
          </div>
        </div>

        <!-- Start Here -->
        <div class="sbf-section">
          <div class="sbf-section-label">Start Here</div>
          <div class="sbf-grid">
            <a class="sbf-card" href="/docs/framework/getting-started.html" target="_blank">
              <div class="sbf-card-icon">🚀</div>
              <div class="sbf-card-title">Getting Started</div>
              <div class="sbf-card-sub">First session walkthrough, entry points</div>
            </a>
            <a class="sbf-card" href="/docs/framework/faq.html" target="_blank">
              <div class="sbf-card-icon">❓</div>
              <div class="sbf-card-title">FAQ</div>
              <div class="sbf-card-sub">Troubleshooting by project stage</div>
            </a>
          </div>
        </div>

        <!-- Phase Guides -->
        <div class="sbf-section">
          <div class="sbf-section-label">Phase Guides</div>
          <div class="sbf-grid">
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-brainstorm.html" target="_blank">
              <div class="sbf-phase-badge">0</div>
              <div>
                <div class="sbf-card-title">Brainstorm</div>
                <div class="sbf-card-sub">Idea shaping before committing</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-discover.html" target="_blank">
              <div class="sbf-phase-badge">1</div>
              <div>
                <div class="sbf-card-title">Discover + Tech Context</div>
                <div class="sbf-card-sub">User research and stack decisions</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-design-sprint.html" target="_blank">
              <div class="sbf-phase-badge">2</div>
              <div>
                <div class="sbf-card-title">Design Sprint</div>
                <div class="sbf-card-sub">UX and interaction design</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-data-review.html" target="_blank">
              <div class="sbf-phase-badge">2.5</div>
              <div>
                <div class="sbf-card-title">Data + Design Review</div>
                <div class="sbf-card-sub">Schema, data scaffold, review gate</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-plan.html" target="_blank">
              <div class="sbf-phase-badge">3</div>
              <div>
                <div class="sbf-card-title">Plan</div>
                <div class="sbf-card-sub">Backlog, slices, sequencing</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-build.html" target="_blank">
              <div class="sbf-phase-badge">4</div>
              <div>
                <div class="sbf-card-title">Build</div>
                <div class="sbf-card-sub">Slice execution, commits, handoff</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-qa.html" target="_blank">
              <div class="sbf-phase-badge">5</div>
              <div>
                <div class="sbf-card-title">QA + Acceptance</div>
                <div class="sbf-card-sub">Testing, triage, sign-off</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-phase-test.html" target="_blank">
              <div class="sbf-phase-badge">5.5</div>
              <div>
                <div class="sbf-card-title">Phase Test</div>
                <div class="sbf-card-sub">Autonomous framework simulation</div>
              </div>
            </a>
            <a class="sbf-card sbf-card-phase" href="/docs/framework/guide-deploy.html" target="_blank">
              <div class="sbf-phase-badge">6</div>
              <div>
                <div class="sbf-card-title">Deploy</div>
                <div class="sbf-card-sub">Ship checklist and post-deploy</div>
              </div>
            </a>
          </div>
        </div>

        <!-- Decks -->
        <div class="sbf-section">
          <div class="sbf-section-label">Decks</div>
          <div class="sbf-grid">
            <a class="sbf-card" href="/docs/framework/deck-solo.html" target="_blank">
              <div class="sbf-card-icon">🎞️</div>
              <div class="sbf-card-title">Framework Mechanics</div>
              <div class="sbf-card-sub">Session modes, anchors, QA chain · 12 slides</div>
            </a>
            <a class="sbf-card" href="/docs/framework/deck-business.html" target="_blank">
              <div class="sbf-card-icon">💼</div>
              <div class="sbf-card-title">Business Overview</div>
              <div class="sbf-card-sub">How we work today → how we build tomorrow · 11 slides</div>
            </a>
          </div>
        </div>

      </div>
    </div>

  </div>
</div>

<script>
'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let token      = null;
let userName   = null;
let sending    = false;
let pollTimer  = null;
let _msgs      = [];
let attachment = null;
let _memLoaded = false;

// ── DOM ────────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Screen navigation ──────────────────────────────────────────────────────
function showScreen(id, navEl) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  const s = $('screen-' + id);
  if (s) s.classList.remove('hidden');
  document.querySelectorAll('.nav-item:not(.disabled)').forEach(n => n.classList.remove('active'));
  if (navEl) navEl.classList.add('active');
  if (id === 'memory') loadMemory();
}

// ── Fetch ──────────────────────────────────────────────────────────────────
function apiFetch(path, opts = {}, tok = token) {
  return fetch(path, {
    ...opts,
    headers: {
      'Authorization': 'Bearer ' + tok,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
}

// ── Auth ───────────────────────────────────────────────────────────────────
async function tryConnect(t) {
  try {
    const resp = await apiFetch('/api/me', { method: 'GET' }, t);
    if (!resp.ok) return false;
    const data = await resp.json();
    token    = t;
    userName = data.name;
    localStorage.setItem('hs_token', t);
    $('loginOverlay').style.display = 'none';
    $('appShell').style.display     = 'flex';
    $('userName').textContent       = userName;
    $('userAvatar').textContent     = userName.charAt(0).toUpperCase();
    await loadHistory();
    startPolling();
    $('msgInput').focus();
    return true;
  } catch { return false; }
}

async function doLogin() {
  const t = $('tokenInput').value.trim();
  $('loginError').textContent = '';
  if (!t) return;
  $('loginBtn').disabled = true;
  $('loginBtn').textContent = 'Connecting…';
  const ok = await tryConnect(t);
  if (!ok) {
    $('loginError').textContent = 'Invalid token. Check and try again.';
    $('loginBtn').disabled = false;
    $('loginBtn').textContent = 'Connect';
  }
}

function doLogout() {
  localStorage.removeItem('hs_token');
  stopPolling();
  location.reload();
}

$('loginBtn').addEventListener('click', doLogin);
$('tokenInput').addEventListener('keydown', e => { if (e.key === 'Enter') doLogin(); });
$('logoutBtn').addEventListener('click', doLogout);

// ── Message rendering ──────────────────────────────────────────────────────
function whoClass(name) {
  const n = (name || '').toLowerCase();
  if (n === 'ren')   return 'ren';
  if (n === 'ted')   return 'ted';
  return 'scott';
}

function renderMessages() {
  const container = $('messages');
  const empty     = $('emptyState');
  while (container.lastChild && container.lastChild !== empty) {
    container.removeChild(container.lastChild);
  }
  if (_msgs.length === 0) { empty.style.display = 'flex'; return; }
  empty.style.display = 'none';

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
    const hdr = document.createElement('div');
    hdr.className = 'msg-header ' + g.cls;
    hdr.textContent = g.name;
    group.appendChild(hdr);
    const wrap = document.createElement('div');
    wrap.className = 'msg-bubbles';
    for (const text of g.texts) {
      const b = document.createElement('div');
      b.className = 'msg-bubble ' + g.cls;
      b.textContent = text;
      if (g.cls === 'ren' && text) {
        const sp = document.createElement('button');
        sp.className = 'speak-btn'; sp.title = 'Play voice'; sp.textContent = '🔊';
        sp.addEventListener('click', () => playTTS(text, sp));
        b.appendChild(sp);
      }
      wrap.appendChild(b);
    }
    group.appendChild(wrap);
    container.appendChild(group);
  }
  container.scrollTop = container.scrollHeight;
}

function addSessionDivider(label) {
  const div = document.createElement('div');
  div.className = 'session-divider';
  div.textContent = label || 'New session — memory intact';
  $('messages').appendChild(div);
  $('messages').scrollTop = $('messages').scrollHeight;
}

function addLoading(id) {
  const group = document.createElement('div');
  group.className = 'msg-group'; group.id = id;
  const hdr = document.createElement('div');
  hdr.className = 'msg-header ren'; hdr.textContent = 'Ren';
  group.appendChild(hdr);
  const wrap = document.createElement('div'); wrap.className = 'msg-bubbles';
  const b = document.createElement('div');
  b.className = 'msg-bubble ren loading'; b.textContent = 'thinking…';
  wrap.appendChild(b); group.appendChild(wrap);
  $('messages').appendChild(group);
  $('messages').scrollTop = $('messages').scrollHeight;
}

function removeLoading(id) { const el = $(id); if (el) el.remove(); }

// ── History & polling ──────────────────────────────────────────────────────
async function loadHistory() {
  try {
    const resp = await apiFetch('/api/history');
    if (!resp.ok) return;
    _msgs = await resp.json();
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
      if (data.length !== _msgs.length) { _msgs = data; renderMessages(); }
    } catch {}
  }, 5000);
}

function stopPolling() { if (pollTimer) clearInterval(pollTimer); }

// ── New session ────────────────────────────────────────────────────────────
async function newSession() {
  const btn = $('newSessionBtn');
  if (btn.disabled) return;
  btn.disabled = true; btn.textContent = 'Resetting…';
  try {
    const resp = await apiFetch('/api/reset-session', { method: 'POST' });
    if (resp.ok) { _msgs = []; renderMessages(); addSessionDivider(); }
  } catch {}
  btn.disabled = false; btn.textContent = 'New session';
  $('msgInput').focus();
}
$('newSessionBtn').addEventListener('click', newSession);

// ── File attachment ────────────────────────────────────────────────────────
const MAX_FILE_BYTES = 100 * 1024;
function formatBytes(n) { return n < 1024 ? n + ' B' : (n / 1024).toFixed(1) + ' KB'; }

function clearAttachment() {
  attachment = null;
  $('fileInput').value = '';
  $('filePreview').classList.remove('visible');
}

$('attachBtn').addEventListener('click', () => $('fileInput').click());
$('fileRemoveBtn').addEventListener('click', clearAttachment);

$('fileInput').addEventListener('change', () => {
  const file = $('fileInput').files[0];
  if (!file) return;
  if (file.size > MAX_FILE_BYTES) {
    alert('File too large (max 100 KB).');
    $('fileInput').value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = e => {
    attachment = { name: file.name, content: e.target.result };
    $('filePreviewName').textContent = file.name;
    $('filePreviewSize').textContent = formatBytes(file.size);
    $('filePreview').classList.add('visible');
  };
  reader.readAsText(file);
});

// ── Send ───────────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = $('msgInput').value.trim();
  if ((!text && !attachment) || sending) return;
  sending = true;
  $('sendBtn').disabled = true;
  $('msgInput').value = '';
  $('msgInput').style.height = 'auto';

  const cur = attachment;
  clearAttachment();

  const displayText = cur
    ? (text ? text + '\\n\\n📄 ' + cur.name : '📄 ' + cur.name)
    : text;
  _msgs.push({ role: 'user', name: userName, text: displayText });
  renderMessages();

  const loadId = 'loading-' + Date.now();
  addLoading(loadId);

  try {
    const body = { message: text };
    if (cur) body.attachment = cur;
    const resp = await apiFetch('/api/send', { method: 'POST', body: JSON.stringify(body) });
    removeLoading(loadId);
    if (resp.ok) {
      const data = await resp.json();
      if (data.session_reset) { _msgs = []; renderMessages(); addSessionDivider('Session refreshed — memory intact'); }
      if (data.session_warning) addSessionDivider(data.session_warning);
      const msgs = data.messages && data.messages.length ? data.messages
                 : data.response ? [data.response] : [];
      await renderRenMessages(msgs);
      if (data.wants_to_continue) await triggerContinuation();
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
    $('sendBtn').disabled = false;
    $('msgInput').focus();
  }
}

async function renderRenMessages(msgs) {
  for (let i = 0; i < msgs.length; i++) {
    _msgs.push({ role: 'assistant', name: 'Ren', text: msgs[i] });
    renderMessages();
    if (_voiceAuto && msgs[i]) await playTTS(msgs[i], null);
    if (i < msgs.length - 1) await new Promise(r => setTimeout(r, 1000));
  }
}

async function triggerContinuation(depth = 0) {
  if (depth >= 5) return;
  await new Promise(r => setTimeout(r, 2500));
  const cid = 'continue-' + Date.now();
  addLoading(cid);
  try {
    const resp = await apiFetch('/api/send', { method: 'POST', body: JSON.stringify({ message: '__continue__' }) });
    removeLoading(cid);
    if (resp.ok) {
      const data = await resp.json();
      const msgs = data.messages && data.messages.length ? data.messages
                 : data.response ? [data.response] : [];
      await renderRenMessages(msgs);
      if (data.wants_to_continue) await triggerContinuation(depth + 1);
    }
  } catch { removeLoading(cid); }
}

// ── Voice output ───────────────────────────────────────────────────────────
let _voiceAuto = localStorage.getItem('hs_voice_auto') === 'true';
let _currentAudio = null;

(function() {
  const btn = $('voiceAutoBtn');
  btn.textContent = _voiceAuto ? 'Voice: On' : 'Voice: Off';
  btn.classList.toggle('voice-on', _voiceAuto);
  btn.addEventListener('click', () => {
    _voiceAuto = !_voiceAuto;
    localStorage.setItem('hs_voice_auto', _voiceAuto);
    btn.textContent = _voiceAuto ? 'Voice: On' : 'Voice: Off';
    btn.classList.toggle('voice-on', _voiceAuto);
  });
})();

async function playTTS(text, btn) {
  if (_currentAudio) {
    _currentAudio.pause(); _currentAudio = null;
    document.querySelectorAll('.speak-btn.playing').forEach(b => b.classList.remove('playing'));
    if (btn && btn.classList.contains('playing')) return;
  }
  if (btn) btn.classList.add('playing');
  try {
    const resp = await apiFetch('/api/tts', { method: 'POST', body: JSON.stringify({ text }) });
    if (!resp.ok) { if (btn) btn.classList.remove('playing'); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    _currentAudio = new Audio(url);
    _currentAudio.onended = () => { if (btn) btn.classList.remove('playing'); URL.revokeObjectURL(url); _currentAudio = null; };
    _currentAudio.onerror = () => { if (btn) btn.classList.remove('playing'); _currentAudio = null; };
    await _currentAudio.play();
  } catch { if (btn) btn.classList.remove('playing'); }
}

// ── Voice input (mic) ─────────────────────────────────────────────────────
let _recognition = null;
$('micBtn').addEventListener('click', () => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { alert('Voice input not supported in this browser. Try Chrome.'); return; }
  if (_recognition) { _recognition.stop(); return; }
  _recognition = new SR();
  _recognition.lang = 'en-US'; _recognition.interimResults = false; _recognition.maxAlternatives = 1;
  $('micBtn').classList.add('listening');
  _recognition.onresult = e => {
    const t = e.results[0][0].transcript;
    const inp = $('msgInput');
    inp.value = (inp.value ? inp.value + ' ' : '') + t;
    inp.dispatchEvent(new Event('input')); inp.focus();
  };
  _recognition.onend = () => { $('micBtn').classList.remove('listening'); _recognition = null; };
  _recognition.onerror = () => { $('micBtn').classList.remove('listening'); _recognition = null; };
  _recognition.start();
});

$('sendBtn').addEventListener('click', sendMessage);
$('msgInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
$('msgInput').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 140) + 'px';
});

// ── Memory screen ──────────────────────────────────────────────────────────
async function loadMemory() {
  if (_memLoaded) return;
  $('memoryBody').innerHTML = '<div class="mem-state">Loading memory…</div>';
  try {
    const [memResp, jobsResp] = await Promise.all([
      apiFetch('/api/memory-panel'),
      fetch('/api/jobs-status'),
    ]);
    let jobsPaused = false;
    if (jobsResp.ok) { jobsPaused = (await jobsResp.json()).paused; }
    if (!memResp.ok) { $('memoryBody').innerHTML = '<div class="mem-state">Error loading memory.</div>'; return; }
    const data   = await memResp.json();
    const blocks = data.blocks || data;
    const find   = lbl => { const b = blocks.find(b => b.label === lbl); return b ? (b.value || '—') : '—'; };
    renderMemoryBlocks(jobsPaused, find('project_state'), find('always_loaded_core'), find('pending_thoughts'));
    _memLoaded = true;
  } catch {
    $('memoryBody').innerHTML = '<div class="mem-state">Error loading memory.</div>';
  }
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`/g, '&#96;');
}

function renderMemoryBlocks(paused, project, core, pending) {
  const body = $('memoryBody');
  body.innerHTML = '';

  // Jobs card
  const jobsCard = document.createElement('div');
  jobsCard.className = 'mem-block';
  jobsCard.innerHTML =
    '<div class="mem-block-label">Automated Jobs</div>' +
    '<div class="jobs-row">' +
      '<span class="jobs-status ' + (paused ? 'paused' : 'running') + '" id="jobsStatus">' + (paused ? 'Paused' : 'Running') + '</span>' +
      '<button class="jobs-toggle" id="jobsToggleBtn" onclick="toggleJobs()">' + (paused ? 'Resume' : 'Pause') + '</button>' +
    '</div>';
  body.appendChild(jobsCard);

  // Memory blocks
  [
    { label: 'project_state',     value: project },
    { label: 'always_loaded_core', value: core    },
    { label: 'pending_thoughts',  value: pending  },
  ].forEach(({ label, value }) => {
    const card = document.createElement('div');
    card.className = 'mem-block';
    const lbl = document.createElement('div');
    lbl.className = 'mem-block-label';
    lbl.textContent = label;
    const content = document.createElement('div');
    content.className = 'mem-block-content';
    content.textContent = value;
    card.appendChild(lbl);
    card.appendChild(content);
    body.appendChild(card);
  });
}

async function toggleJobs() {
  const btn      = $('jobsToggleBtn');
  const statusEl = $('jobsStatus');
  const nowPaused = statusEl.textContent === 'Running';
  btn.textContent = '…'; btn.disabled = true;
  try {
    const resp = await apiFetch('/api/jobs-paused', {
      method: 'POST', body: JSON.stringify({ paused: nowPaused }),
    });
    if (resp.ok) {
      const data = await resp.json();
      statusEl.textContent = data.paused ? 'Paused' : 'Running';
      statusEl.className   = 'jobs-status ' + (data.paused ? 'paused' : 'running');
      btn.textContent      = data.paused ? 'Resume' : 'Pause';
    }
  } catch { btn.textContent = 'Error'; }
  btn.disabled = false;
}

$('refreshMemoryBtn').addEventListener('click', () => { _memLoaded = false; loadMemory(); });

// ── Notecards screen ───────────────────────────────────────────────────────
let _ncFilter = '';
let _ncLoaded = false;

function ncSetFilter(btn, filter) {
  document.querySelectorAll('.nc-filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  _ncFilter = filter;
  _ncLoaded = false;
  loadNotecards();
}

async function loadNotecards() {
  if (_ncLoaded) return;
  $('nc-list').innerHTML = '<div class="nc-empty">Loading…</div>';
  try {
    const qs = _ncFilter ? '?status=' + _ncFilter : '';
    const resp = await apiFetch('/api/notecards' + qs);
    if (!resp.ok) { $('nc-list').innerHTML = '<div class="nc-empty">Error loading notecards.</div>'; return; }
    const cards = await resp.json();
    renderNotecards(cards);
    const sub = cards.length + ' notecard' + (cards.length !== 1 ? 's' : '');
    $('nc-screen-sub').textContent = sub;
    _ncLoaded = true;
  } catch { $('nc-list').innerHTML = '<div class="nc-empty">Error loading notecards.</div>'; }
}

function renderNotecards(cards) {
  const list = $('nc-list');
  if (!cards.length) { list.innerHTML = '<div class="nc-empty">No notecards here.</div>'; return; }
  list.innerHTML = '';
  cards.forEach(c => {
    const card = document.createElement('div');
    card.className = 'nc-card';
    const creatorInitial = c.creator.charAt(0).toUpperCase();
    const dateStr = c.created_at ? new Date(c.created_at).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) : '—';
    const actions = ncActions(c);
    card.innerHTML =
      '<div class="nc-card-top">' +
        '<div class="nc-creator ' + c.creator + '">' + creatorInitial + '</div>' +
        '<div class="nc-text">' + escNc(c.text) + '</div>' +
        '<div class="nc-meta"><span class="nc-status ' + c.status + '">' + c.status + '</span></div>' +
      '</div>' +
      '<div class="nc-card-footer">' +
        '<span class="nc-date">' + c.creator.charAt(0).toUpperCase() + c.creator.slice(1) + ' · ' + dateStr + ' · ' + c.source + '</span>' +
        '<div class="nc-actions">' + actions + '</div>' +
      '</div>';
    list.appendChild(card);
    card.querySelectorAll('.nc-action-btn').forEach(btn => {
      btn.addEventListener('click', () => updateNcStatus(c.id, btn.dataset.status, card));
    });
  });
}

function ncActions(c) {
  if (c.status === 'active')    return '<button class="nc-action-btn" data-status="completed">Complete</button><button class="nc-action-btn" data-status="archived">Archive</button>';
  if (c.status === 'completed') return '<button class="nc-action-btn" data-status="active">Reopen</button><button class="nc-action-btn" data-status="archived">Archive</button>';
  if (c.status === 'archived')  return '<button class="nc-action-btn" data-status="active">Restore</button>';
  return '';
}

function escNc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function updateNcStatus(id, status, cardEl) {
  try {
    const resp = await apiFetch('/api/notecards/' + id, { method: 'PATCH', body: JSON.stringify({ status }) });
    if (resp.ok) { _ncLoaded = false; loadNotecards(); }
  } catch {}
}

async function openNewNotecard() {
  const text = prompt('Notecard text:');
  if (!text || !text.trim()) return;
  try {
    const resp = await apiFetch('/api/notecards', { method: 'POST', body: JSON.stringify({ text: text.trim(), source: 'manual' }) });
    if (resp.ok) { _ncLoaded = false; loadNotecards(); }
  } catch {}
}

// ── Notecard picker (mid-chat) ─────────────────────────────────────────────
let _pickerOpen = false;

async function toggleNcPicker() {
  _pickerOpen = !_pickerOpen;
  $('ncPicker').classList.toggle('open', _pickerOpen);
  if (_pickerOpen) await loadNcPicker();
}

async function loadNcPicker() {
  const list = $('ncPickerList');
  list.innerHTML = '<div class="nc-picker-empty">Loading…</div>';
  try {
    const resp = await apiFetch('/api/notecards?status=active');
    if (!resp.ok) { list.innerHTML = '<div class="nc-picker-empty">Error loading.</div>'; return; }
    const cards = await resp.json();
    if (!cards.length) { list.innerHTML = '<div class="nc-picker-empty">No active notecards.</div>'; return; }
    list.innerHTML = '';
    cards.forEach(c => {
      const item = document.createElement('div');
      item.className = 'nc-picker-item';
      const dateStr = c.created_at ? new Date(c.created_at).toLocaleDateString('en-US', { month:'short', day:'numeric' }) : '';
      item.innerHTML =
        '<div class="nc-picker-item-text">' + escNc(c.text) + '</div>' +
        '<div class="nc-picker-item-meta">' + c.creator + ' · ' + dateStr + '</div>';
      item.addEventListener('click', () => injectNotecard(c.text));
      list.appendChild(item);
    });
  } catch { list.innerHTML = '<div class="nc-picker-empty">Error loading.</div>'; }
}

function injectNotecard(text) {
  const input = $('msgInput');
  const prefix = '📌 ' + text;
  input.value = input.value ? input.value + '\\n\\n' + prefix : prefix;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  _pickerOpen = false;
  $('ncPicker').classList.remove('open');
  input.focus();
}

// Close picker when clicking outside
document.addEventListener('click', e => {
  if (_pickerOpen && !e.target.closest('.nc-picker-wrap')) {
    _pickerOpen = false;
    $('ncPicker').classList.remove('open');
  }
});

// ── Boot ───────────────────────────────────────────────────────────────────
(async function init() {
  const saved = localStorage.getItem('hs_token');
  if (saved) {
    const ok = await tryConnect(saved);
    if (ok) return;
    localStorage.removeItem('hs_token');
  }
  $('loginOverlay').style.display = 'flex';
})();
</script>
</body>
</html>"""
