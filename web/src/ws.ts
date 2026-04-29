import { WS_VOICE_URL } from './config';
import type { WsJsonFrame } from './types';

export type WsEventHandler = {
  onOpen?: () => void;
  onClose?: () => void;
  onJson?: (frame: WsJsonFrame) => void;
  onBinary?: (data: ArrayBuffer) => void;
  onError?: (msg: string) => void;
};

export class VoiceSocket {
  private ws: WebSocket | null = null;
  private handlers: WsEventHandler;

  constructor(handlers: WsEventHandler) {
    this.handlers = handlers;
  }

  connect(): void {
    if (this.ws && this.ws.readyState < WebSocket.CLOSING) return;

    this.ws = new WebSocket(WS_VOICE_URL);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => this.handlers.onOpen?.();

    this.ws.onclose = () => this.handlers.onClose?.();

    this.ws.onerror = () => this.handlers.onError?.('WebSocket error');

    this.ws.onmessage = (evt) => {
      if (evt.data instanceof ArrayBuffer) {
        this.handlers.onBinary?.(evt.data);
      } else if (typeof evt.data === 'string') {
        try {
          const frame = JSON.parse(evt.data) as WsJsonFrame;
          this.handlers.onJson?.(frame);
        } catch {
          // ignore malformed JSON
        }
      }
    };
  }

  sendJson(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  sendBinary(data: ArrayBuffer | Blob): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(data);
    }
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }

  get isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
