// The user guide is structured data, one file per chapter per language
// (content/en/<chapter>.ts, content/th/<chapter>.ts). Both languages share the
// same chapter, section, screenshot and diagram ids; guide-content.test.ts
// fails when they drift. Inline text supports **bold** and `code`.

export type GuideLanguage = 'en' | 'th';

export interface GuideStep {
  title: string;
  text?: string;
  /** Screenshot id: assets/<lang>/<id>.webp, captured by scripts/guide-capture. */
  shot?: string;
  /** What the user should see once the step is done. */
  check?: string;
}

export type GuideBlock =
  | { kind: 'p'; text: string }
  | { kind: 'list'; items: string[]; ordered?: boolean }
  | { kind: 'note'; tone: 'info' | 'warn' | 'tip'; text: string }
  | { kind: 'code'; text: string }
  | { kind: 'table'; head: string[]; rows: string[][] }
  | {
      kind: 'diagram';
      /** A spec id from diagrams/specs.ts. */
      id: string;
      caption: string;
      /** Text for every node, group and labelled edge id of the spec. */
      text: Record<string, string>;
    }
  | { kind: 'shot'; id: string; caption: string }
  | { kind: 'steps'; items: GuideStep[] }
  | { kind: 'verify'; items: string[]; shot?: string };

export interface GuideSection {
  id: string;
  title: string;
  blocks: GuideBlock[];
}

export interface GuideChapter {
  id: string;
  /** Position in the table of contents (gaps are fine). */
  order: number;
  title: string;
  summary: string;
  sections: GuideSection[];
}
