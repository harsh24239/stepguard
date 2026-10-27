type Name = 'shield' | 'camera' | 'upload' | 'check' | 'lock' | 'refresh' | 'mute' | 'speaker' | 'close' | 'arrow' | 'alert' | 'mic' | 'grid' | 'book' | 'history' | 'layers' | 'crosshair' | 'file' | 'chevron';
const paths: Record<Name, string> = {
  grid: 'M3 3h7v7H3V3Z M14 3h7v7h-7V3Z M3 14h7v7H3v-7Z M14 14h7v7h-7v-7Z',
  book: 'M12 5C9 3 5 3 2 4v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Zm0 0v15',
  history: 'M3 10a9 9 0 1 1 1 7 M3 4v6h6 M12 7v5l3 2',
  layers: 'm12 3 10 5-10 5L2 8l10-5Z M2 12l10 5 10-5 M2 16l10 5 10-5',
  crosshair: 'M12 2v4 M12 18v4 M2 12h4 M18 12h4 M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z M12 10v4 M10 12h4',
  file: 'M5 2h9l5 5v15H5V2Z M14 2v6h5 M8 12h8 M8 16h6',
  chevron: 'm9 5 7 7-7 7',
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
