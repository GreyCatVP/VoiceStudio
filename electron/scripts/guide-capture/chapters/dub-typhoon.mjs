// Screenshots for the dub chapter's "Dubbing Thai: Typhoon models" section, kept apart
// from dub.mjs so they can be re-taken without re-running the whole dub:
//   node scripts/guide-capture/run.mjs --chapter dub-typhoon
// Needs the remote GPU (Ray) set up and a finished dub job of the English dialogue
// (dub.mjs makes one). Turns on the typhoon-translate Ray engine (kept: it only adds
// an engine), selects Typhoon Translate for one real translation and puts the
// previous translation provider back. Never downloads or selects Typhoon Whisper.
const API = (process.env.GUIDE_API_URL || 'http://127.0.0.1:3920').replace(/\/$/, '');
const GLOSSARY = { source: 'board', target: 'คณะกรรมการบริษัท', note: '' };

async function json(page, path, options = {}) {
  const response = await page.request.fetch(`${API}${path}`, { timeout: 60000, ...options });
  if (!response.ok()) throw new Error(`${path}: HTTP ${response.status()}`);
  return response.json();
}

/** The newest dub job of the English dialogue: its English lines, untranslated. */
async function englishDraft(page) {
  const history = await json(page, '/dub/history');
  for (const job of Array.isArray(history) ? history : history.jobs ?? history.history ?? []) {
    const data = typeof job.job_data === 'string' ? JSON.parse(job.job_data) : job.job_data;
    const segments = (data?.segments ?? []).filter((segment) => segment.text_original);
    if (!segments.length || !/quarterly report/.test(segments[0].text_original)) continue;
    return {
      jobId: job.id,
      filename: data.filename,
      duration: data.duration,
      sourceLang: 'English',
      sourceLanguage: 'en',
      target: 'Thai',
      quality: 'fast',
      segments: segments.map(({ id, start, end, speaker_id, words, text_original }) =>
        ({ id, start, end, speaker_id, words, text: text_original, text_original })),
    };
  }
  throw new Error('No dub job of the English dialogue found: run --chapter dub first');
}

export default async function capture({ page, goto, shot, L }) {
  const row = (id) => page.locator(`[data-slot="settings-row"]:has(h3#${id})`);

  // 1. Settings → Remote GPU: the ASR and translation engines that run there.
  await page.setViewportSize({ width: 1280, height: 900 });
  await goto('/settings/ray');
  const group = (kind) => page.locator(`[role="group"][aria-labelledby="ray-engines-${kind}"]`);
  const engine = (kind, id) => group(kind).locator('label').filter({ hasText: id });
  const typhoonEngine = engine('translation', 'typhoon-translate');
  await typhoonEngine.waitFor({ timeout: 60000 });
  if (!(await typhoonEngine.locator('input').isChecked())) {
    await typhoonEngine.locator('input').check();
    await row('ray-save').getByRole('button', { name: L('common.save'), exact: true }).click();
    for (let tries = 0; !(await json(page, '/api/settings/ray')).engines.includes('typhoon-translate'); tries += 1) {
      if (tries > 30) throw new Error('typhoon-translate was not saved');
      await page.waitForTimeout(1000);
    }
  }
  await page.locator('#ray-engines-asr').evaluate((node) => node.scrollIntoView({ block: 'start' }));
  await page.mouse.wheel(0, -40);
  const whisperEngine = engine('asr', 'faster-whisper-isolated');
  await shot('dub-typhoon-engines', { marks: [whisperEngine, typhoonEngine] });

  // 2. Settings → Models → Translation: select Typhoon Translate (put back at the end).
  const previous = (await json(page, '/engines/translation')).active;
  try {
    await page.setViewportSize({ width: 1280, height: 800 });
    await goto('/settings/models/translation');
    const provider = row('translation-typhoon');
    await provider.waitFor({ timeout: 30000 });
    const select = provider.getByRole('button', { name: new RegExp(`^(${L('modelSettings.select')}|${L('modelSettings.selected')})$`) });
    if ((await select.getAttribute('aria-pressed')) !== 'true') await select.click();
    await provider.locator('button[aria-pressed="true"]').waitFor({ timeout: 30000 });
    await provider.scrollIntoViewIfNeeded();
    await shot('dub-typhoon-provider', { marks: [provider, select] });

    // 3. Model Catalogue → Speech recognition: the Typhoon Whisper Turbo row (not downloaded here).
    await goto('/settings/models/asr');
    const whisper = row('model-typhoon-ai-typhoon-whisper-turbo');
    await whisper.waitFor({ timeout: 60000 });
    await whisper.evaluate((node) => node.scrollIntoView({ block: 'center' }));
    await page.waitForTimeout(1500); // licence state loads after the row
    // Downloaded or not, the row's action is Download or Select (never pressed here).
    const action = whisper.getByRole('button', {
      name: new RegExp(`^(${L('modelMaintenance.download')}|${L('modelSettings.select')}|${L('modelSettings.selected')})$`),
    });
    const licenceNeeded = whisper.getByText(L('modelLicense.acceptNeeded'), { exact: true });
    await shot('dub-typhoon-asr', {
      marks: [
        // Anchored: the row title "(Thai only)" must not match; the chip's language name varies.
        whisper.getByText(new RegExp(`^${L.pattern('modelSettings.languageOnly').source}$`)),
        whisper.getByRole('button', { name: new RegExp(`^${L('modelLicense.label')}:`) }),
        ...((await licenceNeeded.isVisible()) ? [licenceNeeded] : []),
        action,
      ],
    });

    // 4. A real Typhoon translation of the dialogue, with one glossary rule.
    const draft = await englishDraft(page);
    const terms = await json(page, `/glossary/${draft.jobId}`);
    if (!terms.some((term) => term.source === GLOSSARY.source)) {
      await json(page, `/glossary/${draft.jobId}`, { method: 'POST', data: GLOSSARY });
    }
    await page.context().addInitScript((value) => localStorage.setItem('voicestudio.dub.session.v1', JSON.stringify(value)), draft);
    await goto('/dub');
    await page.reload({ waitUntil: 'networkidle' }); // a hash change keeps the page: reload to restore the draft
    const aside = page.getByRole('complementary', { name: L('nav.dub') });
    const transcript = page.locator('[data-slot="dub-transcript"]');
    const translateAll = page.getByRole('button', { name: L('dub.translate_all'), exact: true });
    const boardLine = transcript.locator('article').filter({ hasText: /board meeting/ }).first();
    await boardLine.waitFor({ timeout: 30000 });
    await translateAll.click();
    const accept = page.getByRole('dialog').getByRole('button', { name: L('modelLicense.accept') });
    const end = Date.now() + 1800000; // the first run installs the engine and downloads ~8 GB on the cluster
    let accepted = false;
    while (Date.now() < end) {
      if (!accepted && (await accept.isVisible().catch(() => false))) {
        await page.getByRole('dialog').getByRole('checkbox').first().check();
        await accept.click();
        accepted = true;
        await page.waitForTimeout(1500);
        await page.keyboard.press('Escape'); // the dialog stays open on "Licences accepted"
        await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 10000 });
        await translateAll.click();
      }
      if (/[฀-๿]/.test(await boardLine.innerText()) && (await translateAll.isEnabled({ timeout: 1000 }).catch(() => false))) break;
      await page.waitForTimeout(2000);
    }
    if (!/[฀-๿]/.test(await boardLine.innerText())) throw new Error('Timed out waiting for the Typhoon translation');
    await page.waitForTimeout(1500);
    const glossaryButton = page.getByRole('button', { name: L.pattern('dub.glossary_btn') }).first();
    // The count on + Glossary updates only once its panel has opened: open it and close it again.
    await glossaryButton.click();
    await page.getByRole('textbox', { name: L('glossary.source') }).first().waitFor({ timeout: 15000 });
    await glossaryButton.click();
    await page.getByRole('button', { name: L('dub.glossary_btn', { count: 1 }) }).first().waitFor({ timeout: 10000 });
    await boardLine.scrollIntoViewIfNeeded();
    const translator = aside.getByRole('group', { name: L('about.translator') });
    await translator.scrollIntoViewIfNeeded();
    await shot('dub-typhoon-translate', {
      marks: [translator.locator('button[aria-pressed="true"]'), glossaryButton, boardLine, translateAll],
    });
  } finally {
    if (previous && previous !== 'typhoon') {
      await json(page, '/engines/translation/select', { method: 'POST', data: { engine_id: previous } })
        .catch((error) => console.warn(`  ! could not restore translation provider ${previous}: ${error.message}`));
    }
  }
}
