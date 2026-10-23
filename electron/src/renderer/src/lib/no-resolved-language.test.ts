import { expect, it } from 'vitest';

// i18next's `resolvedLanguage` stays "en" until a lazily loaded locale arrives,
// so UI that reads it shows English (or half-English) in the user's language.
// Read `i18n.language` instead.
const sources = import.meta.glob('../**/*.{ts,tsx}', { eager: true, query: '?raw', import: 'default' });

it('never reads i18n.resolvedLanguage', () => {
  const offenders = Object.entries(sources)
    .filter(([path]) => !path.endsWith('.test.ts') && !path.endsWith('.test.tsx'))
    .filter(([, text]) => /\.resolvedLanguage\b/.test(String(text)))
    .map(([path]) => path);
  expect(offenders).toEqual([]);
});
