import type { DiagramSpec } from '../specs';

/** The batch queue: files wait in line, one job runs at a time. */
const spec: DiagramSpec = {
  width: 920,
  height: 330,
  groups: [{ id: 'worker', x: 355, y: 20, w: 560, h: 200, tone: 'backend' }],
  nodes: [
    { id: 'files', x: 10, y: 50, w: 140, h: 70, tone: 'ui' },
    { id: 'queue', x: 200, y: 50, w: 110, h: 70, tone: 'data', shape: 'store' },
    { id: 'extract', x: 370, y: 60, w: 95, h: 60, tone: 'backend' },
    { id: 'asr', x: 480, y: 60, w: 95, h: 60, tone: 'engine' },
    { id: 'mt', x: 590, y: 60, w: 95, h: 60, tone: 'engine' },
    { id: 'tts', x: 700, y: 60, w: 95, h: 60, tone: 'engine' },
    { id: 'mix', x: 810, y: 60, w: 95, h: 60, tone: 'backend' },
    { id: 'perlang', x: 590, y: 145, w: 315, h: 50, tone: 'neutral' },
    { id: 'outputs', x: 760, y: 250, w: 150, h: 64, tone: 'data', shape: 'store' },
    { id: 'tabs', x: 330, y: 250, w: 300, h: 64, tone: 'ui' },
  ],
  edges: [
    { from: 'files', to: 'queue', id: 'enqueue' },
    { from: 'queue', to: 'extract', id: 'next' },
    { from: 'extract', to: 'asr' },
    { from: 'asr', to: 'mt' },
    { from: 'mt', to: 'tts' },
    { from: 'tts', to: 'mix' },
    { from: 'mix', to: 'outputs' },
    { from: 'queue', to: 'tabs', id: 'status', dashed: true, via: [[255, 282]] },
  ],
};

export default spec;
