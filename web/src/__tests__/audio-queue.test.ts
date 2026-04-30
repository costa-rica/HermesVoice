import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AudioQueue } from '../audio';

type SourceDouble = {
  buffer: unknown;
  connect: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
  onended: (() => void) | null;
};

let sources: SourceDouble[];
let decodeAudioData: ReturnType<typeof vi.fn>;
let resume: ReturnType<typeof vi.fn>;

function makeSource(): SourceDouble {
  return {
    buffer: null,
    connect: vi.fn(),
    disconnect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    onended: null,
  };
}

function flushPromises(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function waitForSources(count: number): Promise<void> {
  for (let i = 0; i < 10 && sources.length < count; i++) {
    await flushPromises();
  }
}

function enqueueChunk(queue: AudioQueue, id: number): void {
  queue.enqueue(new Uint8Array([id]).buffer);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function makeQueue(): Promise<AudioQueue> {
  const mod = await import('../audio');
  return new mod.AudioQueue();
}

describe('AudioQueue stoppable playback', () => {
  beforeEach(() => {
    sources = [];
    decodeAudioData = vi.fn().mockImplementation(async (buf: ArrayBuffer) => ({
      decoded: new Uint8Array(buf)[0],
    }));
    resume = vi.fn().mockResolvedValue(undefined);

    class MockAudioContext {
      state = 'running';
      destination = {};
      resume = resume;
      decodeAudioData = decodeAudioData;
      createBufferSource = vi.fn().mockImplementation(() => {
        const source = makeSource();
        sources.push(source);
        return source;
      });
    }

    class MockBlob {
      private parts: ArrayBuffer[];

      constructor(parts: ArrayBuffer[]) {
        this.parts = parts;
      }

      async arrayBuffer(): Promise<ArrayBuffer> {
        return this.parts[0];
      }
    }

    vi.stubGlobal('Blob', MockBlob);
    vi.stubGlobal('AudioContext', MockAudioContext);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('clear empties queued chunks and stops active browser playback', async () => {
    const queue = await makeQueue();

    enqueueChunk(queue, 1);
    enqueueChunk(queue, 2);
    await waitForSources(1);

    queue.clear();
    sources[0].onended?.();
    await flushPromises();

    expect(sources[0].stop).toHaveBeenCalledTimes(1);
    expect(sources[0].disconnect).toHaveBeenCalledTimes(1);
    expect(sources).toHaveLength(1);
  });

  it('does not let a stopped source onended start stale queued audio', async () => {
    const queue = await makeQueue();

    enqueueChunk(queue, 1);
    enqueueChunk(queue, 2);
    await waitForSources(1);

    queue.clear();
    sources[0].onended?.();
    await flushPromises();

    expect(sources).toHaveLength(1);
  });

  it('plays non-canceled chunks sequentially when onended fires', async () => {
    const queue = await makeQueue();

    enqueueChunk(queue, 1);
    enqueueChunk(queue, 2);
    await waitForSources(1);

    expect(sources).toHaveLength(1);

    sources[0].onended?.();
    await waitForSources(2);

    expect(sources).toHaveLength(2);
    expect(sources[0].start).toHaveBeenCalledTimes(1);
    expect(sources[1].start).toHaveBeenCalledTimes(1);
  });

  it('skips decode failures and continues to later queued chunks', async () => {
    decodeAudioData
      .mockRejectedValueOnce(new Error('bad audio'))
      .mockResolvedValueOnce({ decoded: 2 });
    const queue = await makeQueue();

    enqueueChunk(queue, 1);
    enqueueChunk(queue, 2);
    await waitForSources(1);

    expect(sources).toHaveLength(1);
    expect(sources[0].start).toHaveBeenCalledTimes(1);
  });

  it('does not start audio when decode finishes after clear', async () => {
    const decode = deferred<unknown>();
    decodeAudioData.mockReturnValueOnce(decode.promise);
    const queue = await makeQueue();

    enqueueChunk(queue, 1);
    for (let i = 0; i < 10 && decodeAudioData.mock.calls.length === 0; i++) {
      await flushPromises();
    }

    queue.clear();
    decode.resolve({ decoded: 1 });
    await flushPromises();

    expect(sources).toHaveLength(0);
  });
});
