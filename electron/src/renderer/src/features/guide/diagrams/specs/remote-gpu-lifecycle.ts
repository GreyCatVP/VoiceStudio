import type { DiagramSpec } from '../specs';

/** One remote job, from the job package to the freed GPU (Ray and Modal alike). */
const spec: DiagramSpec = {
  width: 920,
  height: 320,
  nodes: [
    { id: 'package', x: 5, y: 40, w: 130, h: 84, tone: 'backend' },
    { id: 'upload', x: 161, y: 40, w: 130, h: 84, tone: 'backend' },
    { id: 'install', x: 317, y: 40, w: 130, h: 84, tone: 'remote' },
    { id: 'run', x: 473, y: 40, w: 130, h: 84, tone: 'remote' },
    { id: 'result', x: 629, y: 40, w: 130, h: 84, tone: 'backend' },
    { id: 'free', x: 785, y: 40, w: 130, h: 84, tone: 'remote' },
    { id: 'cache', x: 317, y: 170, w: 130, h: 76, tone: 'data', shape: 'store' },
    { id: 'progress', x: 629, y: 176, w: 130, h: 64, tone: 'ui' },
    { id: 'cancel', x: 5, y: 250, w: 200, h: 56, tone: 'neutral' },
  ],
  edges: [
    { from: 'package', to: 'upload' },
    { from: 'upload', to: 'install' },
    { from: 'install', to: 'run' },
    { from: 'run', to: 'result' },
    { from: 'result', to: 'free' },
    { from: 'install', to: 'cache', id: 'reuse', both: true },
    { from: 'run', to: 'progress', id: 'frames', via: [[538, 208]] },
    { from: 'cancel', to: 'run', id: 'stop', dashed: true, via: [[560, 278]] },
  ],
};

export default spec;
