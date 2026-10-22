import type { DiagramSpec } from '../specs';

/** Audiobook: from a book file to a chaptered M4B/MP3, chapter by chapter. */
const spec: DiagramSpec = {
  width: 920,
  height: 330,
  nodes: [
    { id: 'book', x: 10, y: 40, w: 130, h: 80, tone: 'ui' },
    { id: 'import', x: 185, y: 40, w: 175, h: 80, tone: 'backend' },
    { id: 'script', x: 405, y: 40, w: 145, h: 80, tone: 'ui' },
    { id: 'plan', x: 595, y: 40, w: 145, h: 80, tone: 'backend' },
    { id: 'queue', x: 785, y: 40, w: 125, h: 80, tone: 'backend' },
    { id: 'out', x: 10, y: 220, w: 145, h: 88, tone: 'ui' },
    { id: 'assemble', x: 195, y: 220, w: 170, h: 88, tone: 'backend' },
    { id: 'wavs', x: 405, y: 216, w: 160, h: 96, tone: 'data', shape: 'store' },
    { id: 'engine', x: 605, y: 220, w: 160, h: 88, tone: 'remote' },
    { id: 'manifest', x: 800, y: 216, w: 110, h: 96, tone: 'data', shape: 'store' },
  ],
  edges: [
    { from: 'book', to: 'import' },
    { from: 'import', to: 'script' },
    { from: 'script', to: 'plan' },
    { from: 'plan', to: 'queue' },
    { from: 'queue', to: 'manifest', id: 'saved', dashed: true },
    { from: 'queue', to: 'engine', id: 'missing' },
    { from: 'queue', to: 'wavs', id: 'hit', dashed: true },
    { from: 'engine', to: 'wavs' },
    { from: 'wavs', to: 'assemble' },
    { from: 'assemble', to: 'out' },
  ],
};

export default spec;
