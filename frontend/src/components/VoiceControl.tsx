import { useEffect, useRef, useState } from 'react';
import { browserVoiceEnvironment, createVoiceRecorder, type VoiceStatus } from '../lib/voice';
import Icon from './Icon';

type Props = {
  disabled: boolean;
  available: boolean;
  mockMode: boolean;
  message: string;
  onStart: () => boolean;
  onAudio: (audio: Blob) => Promise<void>;
  onCancel: () => void;
};

export default function VoiceControl(props: Props) {
  const [status, setStatus] = useState<VoiceStatus | 'transcribing'>('idle');
  const [supported, setSupported] = useState(false);
  const [error, setError] = useState('');
  const held = useRef(false);
  const mounted = useRef(false);
  const recorder = useRef<ReturnType<typeof createVoiceRecorder> | null>(null);
  const latest = useRef(props); latest.current = props;

  useEffect(() => {
    mounted.current = true;
    const environment = browserVoiceEnvironment();
    setSupported(environment !== null);
    if (environment) recorder.current = createVoiceRecorder(environment, {
      onStatus(value) { if (value === 'idle' || value === 'stopping') held.current = false; if (mounted.current) setStatus(value); },
      onCancel() { latest.current.onCancel(); },
      onError(message) { if (mounted.current) setError(message); },
      onAudio(audio) {
        if (!mounted.current) return;
        setStatus('transcribing');
        void latest.current.onAudio(audio).catch(() => { if (mounted.current) setError('The voice command could not be processed. Use Check step.'); })
          .finally(() => { if (mounted.current) setStatus('idle'); });
      },
    });
    const cancel = () => { held.current = false; recorder.current?.cancel(); };
    const visibility = () => { if (document.hidden) cancel(); };
    window.addEventListener('blur', cancel);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      mounted.current = false; recorder.current?.dispose(); recorder.current = null;
      window.removeEventListener('blur', cancel); document.removeEventListener('visibilitychange', visibility);
    };
  }, []);

  useEffect(() => { if (!props.available) { held.current = false; recorder.current?.cancel(); } }, [props.available]);

  function start() {
    if (held.current || status !== 'idle' || props.disabled || !recorder.current || !props.onStart()) return;
    held.current = true; setError(''); void recorder.current.start();
  }
  function release() { if (held.current) { held.current = false; recorder.current?.release(); } }
  function cancel() { held.current = false; recorder.current?.cancel(); }
  const working = status === 'transcribing' || status === 'stopping';
  return <div className="voice-control">
    <button className={`button secondary small voice-button ${status === 'recording' ? 'is-recording' : ''}`}
      disabled={!supported || working || (props.disabled && status === 'idle')}
      aria-label="Hold to record a step command" aria-describedby="voice-help" aria-pressed={status === 'recording'}
      onPointerDown={event => { if (event.button !== 0) return; event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId); start(); }}
      onPointerUp={release} onPointerCancel={cancel} onLostPointerCapture={() => { if (held.current) cancel(); }}
      onKeyDown={event => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); if (!event.repeat) start(); } if (event.key === 'Escape') cancel(); }}
      onKeyUp={event => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); release(); } }}
      onBlur={() => { if (held.current) cancel(); }} onContextMenu={event => event.preventDefault()}>
      {working ? <span className="spinner" /> : <Icon name="mic" size={15} />}
      {status === 'requesting' ? 'Allow microphone, then keep holding…' : status === 'recording' ? 'Recording… release to check' : working ? 'Processing voice…' : 'Hold to speak'}
    </button>
    <p id="voice-help">{!supported ? 'Voice recording is unavailable in this browser. Use Check step.' : 'Hold mouse, touch, Space, or Enter. Say “step done”, “check step”, or “next step”. Up to 5 seconds. Escape cancels.'}</p>
    {props.mockMode && <p className="voice-mock">MOCK transcription always returns “step done”; recorded speech is not recognized.</p>}
    <p className="voice-status" role="status">{error || props.message}</p>
  </div>;
}
