import { MAX_AUDIO_BYTES } from './voice';

const RATE = 16000;
const MAX_SECONDS = 6; // Five-second recorder plus a small browser scheduling allowance.
const conversionError = () => new Error('Recorded audio could not be converted to PCM WAV. Use Check step or record again.');

export function encodePcmWav(samples: Float32Array, sampleRate: 16000 | 24000 = RATE): Blob {
  if (![16000, 24000].includes(sampleRate) || !samples.length || samples.length > sampleRate * MAX_SECONDS || !samples.every(Number.isFinite)) throw conversionError();
  const bytes = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(bytes);
  const text = (offset: number, value: string) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, 'RIFF'); view.setUint32(4, bytes.byteLength - 8, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, samples.length * 2, true);
  samples.forEach((value, index) => { const clipped = Math.max(-1, Math.min(1, value)); view.setInt16(44 + index * 2, Math.round(clipped * (clipped < 0 ? 32768 : 32767)), true); });
  return new Blob([bytes], { type: 'audio/wav' });
}

async function renderMono(bytes: ArrayBuffer): Promise<Float32Array> {
  const environment = window as typeof window & { webkitAudioContext?: typeof AudioContext };
  const Decoder = environment.AudioContext ?? environment.webkitAudioContext;
  if (!Decoder || !environment.OfflineAudioContext) throw conversionError();
  const decoder = new Decoder();
  try {
    const audio = await decoder.decodeAudioData(bytes);
    if (!Number.isFinite(audio.duration) || audio.duration <= 0 || audio.duration > MAX_SECONDS) throw conversionError();
    // Web Audio performs channel downmixing and filtered resampling, rather than
    // dropping samples or treating compressed bytes as PCM.
    const renderer = new environment.OfflineAudioContext(1, Math.ceil(audio.duration * RATE), RATE);
    const source = renderer.createBufferSource(); source.buffer = audio;
    source.connect(renderer.destination); source.start(0);
    const rendered = await renderer.startRendering();
    return rendered.getChannelData(0).slice();
  } finally { await decoder.close().catch(() => {}); }
}

export async function toVoiceWav(audio: Blob, render = renderMono): Promise<Blob> {
  if (!audio.size || audio.size > MAX_AUDIO_BYTES) throw conversionError();
  try { return encodePcmWav(await render(await audio.arrayBuffer())); }
  catch { throw conversionError(); }
}
