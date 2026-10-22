import type { DiagramSpec } from '../specs';

/** Something failed: which screen to open first, and where to go next. */
const spec: DiagramSpec = {
  width: 920,
  height: 480,
  nodes: [
    { id: 'fail', x: 10, y: 24, w: 160, h: 56, tone: 'neutral' },
    { id: 'q1', x: 210, y: 20, w: 190, h: 64, tone: 'neutral' },
    { id: 'a1', x: 440, y: 20, w: 220, h: 64, tone: 'ui' },
    { id: 'q2', x: 210, y: 120, w: 190, h: 64, tone: 'neutral' },
    { id: 'a2', x: 440, y: 120, w: 220, h: 64, tone: 'backend' },
    { id: 'q3', x: 210, y: 220, w: 190, h: 64, tone: 'neutral' },
    { id: 'a3', x: 440, y: 220, w: 220, h: 64, tone: 'remote' },
    { id: 'logs', x: 440, y: 320, w: 220, h: 64, tone: 'data' },
    { id: 'agent', x: 720, y: 400, w: 190, h: 64, tone: 'ui' },
    { id: 'report', x: 720, y: 320, w: 190, h: 64, tone: 'neutral' },
  ],
  edges: [
    { from: 'fail', to: 'q1' },
    { from: 'q1', to: 'a1', id: 'yes1' },
    { from: 'q1', to: 'q2', id: 'no1' },
    { from: 'q2', to: 'a2', id: 'yes2' },
    { from: 'q2', to: 'q3', id: 'no2' },
    { from: 'q3', to: 'a3', id: 'yes3' },
    { from: 'q3', to: 'logs', id: 'no3', via: [[305, 352]] },
    { from: 'a1', to: 'logs', via: [[680, 52], [680, 302], [600, 302]] },
    { from: 'a2', to: 'logs', via: [[680, 152], [680, 302], [600, 302]] },
    { from: 'a3', to: 'logs', id: 'unclear', via: [[680, 252], [680, 302], [600, 302]] },
    { from: 'logs', to: 'agent', id: 'desktop', dashed: true, via: [[550, 432]] },
    { from: 'logs', to: 'report', id: 'stuck' },
  ],
};

export default spec;
