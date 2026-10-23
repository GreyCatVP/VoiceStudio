import { afterEach, describe, expect, it, vi } from 'vitest';
import { countWords, formatRuntimeClock, scriptStats } from '@shared/utils/audiobookScript';
import { splitIntoChunks } from '@shared/utils/splitStoryText';

// Thai writes no spaces between words; spaces only separate phrases/sentences.
const THAI_BOOK = [
  '# บทที่ 1 จุดเริ่มต้น',
  'กาลครั้งหนึ่งนานมาแล้ว มีเด็กหญิงคนหนึ่งชื่อมะลิอาศัยอยู่ในหมู่บ้านเล็กๆริมแม่น้ำ',
  '# บทที่ 2 การเดินทาง',
  'วันหนึ่งคุณครูประกาศว่าจะพานักเรียนไปทัศนศึกษาที่กรุงเทพมหานคร',
  '# บทที่ 3 บ้าน',
  'เมื่อกลับถึงบ้าน มะลิเล่าเรื่องทั้งหมดให้แม่ฟังด้วยรอยยิ้ม',
].join('\n');

afterEach(() => vi.unstubAllGlobals());

describe('Thai word count', () => {
  it('counts dictionary words, not space-separated phrases', () => {
    const stats = scriptStats(THAI_BOOK);
    expect(stats.chapters).toBe(3);
    // A whitespace split sees 5 "words" here; the real count is several times that.
    expect(stats.words).toBeGreaterThan(30);
    expect(formatRuntimeClock(stats.runtimeSec)).not.toBe('0:02');
  });
  it('keeps English counts, ignores punctuation and markup', () => {
    expect(countWords("Hello, world — it's fine.")).toBe(4);
    expect(scriptStats('[voice:Mara] Hello world. [pause 1s]').words).toBe(2);
  });
  it('falls back to whitespace words without Intl.Segmenter', () => {
    vi.stubGlobal('Intl', { ...Intl, Segmenter: undefined });
    expect(countWords('one two  three')).toBe(3);
  });
});

describe('Thai chunk splitting', () => {
  it('cuts a long space-free Thai run on a word boundary, never mid-word', () => {
    const run = 'มะลิเล่าเรื่องทั้งหมดให้แม่ฟังด้วยรอยยิ้ม'.repeat(8);
    const chunks = splitIntoChunks(run, 50);
    expect(chunks.join('')).toBe(run);
    const words = [...new Intl.Segmenter('th', { granularity: 'word' }).segment(run)];
    const starts = new Set(words.map((w) => w.index));
    let at = 0;
    for (const chunk of chunks.slice(0, -1)) {
      at += chunk.length;
      expect(chunk.length).toBeLessThanOrEqual(50);
      expect(starts.has(at)).toBe(true);
    }
  });
});
