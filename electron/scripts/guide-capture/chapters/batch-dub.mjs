// Chapter "batch-dub": queue two short clips for a Thai dub and watch them run.
// Uses the backend's global ASR, translation and TTS settings.
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { labels } from './dub.mjs';

const SAMPLE = process.env.GUIDE_DUB_SAMPLE; // a short two-speaker video, see run.mjs

/** Two short, distinct clips cut from the sample video. */
function clips(language) {
  if (!existsSync(SAMPLE)) throw new Error(`Sample video not found: ${SAMPLE} (set GUIDE_DUB_SAMPLE)`);
  return [
    ['meeting-part-1', 0, 20],
    ['meeting-part-2', 27, 20],
  ].map(([name, start, length]) => {
    const out = join(tmpdir(), `${name}-${language}.mp4`);
    execFileSync('ffmpeg', [
      '-loglevel', 'error', '-y', '-ss', String(start), '-t', String(length), '-i', SAMPLE,
      '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'aac', out,
    ]);
    return out;
  });
}

export default async function capture({ page, goto, shot, language }) {
  const L = labels(language);
  await goto('/batch');
  const aside = page.getByRole('complementary', { name: L('nav.batch_dub') });
  const tab = (key) => page.getByRole('button', { name: L(key), exact: true });

  // 1. Files and queue-wide settings.
  await aside.getByLabel(L('batch.file_input_label')).setInputFiles(clips(language));
  const picker = aside.getByRole('button', { name: L('clone.language'), exact: true }).first();
  await picker.click();
  await page.keyboard.type('Thai');
  await page.getByRole('option', { name: /Thai|ไทย/ }).first().click();
  await page.waitForTimeout(500);
  // The preselected Spanish chip: clicking it removes the language.
  await aside.getByRole('button', { name: /^(Spanish|สเปน)$/ }).click();
  const voice = aside.locator('details', { has: page.locator('summary', { hasText: L('batch.voice_kicker') }) });
  // Keep the voice list folded so the whole panel fits in one shot.
  if ((await voice.getAttribute('open')) !== null) await voice.locator('summary').click();
  const add = aside.getByRole('button', { name: L('batch.add_to_queue'), exact: true });
  await shot('batch-dub-setup', {
    marks: [
      aside.getByRole('button', { name: `${L('batch.delete')}: meeting-part-1-${language}.mp4` }).locator('xpath=..'),
      picker,
      voice.locator('summary'),
      aside.getByRole('switch', { name: L('batch.preserve_bg') }),
      add,
    ],
  });

  // 2. Queue and watch.
  await add.click();
  const running = page.locator('article [role="status"]').first();
  await running.waitFor({ timeout: 300000 });
  // Prefer the speech stage, which also shows the line count.
  await page.getByText(L('batch.stage_generate')).first().waitFor({ timeout: 300000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await shot('batch-dub-active', {
    marks: [tab('batch.active'), page.locator('article').filter({ has: page.locator('[role="status"]') }).first(), running],
  });

  // 3. Results: wait for the Active tab to empty.
  const end = Date.now() + 1500000;
  while (Date.now() < end && (await page.locator('article').count())) await page.waitForTimeout(10000);
  await tab('batch.completed').click();
  await page.waitForTimeout(2000);
  const first = page.locator('article').filter({ hasText: `meeting-part-1-${language}` }).first();
  await shot('batch-dub-done', {
    marks: [tab('batch.completed'), first, first.getByRole('button', { name: `${L('dub.export')} th` })],
  });
}
