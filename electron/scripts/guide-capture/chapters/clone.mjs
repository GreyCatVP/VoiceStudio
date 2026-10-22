// Chapter "clone": clone a voice from a short clip, generate, find the take.
// Runs for real: the take is rendered by the active engine (OmniVoice on the
// remote GPU in the capture setup). Leaves one saved voice, "Maya".
const API = process.env.GUIDE_API_URL || 'http://127.0.0.1:3920';
/** A 5–15 s clip of clean English speech (GUIDE_CLONE_CLIP=/path/to/clip.wav). */
const CLIP = process.env.GUIDE_CLONE_CLIP;
const NAME = 'Maya';

/** Remove the voice and takes an earlier run left, so each language starts clean. */
async function reset(request, script) {
  const profiles = await (await request.get(`${API}/profiles`)).json();
  for (const profile of profiles.filter((item) => item.name === NAME))
    await request.delete(`${API}/profiles/${profile.id}`);
  const history = await (await request.get(`${API}/history`)).json();
  const items = Array.isArray(history) ? history : (history.items ?? []);
  for (const item of items.filter((take) => take.text === script))
    await request.delete(`${API}/history/${item.id}`);
}

export default async function capture({ page, goto, shot, t, L }) {
  const script = t({
    en: 'Welcome to VoiceStudio. This voice was cloned from a five second clip.',
    th: 'Welcome to VoiceStudio. This voice was cloned from a five second clip.',
  });
  if (!CLIP) throw new Error('Set GUIDE_CLONE_CLIP to a 5–15 s speech clip');
  await reset(page.request, script);
  // Toasts would cover the controls the marks point at.
  await page.addInitScript(() => {
    addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = '[data-sonner-toaster]{display:none!important}';
      document.head.append(style);
    });
  });

  await goto('/clone');
  const drop = page.locator('label:has(+ *), label').filter({ has: page.locator('svg') })
    .filter({ hasText: L('clone.drop_audio').split(/ — | หรือ/)[0] }).first();
  const record = page.getByRole('button', { name: L('clone.record'), exact: true }).first();
  await drop.waitFor();
  await shot('clone-choose', { marks: [drop, record] });

  const transcript = page.getByLabel(L('clone.transcript'), { exact: true });
  // Automatic transcription fills the field; wait for it rather than typing.
  // A dev-server reload drops the unsaved clip, so upload again when it does.
  for (let attempt = 1; ; attempt += 1) {
    await page.locator('input[type=file][accept^=audio]').setInputFiles(CLIP);
    const filled = await page
      .waitForFunction(
        () => [...document.querySelectorAll('textarea')].some((node) => node.value.trim().length > 10),
        null,
        { timeout: 240000 },
      )
      .then(() => true, () => false);
    if (filled) break;
    if (attempt === 3) throw new Error('reference transcription never filled the Transcript field');
    await goto('/clone');
  }
  const name = page.getByLabel(L('clone.profile_name'), { exact: true });
  await name.fill(NAME);
  const save = page.getByRole('button', { name: L('clone.save'), exact: true });
  await save.waitFor();
  await page.waitForFunction(
    () => ![...document.querySelectorAll('button')].some((b) => b.type === 'submit' && b.disabled),
    null,
    { timeout: 400000 },
  );
  const clip = page.locator('div:has(> div > svg) :text("h200_clip0.wav")').first();
  await shot('clone-reference', {
    marks: [page.locator('div.rounded-lg.bg-muted\\/30:has(audio), div.rounded-lg.bg-muted\\/30').filter({ hasText: 'h200_clip0.wav' }).first(), transcript, name, save],
  });
  void clip;

  await save.click();
  const editor = page.locator('[data-clone-script]');
  await editor.waitFor({ timeout: 60000 });
  await editor.fill(script);
  const synth = page.getByRole('button', { name: L('clone.synthesize') }).first();
  const voice = page.getByRole('button', { name: L('cloneFlow.change_voice') }).first();
  const language = page.locator('[data-slot="workspace-content"] button', { hasText: L('clone.auto') }).first();
  await page.waitForTimeout(600);
  await shot('clone-script', { marks: [voice, editor, language, synth] });

  await synth.click();
  await page.getByText(L.pattern('clone.output_meta')).first().waitFor({ timeout: 300000 });
  const panel = page.locator('div:has(> div > :text-is("' + L('clone.output_title') + '"))').last();
  // The take panel's own heading (in Thai the title-bar history button has the same label).
  const take = panel.getByText(L('clone.output_title'), { exact: true }).first();
  const play = panel.locator('button').filter({ has: page.locator('svg') }).nth(2);
  const download = page.getByRole('button', { name: L('clone.download') }).first();
  await shot('clone-take', { marks: [take, play, download] });

  // Taller window: the take list gets more than one row of room under the menu.
  await page.setViewportSize({ width: 1280, height: 1100 });
  await page.getByRole('button', { name: L('clone.history_title') }).first().click();
  // shortcut: switching the sidebar to Recent takes leaves its virtualised list empty until
  // it remounts (voices-sidebar.tsx VirtualTakes); drop the reload once that is fixed.
  await page.reload({ waitUntil: 'networkidle' });
  // The take's row in the history list (the script editor holds the same text).
  const row = page.locator('button[aria-pressed]').filter({ hasText: script.slice(0, 24) }).first();
  await row.waitFor({ timeout: 60000 });
  await row.click({ position: { x: 8, y: 6 } });
  await page.waitForTimeout(1200);
  const details = page.locator('aside, [data-slot="workspace-pane"]').last();
  await shot('clone-history', { marks: [row, details] });

  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1280, height: 800 });
  await goto('/clone');
  await page.getByRole('button', { name: L('cloneFlow.voice_sample'), exact: true }).first().click();
  await page.waitForTimeout(1500);
  const edit = page.getByRole('button', { name: L('clone.edit_voice'), exact: true }).first();
  const stored = page.getByLabel(L('clone.transcript'), { exact: true }).last();
  await shot('clone-voice-sample', { marks: [edit, stored] });

  // Result: the saved voice is offered whenever a voice is chosen.
  await page.getByRole('button', { name: L('cloneFlow.change_voice') }).first().click();
  const savedVoice = page.getByRole('button', { name: new RegExp('^' + NAME) }).first();
  await savedVoice.waitFor();
  await shot('clone-result', { marks: [savedVoice] });
}
