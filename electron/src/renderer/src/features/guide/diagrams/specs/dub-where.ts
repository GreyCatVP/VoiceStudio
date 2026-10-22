import type { DiagramSpec } from '../specs';

/** Which dub steps run on this computer and which can run on the remote GPU. */
const spec: DiagramSpec = {
  width: 920,
  height: 390,
  groups: [
    { id: 'computer', x: 20, y: 20, w: 470, h: 350, tone: 'neutral' },
    { id: 'remote', x: 560, y: 20, w: 340, h: 350, tone: 'remote' },
  ],
  nodes: [
    { id: 'ffmpeg', x: 40, y: 55, w: 220, h: 56, tone: 'backend' },
    { id: 'refs', x: 40, y: 125, w: 220, h: 56, tone: 'backend' },
    { id: 'fit', x: 40, y: 195, w: 220, h: 56, tone: 'backend' },
    { id: 'mux', x: 40, y: 265, w: 220, h: 56, tone: 'backend' },
    { id: 'edit', x: 290, y: 125, w: 180, h: 56, tone: 'ui' },
    { id: 'demucs', x: 590, y: 50, w: 280, h: 50, tone: 'remote' },
    { id: 'asr', x: 590, y: 115, w: 280, h: 50, tone: 'remote' },
    { id: 'diar', x: 590, y: 180, w: 280, h: 50, tone: 'remote' },
    { id: 'mt', x: 590, y: 245, w: 280, h: 50, tone: 'remote' },
    { id: 'tts', x: 590, y: 310, w: 280, h: 50, tone: 'remote' },
  ],
  edges: [
    { from: 'ffmpeg', to: 'demucs', id: 'send', dashed: true, both: true },
    { from: 'fit', to: 'tts', id: 'back', dashed: true, both: true },
  ],
};

export default spec;
