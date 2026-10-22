// Chapter "design": describe a voice, generate with it, save it as a design voice.
// Runs for real (OmniVoice voice design). Leaves one saved voice, "Storyteller".
const API = process.env.GUIDE_API_URL || 'http://127.0.0.1:3920';
const NAME = 'Storyteller';
const DESCRIPTION = 'an elderly British man with a low voice, slightly raspy';
const SCRIPT = 'Long ago, in a quiet village by the sea, there lived an old lighthouse keeper.';

async function reset(request) {
  const profiles = await (await request.get(`${API}/profiles`)).json();
  for (const profile of profiles.filter((item) => item.name === NAME))
    await request.delete(`${API}/profiles/${profile.id}`);
  const history = await (await request.get(`${API}/history`)).json();
  const items = Array.isArray(history) ? history : (history.items ?? []);
  for (const item of items.filter((take) => take.text === SCRIPT))
    await request.delete(`${API}/history/${item.id}`);
}

export default async function capture({ page, goto, shot, t, L }) {
  await reset(page.request);
  await page.addInitScript(() => {
    addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = '[data-sonner-toaster]{display:none!important}';
      document.head.append(style);
    });
  });
  await goto('/design');

  const starting = page.locator('details:has(> summary:has-text("' + L('clone.starting_points') + '"))').first();
  const demo = page.getByText(L('demo.hear_demo'), { exact: true }).first();
  const useDesign = page.getByRole('button', { name: L('demo.preset_use') }).first();
  await demo.waitFor();
  await shot('design-start', { marks: [starting, demo, useDesign] });
  await demo.click(); // fold the demo list so the script and the take stay in view

  const describe = page.locator('#voice-description');
  await describe.fill(DESCRIPTION);
  const status = page.locator('section:has(#voice-description) p[role=status]');
  await status.filter({ hasText: /slightly raspy/ }).waitFor({ timeout: 30000 });
  const details = page.locator('details:has(> summary:has-text("' + L('sidebarTools.details') + '"))').first();
  await details.locator('summary').click();
  await page.waitForTimeout(500);
  await details.locator('summary').scrollIntoViewIfNeeded();
  await shot('design-describe', { marks: [describe, status, details.locator('summary')] });

  const seed = page.getByLabel(L('clone.seed_label'), { exact: true });
  await seed.scrollIntoViewIfNeeded();
  const pitch = details.locator('fieldset').nth(2);
  const accent = details.locator('fieldset').nth(4);
  const reroll = page.getByRole('button', { name: L('clone.seed_reroll') });
  await shot('design-details', { marks: [pitch, accent, seed, reroll] });

  const script = page.locator('#design-script');
  await script.fill(SCRIPT);
  const synth = page.getByRole('button', { name: L('clone.synthesize') }).first();
  await page.waitForTimeout(500);
  await shot('design-script', { marks: [script, synth] });

  await synth.click();
  await page.getByText(L.pattern('clone.output_meta')).first().waitFor({ timeout: 300000 });
  const take = page.getByText(L('clone.output_title'), { exact: true }).first();
  const download = page.getByRole('button', { name: L('clone.download') }).first();
  await shot('design-take', { marks: [take, download] });

  const name = page.getByLabel(L('clone.profile_name'), { exact: true });
  await name.scrollIntoViewIfNeeded();
  await name.fill(NAME);
  const save = page.getByRole('button', { name: L('clone.save_as_profile') }).first();
  await save.click();
  const voice = page.getByRole('button', { name: L('cloneFlow.change_voice') }).first();
  await voice.filter({ hasText: NAME }).waitFor({ timeout: 30000 });
  const saved = page.locator('details:has(> summary:has-text("' + L('clone.saved_profiles') + '"))').first();
  await saved.locator('summary').click();
  await saved.scrollIntoViewIfNeeded();
  await voice.scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await shot('design-saved', { marks: [saved, voice] });

  // Result: the design is a saved voice with the designed-voice (wand) mark.
  await goto('/personas');
  const filter = L('designWorkspace.title');
  await page.locator('[role=group] [aria-label="' + filter + '"]').first().click();
  const row = page.locator('li:has(> button[aria-label="' + NAME + '"])').first();
  await row.waitFor();
  await shot('design-result', { marks: [page.locator('[role=group] [aria-label="' + filter + '"]').first(), row] });
}
