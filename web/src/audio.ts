// Microphone capture using MediaRecorder API.
// Note: browser mic capture requires localhost, 127.0.0.1, or HTTPS.

export interface AudioChunk {
  data: Blob;
  format: string;
  sampleRate: number;
}

export class MicCapture {
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private _mimeType = '';

  get mimeType(): string {
    return this._mimeType;
  }

  async init(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: 48000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
      video: false,
    });
  }

  start(): void {
    if (!this.stream) throw new Error('MicCapture not initialized');
    this.chunks = [];

    // Prefer webm/opus; fall back to whatever the browser supports
    const preferred = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    this._mimeType = preferred.find(m => MediaRecorder.isTypeSupported(m)) ?? '';

    const opts = this._mimeType ? { mimeType: this._mimeType } : {};
    this.recorder = new MediaRecorder(this.stream, opts);
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start(100); // collect chunks every 100 ms
  }

  async stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      if (!this.recorder) { reject(new Error('Not recording')); return; }
      this.recorder.onstop = () => {
        const mime = this._mimeType || 'audio/webm';
        resolve(new Blob(this.chunks, { type: mime }));
      };
      this.recorder.stop();
    });
  }

  getAudioFormat(): string {
    const m = this._mimeType.toLowerCase();
    if (m.includes('ogg')) return 'ogg/opus';
    return 'webm/opus';
  }

  destroy(): void {
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null;
    this.recorder = null;
  }
}

// ---------------------------------------------------------------------------
// Audio playback queue — plays Opus blobs sequentially.
// ---------------------------------------------------------------------------

export class AudioQueue {
  private queue: Blob[] = [];
  private playing = false;
  private ctx: AudioContext | null = null;
  private activeSource: AudioBufferSourceNode | null = null;
  private playbackGeneration = 0;

  private getCtx(): AudioContext {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new AudioContext();
    }
    return this.ctx;
  }

  enqueue(data: ArrayBuffer): void {
    const blob = new Blob([data], { type: 'audio/ogg; codecs=opus' });
    this.queue.push(blob);
    if (!this.playing) this._playNext();
  }

  private async _playNext(): Promise<void> {
    const generation = this.playbackGeneration;
    const blob = this.queue.shift();
    if (!blob) {
      if (generation === this.playbackGeneration) this.playing = false;
      return;
    }
    this.playing = true;
    try {
      const ctx = this.getCtx();
      if (ctx.state === 'suspended') await ctx.resume();
      if (generation !== this.playbackGeneration) return;
      const buf = await blob.arrayBuffer();
      if (generation !== this.playbackGeneration) return;
      const decoded = await ctx.decodeAudioData(buf);
      if (generation !== this.playbackGeneration) return;
      const src = ctx.createBufferSource();
      src.buffer = decoded;
      src.connect(ctx.destination);
      src.onended = () => {
        if (generation !== this.playbackGeneration || this.activeSource !== src) return;
        this.activeSource = null;
        this._playNext();
      };
      this.activeSource = src;
      src.start();
    } catch {
      // Decode error — skip this chunk and continue
      if (generation === this.playbackGeneration) this._playNext();
    }
  }

  clear(): void {
    this.playbackGeneration++;
    this.queue = [];
    this.playing = false;
    const source = this.activeSource;
    this.activeSource = null;
    if (!source) return;

    try {
      source.stop();
    } catch {
      // Best effort: stop() can throw if the source already ended.
    }
    try {
      source.disconnect();
    } catch {
      // Best effort cleanup for browser implementations that throw here.
    }
  }
}
