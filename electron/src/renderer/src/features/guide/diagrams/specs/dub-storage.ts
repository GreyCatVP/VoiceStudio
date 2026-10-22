import type { DiagramSpec } from '../specs';

/** What a dub writes, and where: the job folder and the database. */
const spec: DiagramSpec = {
  width: 920,
  height: 470,
  groups: [{ id: 'folder', x: 200, y: 20, w: 510, h: 430, tone: 'data' }],
  nodes: [
    { id: 'source', x: 10, y: 60, w: 150, h: 64, tone: 'ui' },
    { id: 'original', x: 220, y: 60, w: 190, h: 64, tone: 'data', shape: 'store' },
    { id: 'audio', x: 480, y: 60, w: 210, h: 64, tone: 'data', shape: 'store' },
    { id: 'vocals', x: 220, y: 165, w: 190, h: 64, tone: 'data', shape: 'store' },
    { id: 'bed', x: 480, y: 165, w: 210, h: 64, tone: 'data', shape: 'store' },
    { id: 'refs', x: 220, y: 270, w: 190, h: 64, tone: 'data', shape: 'store' },
    { id: 'lines', x: 480, y: 270, w: 210, h: 64, tone: 'data', shape: 'store' },
    { id: 'track', x: 480, y: 370, w: 210, h: 64, tone: 'data', shape: 'store' },
    { id: 'db', x: 10, y: 270, w: 150, h: 72, tone: 'data', shape: 'store' },
    { id: 'exports', x: 750, y: 370, w: 160, h: 64, tone: 'ui' },
  ],
  edges: [
    { from: 'source', to: 'original', id: 'upload' },
    { from: 'original', to: 'audio', id: 'extract' },
    { from: 'audio', to: 'vocals', id: 'demucs', via: [[585, 145], [315, 145]] },
    { from: 'audio', to: 'bed' },
    { from: 'vocals', to: 'refs', id: 'cut' },
    { from: 'refs', to: 'lines', id: 'clone' },
    { from: 'lines', to: 'track', id: 'assemble' },
    { from: 'track', to: 'exports' },
    { from: 'bed', to: 'exports', id: 'music', via: [[830, 197]] },
    { from: 'original', to: 'exports', id: 'picture', via: [[315, 8], [870, 8]], dashed: true },
    { from: 'vocals', to: 'db', id: 'segments', via: [[85, 197]] },
  ],
};

export default spec;
