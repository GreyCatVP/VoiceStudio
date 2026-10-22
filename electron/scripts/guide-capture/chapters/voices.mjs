// Chapter "voices": saved voices (edit, preview, export, delete) and the Gallery.
// Needs the "Maya" voice the clone chapter saves. Opening Community fetches the
// community list from jsDelivr; nothing else here downloads anything.
const VOICE = 'Maya';

export default async function capture({ page, goto, shot, t, L }) {
  await page.addInitScript(() => {
    addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = '[data-sonner-toaster]{display:none!important}';
      document.head.append(style);
    });
  });

  await goto('/personas');
  const row = page.getByRole('button', { name: VOICE, exact: true }).first();
  await row.waitFor();
  await row.hover();
  const card = page.locator('li:has(> button[aria-label="' + VOICE + '"])').first();
  const editLabel = L('paneActions.edit');
  const edit = card.getByRole('button', { name: editLabel });
  const filters = page.getByRole('group').first();
  await shot('voices-saved', {
    marks: [page.getByPlaceholder(/./).first(), filters, card, edit],
  });

  await edit.click();
  const pane = page.locator('[data-slot="workspace-pane"], aside').last();
  const name = page.getByLabel(L('clone.profile_name'), { exact: true }).last();
  await name.waitFor();
  const replace = page.getByRole('button', { name: L('clone.replace_reference') }).first();
  await page.waitForTimeout(800);
  await shot('voices-edit', { marks: [replace, name] });

  const exportSummary = pane.locator('summary', { hasText: L('voice_profile.persona_export') }).first();
  const trySummary = pane.locator('summary', { hasText: L('voice_profile.try_voice') }).first();
  await exportSummary.click();
  await trySummary.click();
  const includeClip = pane.getByRole('checkbox').first();
  const generate = pane.getByRole('button', { name: L('voice_profile.gen_preview') }).first();
  await generate.click();
  // The preview renders with the active engine; wait until the button is free again.
  await page.waitForTimeout(3000);
  await generate.filter({ hasText: L('voice_profile.gen_preview') }).waitFor({ timeout: 300000 });
  await page.waitForTimeout(1500);
  await exportSummary.scrollIntoViewIfNeeded();
  await shot('voices-edit-more', { marks: [exportSummary, includeClip, trySummary, generate] });

  await goto('/gallery');
  const useVoice = page.getByRole('button', { name: L('clone.select_profile'), exact: true }).first();
  await useVoice.waitFor({ timeout: 60000 });
  const first = page.locator('div:has(> div button)', { has: useVoice }).last();
  const categories = page.getByRole('button', { name: L('homeUi.all'), exact: true }).first();
  const zones = page.locator('div:has(> button[aria-pressed]):has(> button:nth-child(3))').first();
  await shot('voices-gallery', { marks: [zones, categories, useVoice] });
  void first;

  // Result: "Use voice" saves the archetype and opens it in Design.
  await useVoice.click();
  await page.waitForFunction(() => location.hash.includes('/design'), null, { timeout: 60000 });
  await page.waitForTimeout(1500);
  const details = page.locator('details:has(> summary:has-text("' + L('sidebarTools.details') + '")) > summary').first();
  await shot('voices-result', { marks: [details] });
  await goto('/gallery');

  await page.getByRole('button', { name: L('gallery.zone_community'), exact: true }).first().click();
  const designer = page.getByRole('button', { name: L('gallery.open_designer') }).first();
  await designer.waitFor({ timeout: 60000 });
  const explainer = page.getByText('omnivoice-gallery').first();
  await shot('voices-community', { marks: [explainer, designer] });

  await page.getByRole('button', { name: L('gallery.zone_imports'), exact: true }).first().click();
  await page.waitForTimeout(1500);
  const url = page.getByPlaceholder(L('gallery.import_placeholder'), { exact: true }).first();
  const upload = page.getByRole('button', { name: L('gallery.upload') }).first();
  const persona = page.getByRole('button', { name: L('gallery.import_persona') }).first();
  await shot('voices-imports', { marks: [url, upload, persona] });

  await goto('/settings/models');
  const previews = page.getByText(L('models.voice_previews'), { exact: true }).first();
  await previews.scrollIntoViewIfNeeded();
  const toggle = page.getByRole('switch').first();
  await shot('voices-previews', { marks: [toggle] });
}
