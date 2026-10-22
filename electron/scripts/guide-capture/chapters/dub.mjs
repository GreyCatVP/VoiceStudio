// Chapter "dub": a real dub of a two-speaker clip into Thai with NLLB.
// Needs the backend's ASR, diarisation, Demucs, NLLB and TTS working (local or
// on the remote GPU) and the NLLB licence accepted. Takes ~10 minutes per language.
// UI labels come from the locale catalogs, so a reworded label does not break it.
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SAMPLE =
  process.env.GUIDE_DUB_SAMPLE ||
  '/tmp/claude-0/-root-voicestudio/a001375f-0ebe-488d-b999-ba1df3548c39/scratchpad/e2e/dialogue.mp4';
const LOCALES = join(dirname(fileURLToPath(import.meta.url)), '../../../src/renderer/src/i18n/locales');

/** L('dub.translate_all') in the capture language; L.pattern() matches it with any {{values}}. */
export function labels(language) {
  const catalog = JSON.parse(readFileSync(join(LOCALES, `${language}.json`), 'utf8'));
  const raw = (key) => {
    const text = key.split('.').reduce((node, part) => node?.[part], catalog);
    if (typeof text !== 'string') throw new Error(`Missing ${language} label ${key}`);
    return text;
  };
  const L = (key, values = {}) => raw(key).replace(/\{\{(\w+)\}\}/g, (_, name) => String(values[name] ?? ''));
  L.pattern = (key) =>
    new RegExp(raw(key).split(/\{\{\w+\}\}/).map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('.+?'));
  return L;
}

/** A copy with its own content hash, so the backend really runs Demucs instead of reusing a cache. */
function freshCopy(language) {
  if (!existsSync(SAMPLE)) throw new Error(`Sample video not found: ${SAMPLE} (set GUIDE_DUB_SAMPLE)`);
  const out = join(tmpdir(), `guide-dub-${language}.mp4`);
  execFileSync('ffmpeg', [
    '-loglevel', 'error', '-y', '-i', SAMPLE, '-c', 'copy',
    '-metadata', `comment=guide-${language}-${Date.now()}`, out,
  ]);
  return out;
}

async function waitUntil(page, check, timeout, what) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await check().catch(() => false)) return;
    await page.waitForTimeout(1000);
  }
  throw new Error(`Timed out waiting for ${what}`);
}

export default async function capture({ page, goto, shot, language }) {
  const L = labels(language);
  const aside = page.getByRole('complementary', { name: L('nav.dub') });
  const transcript = page.locator('[data-slot="dub-transcript"]');
  const button = (key, values) => page.getByRole('button', { name: L(key, values), exact: true });
  const openGroup = async (key) => {
    const summary = aside.locator('summary', { hasText: L(key) }).first();
    const details = summary.locator('xpath=..');
    if ((await details.getAttribute('open')) === null) await summary.click();
    await summary.scrollIntoViewIfNeeded();
    return details;
  };

  // 1. Import.
  await goto('/dub');
  await shot('dub-import', {
    marks: [
      button('settings.audio_tools_choose_file'),
      page.getByPlaceholder(L('dub.paste_url')),
      aside.locator('summary', { hasText: L('dub.source_language') }).first(),
    ],
  });

  // 2. Preparation: Demucs on a fresh copy.
  await aside.locator('input[type=file]').first().setInputFiles(freshCopy(language));
  const bar = (key) => page.getByRole('status').filter({ hasText: L(key) }).last();
  const demucs = bar('dub.prep_demucs');
  const transcribing = bar('dub_workflow.transcribing_audio');
  await waitUntil(page, async () => (await demucs.isVisible()) || (await transcribing.isVisible()), 300000, 'preparation');
  const stage = (await demucs.isVisible()) ? demucs : transcribing;
  await shot('dub-prepare', { marks: [stage, button('common.cancel')], settle: 0 });

  // 3. Transcript, speakers and timeline.
  await waitUntil(page, () => transcript.locator('article').first().isVisible(), 900000, 'the transcript');
  await page.waitForTimeout(1500);
  const firstLine = transcript.locator('article').first();
  await shot('dub-segments', {
    marks: [
      transcript.getByRole('region').first(),
      firstLine.getByRole('button').first(),
      firstLine.getByRole('button').last(),
    ],
  });

  // 4. Translate into Thai.
  const target = aside.getByRole('button', { name: L('clone.language'), exact: true }).first();
  await target.click();
  await page.keyboard.type('Thai');
  await page.getByRole('option', { name: /Thai|ไทย/ }).first().click();
  await page.waitForTimeout(800);
  await button('dub.translate_all').click();
  await waitUntil(page, async () => /[฀-๿]/.test(await firstLine.innerText()) &&
    (await button('dub.translate_all').isEnabled()), 600000, 'the translation');
  await page.waitForTimeout(1500);
  const translator = aside.getByRole('group', { name: L('about.translator') });
  await translator.scrollIntoViewIfNeeded();
  await shot('dub-translate', {
    marks: [target, translator, button('dub.translate_all'), firstLine.getByRole('button').last()],
  });

  // 5. Voices per speaker.
  const cast = await openGroup('dub.cast');
  const speakers = cast.getByRole('combobox');
  await speakers.last().scrollIntoViewIfNeeded();
  await shot('dub-cast', { marks: [speakers.first(), speakers.nth(1)] });

  // 6. Generate.
  const timing = await openGroup('dub.timing_label');
  await timing.scrollIntoViewIfNeeded();
  await button('dub.generate_dub').last().click();
  const progress = page.getByRole('status').filter({ hasText: /%/ }).first();
  await progress.waitFor({ timeout: 120000 });
  await page.waitForTimeout(4000);
  await shot('dub-generate', {
    marks: [timing.locator('[aria-pressed="true"]').first(), progress, button('common.cancel')],
    settle: 0,
  });
  // The dub is done when the progress bar is gone and Generate Dub is back.
  await waitUntil(page, async () => !(await progress.isVisible()) &&
    (await button('dub.generate_dub').last().isEnabled()), 900000, 'the dub');
  await page.waitForTimeout(2000);

  // 7. Second-pass check.
  const verify = button('dub.verify').first();
  await verify.click();
  const verdict = page.getByText(L.pattern('dub.qc_result')).or(page.getByText(L.pattern('dub.qc_clean'))).first();
  await verdict.waitFor({ timeout: 600000 });
  await shot('dub-qc', {
    marks: [verify, transcript.locator('article').getByText(L('dub.verify'), { exact: true }).first(), verdict],
    settle: 200,
  });

  // 8. Export options.
  const exportGroup = await openGroup('exportModal.export_options');
  const exportButton = exportGroup.getByRole('button', { name: L('exportModal.export'), exact: true });
  await exportButton.scrollIntoViewIfNeeded();
  await shot('dub-export', {
    marks: [
      exportGroup.getByRole('group', { name: L('exportModal.format') }).getByRole('button').first(),
      exportGroup.getByRole('switch').nth(1),
      exportGroup.getByRole('switch', { name: L('exportModal.bg_audio') }),
      exportButton,
    ],
  });

  // 9. The result: play the dubbed track.
  const dubbed = aside.getByRole('button', { name: L('dub.dubbed_audio', { code: 'th' }), exact: true });
  await dubbed.scrollIntoViewIfNeeded();
  await dubbed.click();
  await page.waitForTimeout(2500);
  await shot('dub-result', { marks: [aside.getByRole('region').first(), dubbed] });
}
