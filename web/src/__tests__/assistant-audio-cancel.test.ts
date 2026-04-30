import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AudioQueue } from '../audio';
import { updateCancelVisibility, updateTimings, updateTurnState } from '../ui';

vi.mock('../ui', () => ({
  renderApp: vi.fn(),
  isBackendTurnCancellable: (state: string) => (
    state === 'thinking'
    || state === 'thinking_progress'
    || state === 'speaking'
  ),
  updateConnectionState: vi.fn(),
  updateTurnState: vi.fn(),
  appendMessage: vi.fn(),
  clearError: vi.fn(),
  showError: vi.fn(),
  showToast: vi.fn(),
  updateCancelVisibility: vi.fn(),
  updateTimings: vi.fn(),
}));

let playbackActiveChanged: ((active: boolean) => void) | null = null;

vi.mock('../audio', () => ({
  MicCapture: vi.fn().mockImplementation(() => ({
    init: vi.fn().mockResolvedValue(undefined),
    start: vi.fn(),
    stop: vi.fn().mockResolvedValue(new Blob()),
    getAudioFormat: vi.fn().mockReturnValue('webm/opus'),
  })),
  AudioQueue: vi.fn().mockImplementation((onPlaybackActiveChanged?: (active: boolean) => void) => {
    playbackActiveChanged = onPlaybackActiveChanged ?? null;
    return {
    enqueue: vi.fn(),
    clear: vi.fn(),
    };
  }),
}));

import { App } from '../app';

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
  simulateBinary(data?: ArrayBuffer): void;
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

    simulateBinary(data = new ArrayBuffer(4)) {
      this.onmessage?.({ data });
    }
  }
  return MockWebSocket;
}

function setupDom() {
  document.body.innerHTML = `
    <div id="app"></div>
    <button id="btn-ptt">PTT</button>
    <button id="btn-cancel">Cancel</button>
  `;
}

async function connectAndReady(app: App): Promise<void> {
  await app.start();
  mockWsInstance!.simulateOpen();
  mockWsInstance!.simulateJson({
    event: 'session_started',
    conversation_id: 'test-conv-id',
  });
}

function audioQueueMock() {
  return vi.mocked(AudioQueue).mock.results[0].value as {
    enqueue: ReturnType<typeof vi.fn>;
    clear: ReturnType<typeof vi.fn>;
  };
}

describe('assistant audio cancel', () => {
  let app: App;

  beforeEach(() => {
    vi.useFakeTimers();
    setupDom();
    mockWsInstance = null;
    playbackActiveChanged = null;
    wsConstructionCount = 0;
    vi.stubGlobal('WebSocket', makeMockWebSocketClass());
    app = new App(document.getElementById('app')!);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it.each(['thinking', 'speaking'] as const)(
    'clicking cancel sends exactly one cancel_turn frame when backend state is %s',
    async (state) => {
    await connectAndReady(app);
    mockWsInstance!.simulateJson({ event: 'active_state', state });

    document.getElementById('btn-cancel')!.click();

    const cancelFrames = mockWsInstance!.send.mock.calls
      .map(([raw]) => JSON.parse(raw as string) as { event: string })
      .filter((frame) => frame.event === 'cancel_turn');
    expect(cancelFrames).toHaveLength(1);
    }
  );

  it('clicking cancel clears local assistant audio immediately', async () => {
    await connectAndReady(app);
    const queue = audioQueueMock();

    document.getElementById('btn-cancel')!.click();

    expect(queue.clear).toHaveBeenCalledTimes(1);
  });

  it('clicking cancel optimistically returns the local turn state to idle', async () => {
    await connectAndReady(app);

    document.getElementById('btn-cancel')!.click();

    expect(vi.mocked(updateTurnState)).toHaveBeenLastCalledWith('idle');
  });

  it('ignores binary audio frames that arrive after cancel', async () => {
    await connectAndReady(app);
    const queue = audioQueueMock();

    document.getElementById('btn-cancel')!.click();
    vi.mocked(updateTimings).mockClear();
    queue.enqueue.mockClear();

    mockWsInstance!.simulateBinary();

    expect(queue.enqueue).not.toHaveBeenCalled();
    expect(vi.mocked(updateTimings)).not.toHaveBeenCalled();
  });

  it('starting a new recording clears the cancel guard so next audio can play', async () => {
    await connectAndReady(app);
    const queue = audioQueueMock();

    document.getElementById('btn-cancel')!.click();
    queue.enqueue.mockClear();

    document.getElementById('btn-ptt')!.dispatchEvent(new Event('pointerdown'));
    mockWsInstance!.simulateBinary();

    expect(queue.enqueue).toHaveBeenCalledTimes(1);
  });

  it('keeps cancel visible after audio starts and backend returns idle', async () => {
    await connectAndReady(app);
    mockWsInstance!.simulateJson({ event: 'active_state', state: 'speaking' });

    playbackActiveChanged?.(true);
    mockWsInstance!.simulateJson({ event: 'active_state', state: 'idle' });

    expect(vi.mocked(updateCancelVisibility)).toHaveBeenLastCalledWith('idle', true);
  });

  it('playback-only idle cancel clears audio but does not send cancel_turn', async () => {
    await connectAndReady(app);
    const queue = audioQueueMock();

    playbackActiveChanged?.(true);
    mockWsInstance!.simulateJson({ event: 'active_state', state: 'idle' });
    mockWsInstance!.send.mockClear();

    document.getElementById('btn-cancel')!.click();

    expect(queue.clear).toHaveBeenCalledTimes(1);
    expect(mockWsInstance!.send).not.toHaveBeenCalled();
  });

  it('hides cancel when playback naturally becomes inactive and backend is idle', async () => {
    await connectAndReady(app);

    playbackActiveChanged?.(true);
    mockWsInstance!.simulateJson({ event: 'active_state', state: 'idle' });
    playbackActiveChanged?.(false);

    expect(vi.mocked(updateCancelVisibility)).toHaveBeenLastCalledWith('idle', false);
  });

  it('close cleanup clears audio and reconnect cleanup allows future audio', async () => {
    await connectAndReady(app);
    const queue = audioQueueMock();
    const countAfterConnect = wsConstructionCount;

    document.getElementById('btn-cancel')!.click();
    queue.clear.mockClear();
    queue.enqueue.mockClear();

    mockWsInstance!.onclose?.();

    expect(queue.clear).toHaveBeenCalledTimes(1);

    (app as unknown as { triggerReconnect: () => void }).triggerReconnect();
    expect(wsConstructionCount).toBeGreaterThan(countAfterConnect);

    mockWsInstance!.simulateOpen();
    mockWsInstance!.simulateJson({
      event: 'session_started',
      conversation_id: 'future-session-id',
    });
    mockWsInstance!.simulateBinary();

    expect(queue.enqueue).toHaveBeenCalledTimes(1);
  });
});
