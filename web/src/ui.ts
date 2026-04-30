import type { BadgeState, ChatMessage, LatencyTimings, TurnState } from './types';

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
    <div class="conn-status">
      <div id="conn-state" class="badge offline">Offline</div>
      <button id="btn-check-conn" class="btn-check" title="Check connection" aria-label="Check connection">↻</button>
    </div>
    <form method="post" action="/logout" style="margin:0">
      <button type="submit" class="btn-small">Logout</button>
    </form>
  </header>

  <main>
    <section class="controls">
      <button id="btn-ptt" class="btn-ptt" disabled>
        Hold to Talk
      </button>
      <button id="btn-cancel" class="btn-cancel" style="display:none">
        Cancel
      </button>
      <div id="turn-state" class="turn-state">idle</div>
      <div id="status-toast" class="status-toast" style="display:none"></div>
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

const _BADGE_LABELS: Record<BadgeState, string> = {
  ready: 'Ready',
  checking: 'Checking…',
  offline: 'Offline',
};

export function updateConnectionState(state: BadgeState): void {
  const badge = document.getElementById('conn-state');
  if (!badge) return;
  badge.textContent = _BADGE_LABELS[state];
  badge.className = `badge ${state}`;
}

const _STATE_LABELS: Partial<Record<TurnState, string>> = {
  idle: 'Idle',
  listening: 'Listening',
  recording: 'Listening',
  transcribing: 'Transcribing',
  thinking: 'Thinking',
  thinking_progress: 'Hermes is taking longer than usual',
  speaking: 'Speaking',
  awaiting_approval: 'Awaiting Approval',
  error: 'Error',
};

const _CANCELLABLE_STATES: ReadonlySet<TurnState> = new Set([
  'thinking',
  'thinking_progress',
  'speaking',
]);

export function isBackendTurnCancellable(state: TurnState): boolean {
  return _CANCELLABLE_STATES.has(state);
}

export function updateCancelVisibility(state: TurnState, assistantPlaybackActive = false): void {
  const cancelBtn = document.getElementById('btn-cancel') as HTMLButtonElement | null;
  if (cancelBtn) {
    cancelBtn.style.display = (
      isBackendTurnCancellable(state) || assistantPlaybackActive
    ) ? '' : 'none';
  }
}

export function updateTurnState(state: TurnState): void {
  const pill = document.getElementById('turn-state');
  if (pill) {
    pill.textContent = _STATE_LABELS[state] ?? state;
    pill.className = `turn-state state-${state.replace('_', '-')}`;
  }

  const btn = document.getElementById('btn-ptt') as HTMLButtonElement | null;
  if (btn) {
    if (state === 'idle') {
      btn.textContent = 'Hold to Talk';
      btn.disabled = false;
      btn.classList.remove('recording');
    } else if (state === 'listening' || state === 'recording') {
      btn.textContent = 'Release to Send';
      btn.disabled = false;
      btn.classList.add('recording');
    } else {
      btn.textContent = (_STATE_LABELS[state] ?? state) + '…';
      btn.disabled = true;
      btn.classList.remove('recording');
    }
  }

  updateCancelVisibility(state);
}

let _toastTimer: ReturnType<typeof setTimeout> | null = null;

export function showToast(msg: string, durationMs = 3000): void {
  const toast = document.getElementById('status-toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.style.display = '';
  if (_toastTimer !== null) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.style.display = 'none';
    _toastTimer = null;
  }, durationMs);
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
