import type { Box, CapturedFrame, Step, VerifyResult } from './types';

export const colors = { ok: '#86e0b6', bad: '#fa8585', unsure: '#efbc68', missing: '#f2d574' };

export function overlayColor(result: VerifyResult, status: 'ok' | 'bad'): string {
  return result.verdict === 'unsure' ? colors.unsure : status === 'bad' ? colors.bad : colors.ok;
}

export function containRect(width: number, height: number, targetWidth: number, targetHeight: number) {
  const scale = Math.min(targetWidth / width, targetHeight / height);
  const w = width * scale;
  const h = height * scale;
  return { x: (targetWidth - w) / 2, y: (targetHeight - h) / 2, width: w, height: h };
}

export function captureFrame(video: HTMLVideoElement): CapturedFrame {
  if (!video.videoWidth || !video.videoHeight || video.readyState < 2) throw new Error('Wait for the camera image, then check again.');
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('This browser could not capture a camera frame.');
  const rect = containRect(video.videoWidth, video.videoHeight, canvas.width, canvas.height);
  context.fillStyle = '#080c10';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(video, rect.x, rect.y, rect.width, rect.height);
  const dataUrl = canvas.toDataURL('image/jpeg', .9);
  return { dataUrl, base64: dataUrl.slice(dataUrl.indexOf(',') + 1), width: canvas.width, height: canvas.height };
}

export function missingZones(result: VerifyResult, step: Step | undefined): { label: string; box: Box }[] {
  if (!step || result.verdict === 'unsure') return [];
  const quadrants = ['top_left', 'top_right', 'bottom_left', 'bottom_right'];
  return result.issues.filter(issue => issue.type === 'missing').flatMap(issue => {
    const rule = step.spatial_rules.find(rule => rule.part === issue.part && quadrants.includes(rule.relation));
    const location = issue.location_hint.toLowerCase().replaceAll('-', '_');
    const quadrant = rule?.relation ?? (quadrants.includes(location) ? location : null);
    const target = result.masks.find(mask => mask.label === (rule?.target ?? step.zone_anchor));
    if (!quadrant || !target) return [];
    const [left, top, right, bottom] = target.box;
    const midX = (left + right) / 2;
    const midY = (top + bottom) / 2;
    return [{ label: `Expected ${issue.part}`, box: [quadrant.endsWith('left') ? left : midX,
      quadrant.startsWith('top') ? top : midY, quadrant.endsWith('left') ? midX : right,
      quadrant.startsWith('top') ? midY : bottom] as Box }];
  });
}

async function tintMask(base64: string, width: number, height: number, color: string): Promise<HTMLCanvasElement | null> {
  if (!base64) return null;
  const image = new Image();
  image.src = `data:image/png;base64,${base64}`;
  await image.decode();
  if (image.width !== width || image.height !== height) throw new Error('Mask dimensions do not match the captured frame.');
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(image, 0, 0);
  const pixels = context.getImageData(0, 0, width, height);
  const data = pixels.data;
  let alphaMask = false;
  for (let index = 3; index < data.length; index += 4) if (data[index] !== 255) { alphaMask = true; break; }
  const rgb = [1, 3, 5].map(offset => parseInt(color.slice(offset, offset + 2), 16));
  for (let index = 0; index < data.length; index += 4) {
    const foreground = alphaMask ? data[index + 3] > 127 : .299 * data[index] + .587 * data[index + 1] + .114 * data[index + 2] > 127;
    data[index] = rgb[0]; data[index + 1] = rgb[1]; data[index + 2] = rgb[2]; data[index + 3] = foreground ? 48 : 0;
  }
  context.putImageData(pixels, 0, 0);
  return canvas;
}

export async function drawOverlay(canvas: HTMLCanvasElement, result: VerifyResult | null, step: Step | undefined,
  frame: CapturedFrame, cancelled: () => boolean): Promise<boolean> {
  canvas.width = frame.width;
  canvas.height = frame.height;
  const context = canvas.getContext('2d');
  if (!context || !result) return false;
  const layers = await Promise.all(result.masks.map(mask => tintMask(mask.mask_png_base64, frame.width, frame.height,
    overlayColor(result, mask.status)).then(canvas => ({ canvas, failed: false })).catch(() => ({ canvas: null, failed: true }))));
  if (cancelled()) return false;
  for (const layer of layers) if (layer.canvas) context.drawImage(layer.canvas, 0, 0);
  context.lineWidth = 2;
  context.font = '12px system-ui, sans-serif';
  function box(bounds: Box, label: string, color: string, dashed = false) {
    const [left, top, right, bottom] = bounds;
    context!.strokeStyle = color;
    context!.setLineDash(dashed ? [7, 5] : []);
    context!.strokeRect(left, top, right - left, bottom - top);
    context!.setLineDash([]);
    const textWidth = Math.min(frame.width - 12, context!.measureText(label).width + 12);
    const textX = Math.min(Math.max(0, left), frame.width - textWidth);
    const textY = Math.max(0, top - 24);
    context!.fillStyle = '#0b1119ee';
    context!.fillRect(textX, textY, textWidth, 22);
    context!.fillStyle = color;
    context!.fillText(label, textX + 6, textY + 15, textWidth - 8);
  }
  for (const mask of result.masks) box(mask.box, mask.label, overlayColor(result, mask.status));
  for (const zone of missingZones(result, step)) box(zone.box, zone.label, colors.missing, true);
  return layers.some(layer => layer.failed);
}
