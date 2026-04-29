import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { updateConnectionState, showToast } from '../ui';

// Keep renderApp real so we can verify rendered HTML (button accessibility, etc.)
// Mock everything else so tests stay fast and isolated.
vi.mock('../ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../ui')>();
  return {
    ...actual,
    updateConnectionState: vi.fn().mockImplementation(actual.updateConnectionState),
    updateTurnState: vi.fn().mockImplementation(actual.updateTurnState),
    appendMessage: vi.fn(),
    clearError: vi.fn(),
    showError: vi.fn(),
    showToast: vi.fn(),
    updateTimings: vi.fn(),
  };
});

vi.mock('../audio', () => ({
  MicCapture: vi.fn().mockImplementation(() => ({
    init: vi.fn().mockResolvedValue(undefined),
    start: vi.fn(),
    stop: vi.fn().mockResolvedValue(new Blob()),
    getAudioFormat: vi.fn().mockReturnValue('webm'),
  })),
  AudioQueue: vi.fn().mockImplementation(() => ({
    enqueue: vi.fn(),
    clear: vi.fn(),
  })),
}));

import { App } from '../app';

// ── WebSocket mock ────────────────────────────────────────────────────────────

const WS_OPEN = 1;
const WS_CLOSED = 3;

interface MockWsInstance {
  readyState: number;
  binaryType: string;
  onopen: (() => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  onmessage: ((evt: { data: string | ArrayBuffer }) => void) | null;
  send: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
  simulateOpen(): void;
  simulateJson(data: object): void;
}

let mockWsInstance: MockWsInstance | null = null;
let wsConstructionCount = 0;

function makeMockWebSocketClass() {
  const WS_CONNECTING = 0;
  class MockWebSocket implements MockWsInstance {
    static CONNECTING = WS_CONNECTING;
    static OPEN = WS_OPEN;
    static CLOSING = 2;
    static CLOSED = WS_CLOSED;

    readyState = WS_CONNECTING;
    binaryType = 'arraybuffer';
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((evt: { data: string | ArrayBuffer }) => void) | null = null;
    send = vi.fn();
    close = vi.fn().mockImplementation(() => { this.readyState = WS_CLOSED; });

    constructor(_url: string) {
      wsConstructionCount++;
      mockWsInstance = this;
    }

    simulateOpen() {
      this.readyState = WS_OPEN;
      this.onopen?.();
    }

    simulateJson(data: object) {
      this.onmessage?.({ data: JSON.stringify(data) });
    }
  }
  return MockWebSocket;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setupDom() {
  // renderApp is real and will populate #app; we only need the root element here
  document.body.innerHTML = `<div id="app"></div>`;
}

async function connectAndReady(app: App): Promise<void> {
  await app.start();
  mockWsInstance!.simulateOpen();
  mockWsInstance!.simulateJson({
    event: 'session_started',
    conversation_id: 'test-conv-id',
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('connection status UX', () => {
  let app: App;

  beforeEach(() => {
    vi.useFakeTimers();
    setupDom();
    wsConstructionCount = 0;
    mockWsInstance = null;
    vi.stubGlobal('WebSocket', makeMockWebSocketClass());
    app = new App(document.getElementById('app')!);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  // ── Badge state transitions ─────────────────────────────────────────────────

  it('badge shows Ready after session_started', async () => {
    await connectAndReady(app);
    expect(vi.mocked(updateConnectionState)).toHaveBeenLastCalledWith('ready');
    const badge = document.getElementById('conn-state');
    expect(badge?.textContent).toBe('Ready');
  });

  it('badge shows Checking during initial connect before session', async () => {
    await app.start();
    mockWsInstance!.simulateOpen();
    // Socket open but no session_started yet
    const calls = vi.mocked(updateConnectionState).mock.calls.map((c) => c[0]);
    // Should have been called with 'checking' at some point, not 'connected'
    expect(calls).toContain('checking');
    expect(calls).not.toContain('connected');
  });

  it('badge shows Offline after socket closes', async () => {
    await connectAndReady(app);
    vi.mocked(updateConnectionState).mockClear();
    mockWsInstance!.onclose?.();
    expect(vi.mocked(updateConnectionState)).toHaveBeenCalledWith('offline');
    const badge = document.getElementById('conn-state');
    expect(badge?.textContent).toBe('Offline');
  });

  // ── Manual check button ─────────────────────────────────────────────────────

  it('check button renders with accessible title', () => {
    const btn = document.getElementById('btn-check-conn');
    expect(btn).toBeTruthy();
    expect(btn?.getAttribute('title')).toBe('Check connection');
    expect(btn?.getAttribute('aria-label')).toBe('Check connection');
  });

  it('check button sends ping and shows Checking when socket open', async () => {
    await connectAndReady(app);
    vi.mocked(updateConnectionState).mockClear();
    mockWsInstance!.send.mockClear();

    document.getElementById('btn-check-conn')!.click();

    expect(mockWsInstance!.send).toHaveBeenCalledWith(
      expect.stringContaining('"event":"ping"'),
    );
    expect(vi.mocked(updateConnectionState)).toHaveBeenCalledWith('checking');
  });

  it('matching pong shows Ready and toast', async () => {
    await connectAndReady(app);
    mockWsInstance!.send.mockClear();

    document.getElementById('btn-check-conn')!.click();

    // Extract the ping id from the sent JSON
    const raw: string = mockWsInstance!.send.mock.calls[0][0];
    const pingId: string = JSON.parse(raw).id;

    vi.mocked(updateConnectionState).mockClear();
    vi.mocked(showToast).mockClear();

    mockWsInstance!.simulateJson({ event: 'pong', id: pingId });

    expect(vi.mocked(updateConnectionState)).toHaveBeenLastCalledWith('ready');
    expect(vi.mocked(showToast)).toHaveBeenCalledWith(
      expect.stringContaining('checked'),
    );
  });

  it('check button triggers reconnect when socket not open', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    // Force socket closed without firing onclose (avoid auto-reconnect timer)
    mockWsInstance!.readyState = WS_CLOSED;

    document.getElementById('btn-check-conn')!.click();

    expect(wsConstructionCount).toBeGreaterThan(countAfterConnect);
  });

  // ── PTT gating (unchanged) ──────────────────────────────────────────────────

  it('PTT disabled before session is ready', async () => {
    await app.start();
    mockWsInstance!.simulateOpen();
    // Socket open but no session_started
    const pttBtn = document.getElementById('btn-ptt') as HTMLButtonElement;
    expect(pttBtn.disabled).toBe(true);
  });

  it('PTT enabled after session_started', async () => {
    await connectAndReady(app);
    const pttBtn = document.getElementById('btn-ptt') as HTMLButtonElement;
    expect(pttBtn.disabled).toBe(false);
  });

  it('PTT stays enabled while recording so mobile browsers do not cancel the press', async () => {
    await connectAndReady(app);
    const pttBtn = document.getElementById('btn-ptt') as HTMLButtonElement;

    pttBtn.dispatchEvent(new Event('pointerdown'));

    expect(pttBtn.disabled).toBe(false);
    expect(pttBtn.textContent).toBe('Release to Send');
    expect(pttBtn.classList.contains('recording')).toBe(true);
  });

  // ── Heartbeat badge behavior ────────────────────────────────────────────────

  it('heartbeat reconnect shows checking not connecting', async () => {
    await connectAndReady(app);
    vi.mocked(updateConnectionState).mockClear();

    vi.advanceTimersByTime(15_000); // heartbeat ping sent, pong timer armed
    vi.advanceTimersByTime(10_000); // pong timeout fires → triggerReconnect

    const states = vi.mocked(updateConnectionState).mock.calls.map((c) => c[0]);
    expect(states).toContain('checking');
    expect(states).not.toContain('connecting');
    expect(states).not.toContain('connected');
  });

  it('manual check pong timeout triggers reconnect', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    document.getElementById('btn-check-conn')!.click(); // ping sent

    // No pong arrives — manual check timeout fires
    vi.advanceTimersByTime(10_000);

    expect(wsConstructionCount).toBeGreaterThan(countAfterConnect);
  });
});
