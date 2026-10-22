import type { DiagramSpec } from '../specs';

/** One dub, from the imported file to the exported video. */
const spec: DiagramSpec = {
  width: 920,
  height: 430,
  nodes: [
    { id: 'import', x: 10, y: 40, w: 150, h: 76, tone: 'ui' },
    { id: 'prepare', x: 195, y: 40, w: 150, h: 76, tone: 'engine' },
    { id: 'transcribe', x: 380, y: 40, w: 150, h: 76, tone: 'engine' },
    { id: 'review', x: 565, y: 40, w: 150, h: 76, tone: 'ui' },
    { id: 'translate', x: 750, y: 40, w: 160, h: 76, tone: 'engine' },
    { id: 'cast', x: 750, y: 200, w: 160, h: 76, tone: 'ui' },
    { id: 'generate', x: 565, y: 200, w: 150, h: 76, tone: 'engine' },
    { id: 'mix', x: 380, y: 200, w: 150, h: 76, tone: 'backend' },
    { id: 'export', x: 195, y: 200, w: 150, h: 76, tone: 'ui' },
    { id: 'qc', x: 380, y: 340, w: 150, h: 64, tone: 'engine' },
  ],
  edges: [
    { from: 'import', to: 'prepare' },
    { from: 'prepare', to: 'transcribe' },
    { from: 'transcribe', to: 'review' },
    { from: 'review', to: 'translate' },
    { from: 'translate', to: 'cast' },
    { from: 'cast', to: 'generate' },
    { from: 'generate', to: 'mix' },
    { from: 'mix', to: 'export' },
    { from: 'mix', to: 'qc', id: 'check', dashed: true },
    { from: 'qc', to: 'generate', id: 'redo', dashed: true, via: [[640, 372]] },
  ],
};

export default spec;
