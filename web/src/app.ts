import { AudioQueue, MicCapture } from './audio';
import type { BadgeState, ChatMessage, ConnectionState, LatencyTimings, TurnState, WsJsonFrame } from './types';
import {
  appendMessage,
  clearError,
  renderApp,
  showError,
  showToast,
  updateConnectionState,
  updateTimings,
  updateTurnState,
} from './ui';
import { VoiceSocket } from './ws';

const HEARTBEAT_INTERVAL_MS = 15_000;
const HEARTBEAT_TIMEOUT_MS = 10_000;

export class App {
  private mic = new MicCapture();
  private audioQueue = new AudioQueue();
  private ws: VoiceSocket;

  private connState: ConnectionState = 'disconnected';
  private badgeState: BadgeState = 'offline';
  private turnState: TurnState = 'idle';
  private timings: LatencyTimings = {};
  private isRecording = false;
  private suppressAssistantAudio = false;
  private conversationId = '';
  private messages: ChatMessage[] = [];

  /** True only after session_started is received; reset on disconnect/error. */
  private sessionReady = false;

  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatPongTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatSeq = 0;
  private lifecycleRecoveryTimer: ReturnType<typeof setTimeout> | null = null;

  /** Tracks an in-flight manual check ping; null when no manual check is pending. */
  private manualCheckPingId: string | null = null;
  private manualCheckTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(root: HTMLElement) {
    renderApp(root);

    this.ws = new VoiceSocket({
      onOpen: () => this.handleWsOpen(),
      onClose: () => this.handleWsClose(),
      onJson: (frame) => this.handleWsJson(frame),
      onBinary: (data) => this.handleWsBinary(data),
      onError: (msg) => showError(msg),
    });

    const pttBtn = document.getElementById('btn-ptt')!;
    pttBtn.addEventListener('pointerdown', () => this.startRecording());
    pttBtn.addEventListener('pointerup', () => this.stopRecording());
    pttBtn.addEventListener('pointercancel', () => this.stopRecording());
    pttBtn.addEventListener('pointerleave', () => {
      if (this.isRecording) this.stopRecording();
    });

    const cancelBtn = document.getElementById('btn-cancel');
    cancelBtn?.addEventListener('click', () => this.sendCancelTurn());

    const checkBtn = document.getElementById('btn-check-conn');
    checkBtn?.addEventListener('click', () => this.checkConnection());

    // Stale-connection recovery on browser lifecycle events
    document.addEventListener('visibilitychange', () => this.handleVisibilityChange());
    window.addEventListener('pageshow', () => this.handlePageShow());
  }

  async start(): Promise<void> {
    try {
      await this.mic.init();
    } catch (err) {
      showError(
        'Microphone access denied. ' +
        'Use localhost or HTTPS to enable mic capture.'
      );
      return;
    }
    this.setConnState('connecting');
    this.setBadgeState('checking');
    this.ws.connect();
  }

  private setConnState(state: ConnectionState): void {
    this.connState = state;
    // Badge is driven by setBadgeState() — not updated here.
    const btn = document.getElementById('btn-ptt') as HTMLButtonElement;
    if (btn) {
      // PTT is enabled only when connected AND sessionReady AND turnState=idle
      btn.disabled = !(state === 'connected' && this.sessionReady && this.turnState === 'idle');
    }
  }

  private setBadgeState(state: BadgeState): void {
    this.badgeState = state;
    updateConnectionState(state);
  }

  private setTurnState(state: TurnState): void {
    this.turnState = state;
    updateTurnState(state);
    // Re-evaluate PTT disabled state whenever turn state changes
    const btn = document.getElementById('btn-ptt') as HTMLButtonElement;
    if (btn) {
      btn.disabled = !(
        this.connState === 'connected'
        && this.sessionReady
        && (state === 'idle' || state === 'listening' || state === 'recording')
      );
    }
  }

  private handleWsOpen(): void {
    // Do NOT mark as ready here — wait for session_started from server.
    // Badge stays 'checking' until session_started arrives.
    this.setConnState('connected');
    clearError();
    this.startHeartbeat();
  }

  private handleWsClose(): void {
    this.sessionReady = false;
    this.suppressAssistantAudio = false;
    this.stopHeartbeat();
    this.setConnState('disconnected');
    this.setBadgeState('offline');
    this.setTurnState('idle');
    this.audioQueue.clear();
    this.isRecording = false;
    // Reconnect after a short delay
    setTimeout(() => {
      if (this.connState === 'disconnected') {
        this.setConnState('connecting');
        this.setBadgeState('checking');
        this.ws.connect();
      }
    }, 2000);
  }

  private handleWsJson(frame: WsJsonFrame): void {
    const event = (frame as { event: string }).event;

    if (event === 'session_started') {
      this.conversationId = (frame as { conversation_id: string }).conversation_id;
      this.sessionReady = true;
      this.suppressAssistantAudio = false;
      this.setConnState('connected'); // re-evaluate PTT enabled state
      this.setBadgeState('ready');
      this.setTurnState('idle');
      clearError();
    } else if (event === 'transcript') {
      const text = (frame as { text: string }).text;
      const msg: ChatMessage = { role: 'user', text, ts: performance.now() };
      this.messages.push(msg);
      appendMessage(msg);
      this.timings.transcriptAt = performance.now();
      this.setTurnState('thinking');
      updateTimings(this.timings);
    } else if (event === 'active_state') {
      const state = (frame as { state: string }).state as TurnState;
      this.setTurnState(state);
    } else if (event === 'assistant_text') {
      const text = (frame as { text: string }).text;
      const msg: ChatMessage = { role: 'assistant', text, ts: performance.now() };
      this.messages.push(msg);
      appendMessage(msg);
    } else if (event === 'turn_started') {
      // active_state(speaking) from server drives the badge; turn_started kept for compat
    } else if (event === 'turn_completed') {
      this.timings.turnEndAt = performance.now();
      updateTimings(this.timings);
      // active_state(idle) follows turn_completed from server
    } else if (event === 'turn_end') {
      // No-op: active_state(idle) already handled state reset
    } else if (event === 'voice_turn_skipped') {
      const reason = (frame as { reason: string }).reason;
      const toastMsg = reason === 'audio_too_short'
        ? 'Audio too short — tap and hold a bit longer'
        : `Turn skipped (${reason})`;
      showToast(toastMsg);
      this.setTurnState('idle');
    } else if (event === 'pong') {
      this.handlePong((frame as { id?: string }).id);
    } else if (event === 'error') {
      const errFrame = frame as { error: { code: string; message: string } };
      showError(`[${errFrame.error.code}] ${errFrame.error.message}`);
      this.setTurnState('idle');
    }
    // Unknown events are silently ignored
  }

  private handleWsBinary(data: ArrayBuffer): void {
    if (this.suppressAssistantAudio) return;

    if (this.timings.firstAudioAt === undefined) {
      this.timings.firstAudioAt = performance.now();
      updateTimings(this.timings);
    }
    this.audioQueue.enqueue(data);
  }

  private async startRecording(): Promise<void> {
    if (!this.sessionReady) {
      showToast(
        this.connState === 'connecting' || this.connState === 'disconnected'
          ? 'Reconnecting… please wait'
          : 'Session not ready — please wait'
      );
      return;
    }
    if (this.turnState !== 'idle') {
      // Already in a turn — ignore (cancel button handles interrupts)
      return;
    }
    if (!this.ws.isOpen) {
      showToast('Connection lost — reconnecting…');
      this.triggerReconnect();
      return;
    }
    this.suppressAssistantAudio = false;
    this.isRecording = true;
    this.timings = {};
    this.audioQueue.clear();
    clearError();
    this.setTurnState('listening');

    this.mic.start();
  }

  private async stopRecording(): Promise<void> {
    if (!this.isRecording) return;
    this.isRecording = false;

    let blob: Blob;
    try {
      blob = await this.mic.stop();
    } catch {
      this.setTurnState('idle');
      return;
    }

    const format = this.mic.getAudioFormat();
    this.timings.utteranceEndAt = performance.now();

    this.ws.sendJson({ event: 'start_utterance', format, sample_rate: 48000 });

    const buf = await blob.arrayBuffer();
    this.ws.sendBinary(buf);
    this.ws.sendJson({ event: 'end_of_utterance' });
    // State stays 'listening' until server sends active_state(thinking)
  }

  private sendCancelTurn(): void {
    this.ws.sendJson({ event: 'cancel_turn' });
    this.audioQueue.clear();
    this.suppressAssistantAudio = true;
    // Optimistically reset local turn state — server will confirm with active_state=idle
    this.setTurnState('idle');
  }

  // --- Stale connection recovery ---

  private triggerReconnect(): void {
    this.sessionReady = false;
    this.suppressAssistantAudio = false;
    this.stopHeartbeat();
    this.isRecording = false;
    this.audioQueue.clear();
    this.setTurnState('idle');
    this.setConnState('connecting');
    this.setBadgeState('checking');
    this.ws.reconnect();
  }

  private handleVisibilityChange(): void {
    if (document.visibilityState === 'hidden') {
      // Stop heartbeat and discard pending pong timer while tab is hidden;
      // browser throttles timers when hidden, so a stale pong timeout would
      // fire after restore and cause a false triggerReconnect().
      this.stopHeartbeat();
    } else {
      this.scheduleLifecycleRecovery();
    }
  }

  private handlePageShow(): void {
    this.scheduleLifecycleRecovery();
  }

  // Debounce recovery so rapid visibilitychange + pageshow coalesce to one attempt.
  private scheduleLifecycleRecovery(): void {
    if (this.lifecycleRecoveryTimer !== null) {
      clearTimeout(this.lifecycleRecoveryTimer);
    }
    this.lifecycleRecoveryTimer = setTimeout(() => {
      this.lifecycleRecoveryTimer = null;
      // Discard any pong timer that may have survived a page-freeze race
      if (this.heartbeatPongTimer !== null) {
        clearTimeout(this.heartbeatPongTimer);
        this.heartbeatPongTimer = null;
      }
      this.checkAndRecoverConnection();
      // Resume heartbeat if the socket is open but heartbeat was paused on hide
      if (this.ws.isOpen && this.heartbeatTimer === null) {
        this.startHeartbeat();
      }
    }, 300);
  }

  private checkAndRecoverConnection(): void {
    if (!this.ws.isOpen && !this.ws.isConnecting) {
      this.triggerReconnect();
    } else if (this.ws.isOpen && !this.sessionReady) {
      // Socket open but no session — request a fresh session
      this.ws.sendJson({ event: 'new_session' });
    }
  }

  // --- Heartbeat ---

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => this.sendHeartbeat(), HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.heartbeatPongTimer !== null) {
      clearTimeout(this.heartbeatPongTimer);
      this.heartbeatPongTimer = null;
    }
  }

  private sendHeartbeat(): void {
    if (!this.ws.isOpen) {
      this.triggerReconnect();
      return;
    }
    const id = `hb-${++this.heartbeatSeq}`;
    this.ws.sendJson({ event: 'ping', id });
    this.heartbeatPongTimer = setTimeout(() => {
      this.heartbeatPongTimer = null;
      // If page is hidden, the timer was throttled by the browser; skip reconnect
      // to avoid a false triggerReconnect() on tab restore.
      if (document.visibilityState === 'hidden') return;
      this.triggerReconnect();
    }, HEARTBEAT_TIMEOUT_MS);
  }

  private handlePong(id?: string): void {
    if (id !== undefined && id === this.manualCheckPingId) {
      // Manual check pong — resolve the pending check
      this.manualCheckPingId = null;
      if (this.manualCheckTimer !== null) {
        clearTimeout(this.manualCheckTimer);
        this.manualCheckTimer = null;
      }
      this.setBadgeState('ready');
      showToast('Connection checked');
      return;
    }
    // Heartbeat pong
    if (this.heartbeatPongTimer !== null) {
      clearTimeout(this.heartbeatPongTimer);
      this.heartbeatPongTimer = null;
    }
  }

  /** Manual check/reconnect triggered by the ↻ button. */
  private checkConnection(): void {
    if (this.ws.isOpen) {
      const id = `check-${Date.now()}`;
      this.manualCheckPingId = id;
      this.setBadgeState('checking');
      this.ws.sendJson({ event: 'ping', id });
      this.manualCheckTimer = setTimeout(() => {
        this.manualCheckPingId = null;
        this.manualCheckTimer = null;
        this.triggerReconnect();
      }, HEARTBEAT_TIMEOUT_MS);
    } else {
      this.triggerReconnect();
    }
  }
}
