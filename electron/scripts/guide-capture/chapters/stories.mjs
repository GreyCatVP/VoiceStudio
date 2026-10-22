// Chapter "stories": auto-cast a two-character scene, voice the cast, render
// it for real and show the finished file. Needs voice profiles named
// "Narrator" and "Mira". A fresh seed per run keeps the chapter cache from
// serving the whole render instantly.
const SCENES = {
  en: [
    'Narrator: The storm had kept the lighthouse dark for three long nights.\nMira: Grandfather, is the lamp still burning?\nNarrator: The old keeper smiled and handed her the brass key.',
    'Mira: Then tonight, I will climb the stairs myself.\nNarrator: And the light swept across the sea once more.',
  ],
  th: [
    'Narrator: พายุทำให้ประภาคารมืดสนิทมาสามคืนแล้ว\nMira: คุณตาคะ ตะเกียงยังสว่างอยู่ไหมคะ\nNarrator: ผู้เฝ้าประภาคารชรายิ้ม แล้วยื่นกุญแจทองเหลืองให้เธอ',
    'Mira: คืนนี้หนูจะปีนบันไดขึ้นไปเองค่ะ\nNarrator: แล้วแสงไฟก็กวาดผ่านท้องทะเลอีกครั้ง',
  ],
};

export default async function capture({ page, goto, shot, t, language, L }) {
  const scene = SCENES[language] ?? SCENES.en;
  await goto('/stories');
  const editor = page.locator('[data-slot="story-editor"]');
  const cards = editor.locator(':scope > div.rounded-xl');
  const autocast = editor.locator(':scope > details').first();
  const autocastText = autocast.locator('textarea');
  const autocastButton = autocast.getByRole('button', { name: L('stories.autocast'), exact: true });

  await page.getByPlaceholder(L('projects.untitled_story')).fill(
    t({ en: 'The Lighthouse', th: 'ประภาคาร' }),
  );
  // Chapter heading first, so the story renders as two named chapters.
  await page.getByRole('button', { name: L('stories.addFirst') }).click();
  await cards.first().locator('textarea').fill(t({ en: '# The Storm', th: '# พายุ' }));
  if (!(await autocastText.isVisible())) await autocast.locator('summary').click();
  await autocastText.fill(scene[0]);
  await shot('stories-autocast', {
    marks: [autocastText, autocastButton, autocast.getByRole('combobox')],
  });
  await autocastButton.click();
  await page.getByRole('button', { name: L('stories.addChapter') }).click();
  await autocastText.fill(scene[1]);
  await autocastButton.click();
  await cards.nth(6).waitFor();

  // Voices: a default for unassigned lines, then one voice per character.
  const sidebar = page.locator('[data-slot="secondary-sidebar"]');
  const defaultVoice = sidebar.getByRole('button', { name: 'Narrator', exact: true }).first();
  await defaultVoice.click();
  const cast = sidebar.locator('details', {
    has: page.locator('summary', { hasText: L('stories.castTitle') }),
  }).first();
  await cast.locator(':scope > summary').click();
  const characters = cast.locator(':scope > div');
  for (const name of ['Narrator', 'Mira']) {
    const row = characters.filter({ has: page.locator(`input[value="${name}"]`) }).first();
    const picker = row.locator('details');
    await picker.locator('summary').click();
    await picker.getByRole('button', { name, exact: true }).click();
  }
  const panel = page.locator('[data-slot="generate-panel"]').first();
  const generate = panel.getByRole('button', { name: L('dub.generate'), exact: true });
  await page.waitForFunction((el) => el && !el.disabled, await generate.elementHandle(), { timeout: 120000 });
  await characters.first().scrollIntoViewIfNeeded();
  await shot('stories-cast', { marks: [characters.nth(0), characters.nth(1)] });

  // Audition one line before rendering everything.
  const miraLine = cards.nth(2);
  await miraLine.scrollIntoViewIfNeeded();
  await miraLine.getByRole('button', { name: L('stories.preview') }).click();
  const linePlay = miraLine.getByRole('button', { name: L('player.play'), exact: true });
  await linePlay.waitFor({ timeout: 300000 });
  await shot('stories-lines', {
    marks: [
      miraLine.locator('textarea'),
      miraLine.locator(':scope > details').first().locator('summary'),
      miraLine.getByRole('button', { name: L('stories.preview') }),
      linePlay,
    ],
  });

  // A fresh seed per run, so the render is not served whole from the chapter cache.
  const overrides = page.locator('details', {
    has: page.locator(':scope > summary', { hasText: L('audiobook.expressive') }),
  }).first();
  await overrides.locator(':scope > summary').click();
  await overrides.getByLabel(L('audiobook.seed')).fill(String(Date.now() % 1000000));
  await overrides.locator(':scope > summary').click();
  await generate.click();
  const progress = panel.locator('[aria-live="polite"]');
  await progress.waitFor({ timeout: 60000 });
  await shot('stories-progress', {
    settle: 1500,
    marks: [progress, panel.getByRole('button', { name: L('common.stop') })],
  });

  const ready = page.getByRole('heading', { name: L('audiobook.ready') });
  await ready.waitFor({ timeout: 900000 });
  const result = page.locator('section', { has: ready }).last();
  await result.scrollIntoViewIfNeeded();
  await shot('stories-result', {
    marks: [
      result.getByRole('button', { name: L('player.play'), exact: true }),
      result.getByLabel(L('player.seek')),
      result.getByRole('button', { name: L('modelMaintenance.download'), exact: true }),
      result.getByRole('button', { name: L('audiobook.download_cues') }),
    ],
  });
}
