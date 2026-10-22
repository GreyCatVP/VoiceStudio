import type { DiagramSpec } from '../specs';

/** An outside program calling VoiceStudio's OpenAI-compatible API or MCP endpoint. */
const spec: DiagramSpec = {
  width: 920,
  height: 360,
  groups: [
    { id: 'outside', x: 10, y: 20, w: 180, h: 240, tone: 'neutral' },
    { id: 'computer', x: 235, y: 20, w: 675, h: 330, tone: 'neutral' },
  ],
  nodes: [
    { id: 'client', x: 25, y: 50, w: 150, h: 70, tone: 'ui' },
    { id: 'agent', x: 25, y: 170, w: 150, h: 70, tone: 'ui' },
    { id: 'openai', x: 255, y: 50, w: 165, h: 70, tone: 'backend' },
    { id: 'mcp', x: 255, y: 170, w: 165, h: 70, tone: 'backend' },
    { id: 'resolve', x: 450, y: 110, w: 160, h: 70, tone: 'backend' },
    { id: 'engine', x: 640, y: 50, w: 140, h: 70, tone: 'engine' },
    { id: 'remote', x: 800, y: 50, w: 100, h: 70, tone: 'remote' },
    { id: 'profiles', x: 450, y: 226, w: 160, h: 62, tone: 'data', shape: 'store' },
    { id: 'mark', x: 640, y: 280, w: 140, h: 60, tone: 'backend' },
  ],
  edges: [
    { from: 'client', to: 'openai' },
    { from: 'agent', to: 'mcp' },
    { from: 'openai', to: 'resolve' },
    { from: 'mcp', to: 'resolve' },
    { from: 'profiles', to: 'resolve', id: 'voice', dashed: true },
    { from: 'resolve', to: 'engine' },
    { from: 'engine', to: 'remote', dashed: true, both: true },
    { from: 'engine', to: 'mark' },
    { from: 'mark', to: 'client', id: 'audio', via: [[215, 310], [215, 85]] },
  ],
};

export default spec;
