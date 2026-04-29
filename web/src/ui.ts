import type { ChatMessage, ConnectionState, LatencyTimings, TurnState } from './types';

// Minimal DOM helpers

export function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id);
  if (!e) throw new Error(`Missing element #${id}`);
  return e as T;
}

export function setText(id: string, text: string): void {
  const e = document.getElementById(id);
  if (e) e.textContent = text;
}

export function setVisible(id: string, visible: boolean): void {
  const e = document.getElementById(id);
  if (e) (e as HTMLElement).style.display = visible ? '' : 'none';
}

export function renderApp(root: HTMLElement): void {
  root.innerHTML = `
<div class="app">
  <header>
    <h1>HermesVoice</h1>
    <div id="conn-state" class="badge disconnected">Disconnected</div>
    <form method="post" action="/logout" style="margin:0">
      <button type="submit" class="btn-small">Logout</button>
    </form>
  </header>

  <main>
    <section class="controls">
      <button id="btn-ptt" class="btn-ptt" disabled>
        Hold to Talk
      </button>
      <div id="turn-state" class="turn-state">idle</div>
    </section>

    <section class="chat-section">
      <h2>Conversation</h2>
      <div id="chat-log" class="chat-log"></div>
    </section>

    <section class="timings-section">
      <h2>Latency</h2>
      <div id="timings" class="timings"></div>
    </section>

    <section id="error-section" class="error-section" style="display:none">
      <h2>Error</h2>
      <div id="error-msg" class="error-msg"></div>
    </section>
  </main>
</div>
  `.trim();
}

export function updateConnectionState(state: ConnectionState): void {
  const badge = document.getElementById('conn-state');
  if (!badge) return;
  badge.textContent = state.charAt(0).toUpperCase() + state.slice(1);
  badge.className = `badge ${state}`;
}

export function updateTurnState(state: TurnState): void {
  setText('turn-state', state);
  const btn = document.getElementById('btn-ptt') as HTMLButtonElement | null;
  if (!btn) return;
  if (state === 'idle') {
    btn.textContent = 'Hold to Talk';
    btn.disabled = false;
    btn.classList.remove('recording');
  } else if (state === 'recording') {
    btn.textContent = 'Release to Send';
    btn.disabled = false;
    btn.classList.add('recording');
  } else {
    btn.textContent = state.charAt(0).toUpperCase() + state.slice(1) + '...';
    btn.disabled = true;
    btn.classList.remove('recording');
  }
}

export function updateTranscript(text: string): void {
  setText('transcript', text || '(no transcript)');
}

export function appendMessage(msg: ChatMessage): void {
  const log = document.getElementById('chat-log');
  if (!log) return;
  const div = document.createElement('div');
  div.className = `bubble bubble-${msg.role}`;
  div.textContent = msg.text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

export function showError(msg: string): void {
  setText('error-msg', msg);
  setVisible('error-section', true);
}

export function clearError(): void {
  setVisible('error-section', false);
}

export function updateTimings(t: LatencyTimings): void {
  const el = document.getElementById('timings');
  if (!el || !t.utteranceEndAt) return;
  const lines: string[] = [];
  if (t.transcriptAt) {
    lines.push(`STT: ${(t.transcriptAt - t.utteranceEndAt).toFixed(0)} ms`);
  }
  if (t.firstAudioAt) {
    lines.push(`First audio: ${(t.firstAudioAt - t.utteranceEndAt).toFixed(0)} ms`);
  }
  if (t.turnEndAt) {
    lines.push(`Full turn: ${(t.turnEndAt - t.utteranceEndAt).toFixed(0)} ms`);
  }
  el.textContent = lines.join(' | ') || 'In progress…';
}
