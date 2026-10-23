// Chapter "tools": every tool of the Tools workspace, run for real.
const CLIP = process.env.GUIDE_SPEECH_CLIP; // a short speech WAV, see run.mjs

export default async function capture({ page, goto, shot, t, L }) {
  const nav = (key) => page.getByRole('button', { name: L(key), exact: true });
  const main = page.locator('main[data-slot="workspace-content"] section.overflow-y-auto').first();

  // 1. Directorial AI
  await goto('/tools');
  await nav('tools.directorial_ai').click();
  const direction = main.locator('textarea');
  await direction.fill('urgent and surprised, a little louder');
  const parse = main.getByRole('button', { name: L('tools.parse') });
  await parse.click();
  const result = page.getByRole('region', { name: L('tools.result') });
  await result.waitFor({ timeout: 60000 });
  await shot('tools-direction', { marks: [nav('tools.directorial_ai'), direction, parse, result] });

  // 2. Speech-rate fit (no language model configured: measure only)
  await nav('tools.speech_rate_fit').click();
  await main.locator('textarea').fill(
    'Welcome back to the channel. Today we are going to talk about something really important for all of us.',
  );
  const slot = main.locator('input[type="number"]');
  await slot.fill('3');
  const fit = main.getByRole('button', { name: L('tools.fit'), exact: true });
  await fit.click();
  await result.waitFor({ timeout: 120000 });
  const language = main.getByText(L('tools.target_language'), { exact: true }).locator('xpath=..');
  await shot('tools-rate-fit', { marks: [main.locator('textarea'), slot, language, fit, result] });

  // 3. Probe file
  await nav('tools.probe_file').click();
  const path = main.locator('input').first();
  await path.fill(CLIP);
  const probe = main.getByRole('button', { name: L('tools.probe'), exact: true });
  await probe.click();
  await result.waitFor({ timeout: 60000 });
  await shot('tools-probe', { marks: [path, probe, result] });

  // 4. A/B voice comparison (two real generations)
  await nav('compare.title').click();
  await main.locator('textarea').fill('Thanks for calling. Your order is on its way and should arrive tomorrow.');
  const columns = main.locator('section');
  const pick = async (side, name) => {
    const list = columns.nth(side).getByRole('button');
    const byName = list.filter({ hasText: name });
    await ((await byName.count()) ? byName.first() : list.nth(side)).click();
  };
  await pick(0, 'Narrator');
  await pick(1, 'VoiceStudio Demo Voice');
  const compare = main.getByRole('button', { name: L('compare.compare_btn'), exact: true });
  await compare.click();
  await page.waitForTimeout(1000);
  await compare.waitFor({ timeout: 600000 }); // label returns to "Compare" when both takes are done
  await main.locator('section').nth(1).locator('[data-slot="waveform-player"], audio, canvas').first()
    .waitFor({ timeout: 600000 }).catch(() => {});
  await shot('tools-compare', {
    marks: [main.locator('textarea'), columns.nth(0), columns.nth(1), compare],
  });

  // 5–6. Convert voice: source clip + target voice, then the converted take
  await nav('convert.convert').click();
  await main.locator('input[type="file"]').setInputFiles(CLIP);
  const voice = main.getByRole('button', { name: 'Narrator', exact: true });
  await voice.click();
  const convert = main.getByRole('button', { name: L('clone.define_convert'), exact: true });
  const sourceSection = main.getByRole('region', { name: L('convert.source_kicker') });
  const match = main.getByRole('switch');
  await page.setViewportSize({ width: 1280, height: 960 }); // the Convert button sits below an 800px window
  await shot('tools-convert-input', { marks: [sourceSection, voice, match, convert] });
  await convert.click();
  const converted = main.getByRole('region', { name: L('convert.result_kicker') });
  await converted.waitFor({ timeout: 600000 });
  await converted.scrollIntoViewIfNeeded();
  await shot('tools-convert-result', { marks: [converted] });
}
