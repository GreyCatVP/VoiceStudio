import { describe, expect, it } from 'vitest';
import { DIAGRAMS, diagramTextIds } from './diagrams/specs';
import { GUIDE, SHOT_IDS } from './guide-content';
import type { GuideBlock, GuideChapter } from './guide-types';

/** Everything that must line up between languages, in order. */
function skeleton(chapter: GuideChapter) {
  return {
    id: chapter.id,
    order: chapter.order,
    sections: chapter.sections.map((section) => ({
      id: section.id,
      blocks: section.blocks.map((block) => shape(block)),
    })),
  };
}

function shape(block: GuideBlock): unknown {
  switch (block.kind) {
    case 'diagram':
      return { kind: block.kind, id: block.id, text: Object.keys(block.text).sort() };
    case 'shot':
      return { kind: block.kind, id: block.id };
    case 'steps':
      return { kind: block.kind, items: block.items.map((step) => ({ shot: step.shot, check: !!step.check })) };
    case 'verify':
      return { kind: block.kind, shot: block.shot, items: block.items.length };
    case 'list':
      return { kind: block.kind, items: block.items.length };
    case 'table':
      return { kind: block.kind, rows: block.rows.length, cols: block.head.length };
    default:
      return { kind: block.kind };
  }
}

const shotsOf = (chapter: GuideChapter) =>
  chapter.sections.flatMap((section) =>
    section.blocks.flatMap((block) =>
      block.kind === 'shot'
        ? [block.id]
        : block.kind === 'steps'
          ? block.items.flatMap((step) => (step.shot ? [step.shot] : []))
          : block.kind === 'verify' && block.shot
            ? [block.shot]
            : [],
    ),
  );

describe('user guide content', () => {
  it('has the same chapters, sections and blocks in English and Thai', () => {
    expect(GUIDE.en.length).toBeGreaterThan(0);
    expect(GUIDE.th.map(skeleton)).toEqual(GUIDE.en.map(skeleton));
  });

  it('uses unique chapter, section and screenshot ids', () => {
    const chapters = GUIDE.en.map((chapter) => chapter.id);
    expect(new Set(chapters).size).toBe(chapters.length);
    for (const chapter of GUIDE.en) {
      const sections = chapter.sections.map((section) => section.id);
      expect(new Set(sections).size, chapter.id).toBe(sections.length);
    }
    const shots = GUIDE.en.flatMap(shotsOf);
    expect(new Set(shots).size).toBe(shots.length);
  });

  it.each(['en', 'th'] as const)('gives every diagram all of its text (%s)', (language) => {
    for (const chapter of GUIDE[language]) {
      for (const section of chapter.sections) {
        for (const block of section.blocks) {
          if (block.kind !== 'diagram') continue;
          const spec = DIAGRAMS[block.id];
          expect(spec, `${chapter.id}: unknown diagram ${block.id}`).toBeDefined();
          const missing = diagramTextIds(spec).filter((id) => !block.text[id]?.trim());
          expect(missing, `${language}/${chapter.id}/${block.id}`).toEqual([]);
          const extra = Object.keys(block.text).filter((id) => !diagramTextIds(spec).includes(id));
          expect(extra, `${language}/${chapter.id}/${block.id}`).toEqual([]);
        }
      }
    }
  });

  it.each(['en', 'th'] as const)('has every referenced screenshot captured (%s)', (language) => {
    const missing = GUIDE[language].flatMap(shotsOf).filter((id) => !SHOT_IDS[language].has(id));
    expect(missing).toEqual([]);
  });

  it('draws diagrams whose edges connect existing nodes', () => {
    for (const [id, spec] of Object.entries(DIAGRAMS)) {
      // One text key per id: a group, node and edge sharing an id would share a label.
      const ids = diagramTextIds(spec);
      expect(ids.length, `${id}: duplicate text ids`).toBe(new Set(ids).size);
      const nodes = new Set(spec.nodes.map((node) => node.id));
      for (const edge of spec.edges) {
        expect(nodes.has(edge.from) && nodes.has(edge.to), `${id}: ${edge.from} → ${edge.to}`).toBe(true);
      }
    }
  });
});
