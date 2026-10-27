// Local pixel differences only. Model calls happen only after a motion-stop event.
export function frameDifference(current: Uint8ClampedArray, previous: Uint8ClampedArray): number {
  if (!current.length || current.length !== previous.length || current.length % 4) throw new Error('Invalid motion frame.');
  let difference = 0;
  for (let i = 0; i < current.length; i += 4) {
    difference += Math.abs(.299 * (current[i] - previous[i]) + .587 * (current[i + 1] - previous[i + 1]) + .114 * (current[i + 2] - previous[i + 2]));
  }
  return difference / (current.length / 4);
}

export function createMotionDetector(notBefore = -Infinity) {
  let previous: Uint8ClampedArray | null = null;
  let previousAt = -Infinity;
  let highSamples = 0;
  let moving = false;
  let stillSince: number | null = null;
  let cooldownUntil = notBefore;
  function reset() { previous = null; highSamples = 0; moving = false; stillSince = null; previousAt = -Infinity; }
  return {
    reset,
    sample(pixels: Uint8ClampedArray, now: number): boolean {
      // Re-baseline after a suspended/hidden tab, camera size change, or clock reset.
      if (now <= previousAt || now - previousAt > 500 || previous?.length !== pixels.length) reset();
      const score = previous ? frameDifference(pixels, previous) : 0;
      previous = pixels.slice(); previousAt = now;
      if (now < cooldownUntil) return false;
      if (score >= 12) {
        highSamples += 1;
        if (highSamples >= 2) moving = true;
        stillSince = null;
      } else {
        highSamples = 0;
        if (score > 6) stillSince = null;
        else if (moving) {
          stillSince ??= now;
          if (now - stillSince >= 700) {
            moving = false; stillSince = null; cooldownUntil = now + 2000;
            return true;
          }
        }
      }
      return false;
    },
  };
}

export function startMotionMonitor(video: HTMLVideoElement, onTrigger: () => void, onError: () => void, notBefore = -Infinity): () => void {
  const canvas = document.createElement('canvas');
  canvas.width = 64; canvas.height = 48;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) { onError(); return () => {}; }
  const detector = createMotionDetector(notBefore);
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  function visibility() { detector.reset(); }
  document.addEventListener('visibilitychange', visibility);
  function stop() {
    stopped = true; clearTimeout(timer);
    document.removeEventListener('visibilitychange', visibility); detector.reset();
  }
  function tick() {
    if (stopped) return;
    try {
      if (document.hidden || video.readyState < 2 || !video.videoWidth || !video.videoHeight) detector.reset();
      else {
        context!.drawImage(video, 0, 0, 64, 48);
        if (detector.sample(context!.getImageData(0, 0, 64, 48).data, performance.now())) {
          // One event per monitor lifetime. React rearms after the result is cleared.
          stop(); onTrigger(); return;
        }
      }
    } catch { stop(); onError(); return; }
    timer = setTimeout(tick, 100);
  }
  timer = setTimeout(tick, 100);
  return stop;
}
