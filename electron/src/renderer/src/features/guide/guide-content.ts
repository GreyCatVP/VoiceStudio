import type { GuideChapter, GuideLanguage } from './guide-types';

// Chapters are discovered by file, so each chapter is self-contained:
// content/<lang>/<chapter-id>.ts default-exports a GuideChapter.
const en = import.meta.glob<{ default: GuideChapter }>('./content/en/*.ts', { eager: true });
const th = import.meta.glob<{ default: GuideChapter }>('./content/th/*.ts', { eager: true });

const ordered = (modules: Record<string, { default: GuideChapter }>) =>
  Object.values(modules)
    .map((module) => module.default)
    .sort((a, b) => a.order - b.order);

export const GUIDE: Record<GuideLanguage, GuideChapter[]> = { en: ordered(en), th: ordered(th) };

const shots = import.meta.glob<string>('./assets/*/*.webp', {
  eager: true,
  query: '?url',
  import: 'default',
});

/** The screenshot's URL in this language, falling back to English. */
export function shotUrl(language: GuideLanguage, id: string): string | undefined {
  return shots[`./assets/${language}/${id}.webp`] ?? shots[`./assets/en/${id}.webp`];
}

export function guideLanguage(language: string | undefined): GuideLanguage {
  return language?.toLowerCase().startsWith('th') ? 'th' : 'en';
}

export const SHOT_IDS: Record<GuideLanguage, Set<string>> = {
  en: new Set(
    Object.keys(shots).flatMap((path) => (path.startsWith('./assets/en/') ? [path.slice(12, -5)] : [])),
  ),
  th: new Set(
    Object.keys(shots).flatMap((path) => (path.startsWith('./assets/th/') ? [path.slice(12, -5)] : [])),
  ),
};
