type Name = 'shield' | 'camera' | 'upload' | 'check' | 'lock' | 'refresh' | 'mute' | 'speaker' | 'close' | 'arrow' | 'alert' | 'mic';
const paths: Record<Name, string> = {
  mic: 'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0V5Z M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8',
  shield: 'M12 3 20 6v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z M8 12l3 3 5-6',
  camera: 'M8 7l2-3h4l2 3h4v13H4V7h4Z M16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  upload: 'M12 16V3 M7 8l5-5 5 5 M4 15v6h16v-6',
  check: 'm5 12 4 4L19 6',
  lock: 'M7 10V7a5 5 0 0 1 10 0v3 M5 10h14v11H5V10Z M12 14v3',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 2 M18 18a8 8 0 0 1-13-2',
  mute: 'M11 5 6 9H3v6h3l5 4V5Z M16 9l6 6 M22 9l-6 6',
  speaker: 'M11 5 6 9H3v6h3l5 4V5Z M16 8a6 6 0 0 1 0 8 M19 5a10 10 0 0 1 0 14',
  close: 'm6 6 12 12 M18 6 6 18',
  arrow: 'M4 12h16 M14 6l6 6-6 6',
  alert: 'm12 3 10 18H2L12 3Z M12 9v5 M12 17v.1',
};

export default function Icon({ name, size = 18 }: { name: Name; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d={paths[name]} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}
