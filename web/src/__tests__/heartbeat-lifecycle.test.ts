import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── Module mocks (must be before importing App) ──────────────────────────────

vi.mock('../ui', () => ({
  renderApp: vi.fn(),
  updateConnectionState: vi.fn(),
  updateTurnState: vi.fn(),
  appendMessage: vi.fn(),
  clearError: vi.fn(),
  showError: vi.fn(),
  showToast: vi.fn(),
  updateTimings: vi.fn(),
}));

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

const WS_CONNECTING = 0;
const WS_OPEN = 1;
const WS_CLOSING = 2;
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
  class MockWebSocket implements MockWsInstance {
    static CONNECTING = WS_CONNECTING;
    static OPEN = WS_OPEN;
    static CLOSING = WS_CLOSING;
    static CLOSED = WS_CLOSED;

    readyState = WS_CONNECTING;
    binaryType = 'arraybuffer';
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((evt: { data: string | ArrayBuffer }) => void) | null = null;
    send = vi.fn();
    close = vi.fn().mockImplementation(() => {
      this.readyState = WS_CLOSED;
    });

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

function setVisibilityState(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => state,
  });
}

function setupDom() {
  document.body.innerHTML = `
    <div id="app"></div>
    <button id="btn-ptt">PTT</button>
    <button id="btn-cancel">Cancel</button>
  `;
}

// Call private App methods directly to avoid DOM event listener accumulation
// between tests. We test the logic, not the event binding.
function hidden(a: App) {
  setVisibilityState('hidden');
  (a as unknown as Record<string, () => void>).handleVisibilityChange();
}

function visible(a: App) {
  setVisibilityState('visible');
  (a as unknown as Record<string, () => void>).handleVisibilityChange();
}

function pageShow(a: App) {
  (a as unknown as Record<string, () => void>).handlePageShow();
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

describe('heartbeat lifecycle fixes', () => {
  let app: App;

  beforeEach(() => {
    vi.useFakeTimers();
    setupDom();
    setVisibilityState('visible');
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

  it('stops heartbeat on hidden and prevents false reconnect on restore', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    // Fire heartbeat (15 s) → ping sent, pong timeout armed
    vi.advanceTimersByTime(15_000);
    expect(mockWsInstance!.send).toHaveBeenCalledWith(
      expect.stringContaining('"event":"ping"'),
    );

    // Tab goes hidden → heartbeat and pong timer should be cleared
    hidden(app);

    // Advance well past pong timeout (10 s) + another heartbeat (15 s)
    vi.advanceTimersByTime(30_000);

    // No new WebSocket created (no false reconnect)
    expect(wsConstructionCount).toBe(countAfterConnect);
  });

  it('does not reconnect when visible with open socket and sessionReady', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    hidden(app);
    visible(app);
    vi.advanceTimersByTime(500); // past debounce

    expect(wsConstructionCount).toBe(countAfterConnect);
  });

  it('triggers reconnect when visible with closed socket', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    // Force close without firing onclose (avoids auto-reconnect timer)
    mockWsInstance!.readyState = WS_CLOSED;

    visible(app);
    vi.advanceTimersByTime(500); // past debounce

    expect(wsConstructionCount).toBeGreaterThan(countAfterConnect);
  });

  it('debounces rapid lifecycle events (visibilitychange + pageshow) to one reconnect', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    // Force socket closed
    mockWsInstance!.readyState = WS_CLOSED;

    // Three rapid lifecycle events
    visible(app);
    pageShow(app);
    visible(app);

    // Before debounce resolves: no reconnect yet
    vi.advanceTimersByTime(100);
    expect(wsConstructionCount).toBe(countAfterConnect);

    // After debounce: exactly one reconnect
    vi.advanceTimersByTime(300);
    expect(wsConstructionCount).toBe(countAfterConnect + 1);
  });

  it('resumes heartbeat after tab restore when socket is open', async () => {
    await connectAndReady(app);

    hidden(app); // pause heartbeat

    // Socket stays open
    mockWsInstance!.readyState = WS_OPEN;
    mockWsInstance!.send.mockClear();

    visible(app);
    vi.advanceTimersByTime(500); // past debounce → heartbeat restarted

    vi.advanceTimersByTime(15_000); // full heartbeat interval

    expect(mockWsInstance!.send).toHaveBeenCalledWith(
      expect.stringContaining('"event":"ping"'),
    );
  });

  it('pong response clears timeout and prevents false reconnect', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    vi.advanceTimersByTime(15_000); // heartbeat fires

    // Receive pong before timeout
    mockWsInstance!.simulateJson({ event: 'pong', id: 'hb-1' });

    vi.advanceTimersByTime(10_000); // past pong timeout window

    expect(wsConstructionCount).toBe(countAfterConnect);
  });

  it('pong timeout skips reconnect when visibilityState is hidden (race guard)', async () => {
    await connectAndReady(app);
    const countAfterConnect = wsConstructionCount;

    vi.advanceTimersByTime(15_000); // ping sent, pong timer armed

    // Page becomes hidden without dispatching visibilitychange (race scenario)
    setVisibilityState('hidden');

    // Pong timeout fires — page is hidden, should NOT reconnect
    vi.advanceTimersByTime(10_000);

    expect(wsConstructionCount).toBe(countAfterConnect);
  });
});
