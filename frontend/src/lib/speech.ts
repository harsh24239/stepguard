export type SpeechAdapter = { cancel: () => void; speak: (message: string) => void };

export function browserSpeech(): SpeechAdapter | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') return null;
  return {
    cancel: () => window.speechSynthesis.cancel(),
    speak: message => {
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.rate = 1;
      window.speechSynthesis.speak(utterance);
    },
  };
}

export function createSpeaker(adapter: SpeechAdapter | null) {
  let muted = false;
  let lastId: number | null = null;
  const cancel = () => { try { adapter?.cancel(); } catch { /* Text feedback remains available. */ } };
  return {
    supported: adapter !== null,
    setMuted(value: boolean) { muted = value; if (value) cancel(); },
    speak(id: number, message: string) {
      if (!adapter || muted || id === lastId) return;
      lastId = id;
      cancel();
      try { adapter.speak(message); } catch { /* Browser speech is optional; always show the result. */ }
    },
    cancel,
  };
}
