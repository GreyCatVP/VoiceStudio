import type { DiagramSpec } from '../specs';

/** One file transcription, from the upload to the saved transcript. */
const spec: DiagramSpec = {
  width: 920,
  height: 300,
  nodes: [
    { id: 'pick', x: 5, y: 110, w: 125, h: 72, tone: 'ui' },
    { id: 'send', x: 155, y: 110, w: 130, h: 72, tone: 'backend' },
    { id: 'decode', x: 310, y: 110, w: 130, h: 72, tone: 'backend' },
    { id: 'fast', x: 470, y: 20, w: 140, h: 64, tone: 'engine' },
    { id: 'accurate', x: 470, y: 118, w: 140, h: 64, tone: 'engine' },
    { id: 'ray', x: 470, y: 225, w: 140, h: 60, tone: 'remote' },
    { id: 'align', x: 640, y: 118, w: 120, h: 64, tone: 'engine' },
    { id: 'polish', x: 640, y: 20, w: 120, h: 64, tone: 'backend' },
    { id: 'result', x: 790, y: 20, w: 125, h: 64, tone: 'ui' },
    { id: 'history', x: 790, y: 118, w: 125, h: 72, tone: 'data', shape: 'store' },
  ],
  edges: [
    { from: 'pick', to: 'send' },
    { from: 'send', to: 'decode' },
    { from: 'decode', to: 'fast' },
    { from: 'decode', to: 'accurate' },
    { from: 'accurate', to: 'ray', id: 'routed', dashed: true, both: true },
    { from: 'accurate', to: 'align' },
    { from: 'align', to: 'polish' },
    { from: 'fast', to: 'polish' },
    { from: 'polish', to: 'result' },
    { from: 'result', to: 'history', id: 'saved' },
  ],
};

export default spec;
