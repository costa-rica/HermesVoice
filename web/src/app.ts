import { AudioQueue, MicCapture } from './audio';
import type { ChatMessage, ConnectionState, LatencyTimings, TurnState, WsJsonFrame } from './types';
import {
  appendMessage,
  clearError,
  renderApp,
  showError,
  updateConnectionState,
  updateTimings,
  updateTurnState,
} from './ui';
import { VoiceSocket } from './ws';

export class App {
  private mic = new MicCapture();
  private audioQueue = new AudioQueue();
  private ws: VoiceSocket;

  private connState: ConnectionState = 'disconnected';
  private turnState: TurnState = 'idle';
  private timings: LatencyTimings = {};
  private isRecording = false;
  private conversationId = '';
  private messages: ChatMessage[] = [];

  constructor(root: HTMLElement) {
    renderApp(root);

    this.ws = new VoiceSocket({
      onOpen: () => this.handleWsOpen(),
      onClose: () => this.handleWsClose(),
      onJson: (frame) => this.handleWsJson(frame),
      onBinary: (data) => this.handleWsBinary(data),
      onError: (msg) => showError(msg),
    });

    const btn = document.getElementById('btn-ptt')!;
    btn.addEventListener('pointerdown', () => this.startRecording());
    btn.addEventListener('pointerup', () => this.stopRecording());
    btn.addEventListener('pointercancel', () => this.stopRecording());
    btn.addEventListener('pointerleave', () => {
      if (this.isRecording) this.stopRecording();
    });
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
    this.ws.connect();
  }

  private setConnState(state: ConnectionState): void {
    this.connState = state;
    updateConnectionState(state);
    if (state === 'connected') {
      (document.getElementById('btn-ptt') as HTMLButtonElement).disabled = false;
    } else {
      (document.getElementById('btn-ptt') as HTMLButtonElement).disabled = true;
    }
  }

  private setTurnState(state: TurnState): void {
    this.turnState = state;
    updateTurnState(state);
  }

  private handleWsOpen(): void {
    this.setConnState('connected');
    clearError();
  }

  private handleWsClose(): void {
    this.setConnState('disconnected');
    this.setTurnState('idle');
    this.audioQueue.clear();
    // Reconnect after a short delay
    setTimeout(() => {
      if (this.connState === 'disconnected') {
        this.setConnState('connecting');
        this.ws.connect();
      }
    }, 2000);
  }

  private handleWsJson(frame: WsJsonFrame): void {
    const event = (frame as { event: string }).event;

    if (event === 'session_started') {
      this.conversationId = (frame as { conversation_id: string }).conversation_id;
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
    } else if (event === 'error') {
      const errFrame = frame as { error: { code: string; message: string } };
      showError(`[${errFrame.error.code}] ${errFrame.error.message}`);
      this.setTurnState('idle');
    }
    // Unknown events are silently ignored
  }

  private handleWsBinary(data: ArrayBuffer): void {
    if (this.timings.firstAudioAt === undefined) {
      this.timings.firstAudioAt = performance.now();
      updateTimings(this.timings);
    }
    this.audioQueue.enqueue(data);
  }

  private async startRecording(): Promise<void> {
    if (this.turnState !== 'idle' || !this.ws.isOpen) return;
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
}
