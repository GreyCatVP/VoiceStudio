import type { DiagramSpec } from '../specs';

/** Running a workflow: validate the whole graph, then walk it once per input. */
const spec: DiagramSpec = {
  width: 920,
  height: 320,
  nodes: [
    { id: 'design', x: 5, y: 60, w: 140, h: 64, tone: 'ui' },
    { id: 'drafts', x: 5, y: 210, w: 140, h: 72, tone: 'data', shape: 'store' },
    { id: 'run', x: 175, y: 60, w: 140, h: 64, tone: 'ui' },
    { id: 'check', x: 345, y: 60, w: 140, h: 64, tone: 'ui' },
    { id: 'invalid', x: 345, y: 214, w: 140, h: 64, tone: 'neutral' },
    { id: 'loop', x: 515, y: 60, w: 160, h: 64, tone: 'ui' },
    { id: 'step', x: 705, y: 60, w: 210, h: 64, tone: 'backend' },
    { id: 'checkpoint', x: 705, y: 210, w: 210, h: 72, tone: 'data', shape: 'store' },
    { id: 'output', x: 515, y: 214, w: 160, h: 64, tone: 'ui' },
  ],
  edges: [
    { from: 'design', to: 'drafts', id: 'autosave', dashed: true },
    { from: 'design', to: 'run' },
    { from: 'run', to: 'check' },
    { from: 'check', to: 'invalid', id: 'fail', dashed: true },
    { from: 'check', to: 'loop' },
    { from: 'loop', to: 'step' },
    { from: 'step', to: 'loop', id: 'next', via: [[810, 28], [595, 28]] },
    { from: 'step', to: 'checkpoint', id: 'saved' },
    { from: 'checkpoint', to: 'output' },
  ],
};

export default spec;
