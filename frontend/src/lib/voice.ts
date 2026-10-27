export const MAX_AUDIO_BYTES = 5 * 1024 * 1024;
export const MAX_RECORDING_MS = 5000;
export type VoiceStatus = 'idle' | 'requesting' | 'recording' | 'stopping';
export type VoiceEnvironment = {
  mime: string;
  acquire: () => Promise<MediaStream>;
  recorder: (stream: MediaStream, mime: string) => MediaRecorder;
  now: () => number;
  after: (callback: () => void, milliseconds: number) => ReturnType<typeof setTimeout>;
  clear: (timer: ReturnType<typeof setTimeout>) => void;
};

export function matchVoiceCommand(text: string): boolean {
  return /^(step done|check step|next step)$/.test(text.trim().toLowerCase().replace(/[.!?]+$/, '').trim().replace(/\s+/g, ' '));
}

export function browserVoiceEnvironment(): VoiceEnvironment | null {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') return null;
  let mime: string | undefined;
  try { mime = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type)); }
  catch { return null; }
  if (!mime) return null;
  return { mime, acquire: () => navigator.mediaDevices.getUserMedia({ audio: true, video: false }),
    recorder: (stream, type) => new MediaRecorder(stream, { mimeType: type }), now: () => performance.now(),
    after: (callback, milliseconds) => setTimeout(callback, milliseconds), clear: timer => clearTimeout(timer) };
}

// Owns microphone lifetime, including a permission grant arriving after release/cancel.
export function createVoiceRecorder(environment: VoiceEnvironment, callbacks: {
  onStatus: (status: VoiceStatus) => void;
  onAudio: (audio: Blob) => void;
  onCancel: () => void;
  onError: (message: string) => void;
}) {
  let status: VoiceStatus = 'idle';
  let generation = 0;
  let stream: MediaStream | null = null;
  let recorder: MediaRecorder | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let chunks: Blob[] = [];
  let size = 0;
  let startedAt = 0;
  const setStatus = (value: VoiceStatus) => { status = value; callbacks.onStatus(value); };
  function clean() {
    if (timer !== undefined) environment.clear(timer);
    timer = undefined;
    if (recorder) {
      recorder.ondataavailable = null; recorder.onstop = null; recorder.onerror = null;
      if (recorder.state !== 'inactive') { try { recorder.stop(); } catch { /* Release tracks below. */ } }
    }
    recorder = null;
    releaseTracks(); chunks = []; size = 0;
  }
  function releaseTracks() {
    stream?.getTracks().forEach(track => { track.onended = null; track.stop(); }); stream = null;
  }
  function cancel() {
    if (status === 'idle') return;
    generation += 1; clean(); setStatus('idle'); callbacks.onCancel();
  }
  function fail(message: string) { cancel(); callbacks.onError(message); }
  function release() {
    if (status === 'requesting') { cancel(); return; }
    if (status !== 'recording' || !recorder) return;
    if (environment.now() - startedAt < 250) { fail('Hold the microphone button a little longer, or use Check step.'); return; }
    setStatus('stopping');
    if (timer !== undefined) environment.clear(timer);
    try { recorder.stop(); releaseTracks(); }
    catch { fail('The recording could not be finished. Use Check step or try again.'); }
  }
  return {
    async start() {
      if (status !== 'idle') return;
      const current = ++generation;
      setStatus('requesting');
      try {
        const acquired = await environment.acquire();
        if (current !== generation) { acquired.getTracks().forEach(track => track.stop()); return; }
        stream = acquired;
        for (const track of acquired.getTracks()) track.onended = () => { if (current === generation) fail('The microphone disconnected. Use Check step or record again.'); };
        const recording = environment.recorder(acquired, environment.mime);
        recorder = recording;
        recording.ondataavailable = event => {
          if (current !== generation || !event.data.size) return;
          chunks.push(event.data); size += event.data.size;
          if (size > MAX_AUDIO_BYTES) fail('The audio clip is too large. Record a shorter command.');
        };
        recording.onerror = () => { if (current === generation) fail('The microphone could not record. Use Check step or try again.'); };
        recording.onstop = () => {
          if (current !== generation) return;
          if (status !== 'stopping') { fail('Recording ended unexpectedly. Hold the microphone button to try again.'); return; }
          const audio = new Blob(chunks, { type: recording.mimeType || environment.mime });
          clean(); setStatus('idle');
          if (!audio.size) { callbacks.onCancel(); callbacks.onError('No audio was recorded. Try again or use Check step.'); }
          else callbacks.onAudio(audio);
        };
        recording.start(250);
        startedAt = environment.now(); setStatus('recording');
        timer = environment.after(release, MAX_RECORDING_MS);
      } catch (cause) {
        if (current !== generation) return;
        const name = cause instanceof DOMException ? cause.name : '';
        fail(name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in your browser, or use Check step.' :
          name === 'NotFoundError' ? 'No microphone was found. Connect one, or use Check step.' :
          'The microphone is unavailable. Use Check step or try recording again.');
      }
    },
    release,
    cancel,
    dispose: cancel,
  };
}
