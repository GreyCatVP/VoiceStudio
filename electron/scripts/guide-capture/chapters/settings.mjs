// Chapter "settings": the Settings sections. Read-only: nothing is changed.
export default async function capture({ page, goto, shot, t, L }) {
  const nav = page.getByRole('navigation', { name: L('nav.settings') });
  const link = (path) => nav.locator(`a[href$="${path}"]`).first();

  await goto('/settings/general');
  const language = page.locator('#language-label').locator('xpath=ancestor::div[@data-slot="settings-row"]').getByRole('combobox');
  await shot('settings-general', {
    marks: [nav, page.locator('aside input[type="search"]'), language, page.getByRole('group', { name: L('settings.review_mode') }).last()],
  });

  const search = page.locator('aside input[type="search"]');
  await search.fill(t({ en: 'token', th: 'โทเค็น' }));
  await page.waitForTimeout(500);
  await shot('settings-search', { marks: [search, link('/settings/credentials')] });
  await search.fill('');

  await goto('/settings/models');
  await page.waitForTimeout(1500);
  await shot('settings-models', {
    marks: [
      link('/settings/models'),
      page.getByRole('switch').first(),
      page.locator('main a[href$="/settings/models/tts"], section a[href$="/settings/models/tts"]').last(),
    ],
  });

  await goto('/settings/performance');
  await page.waitForTimeout(1500);
  const check = page.locator('div:has(> div > h3#system-preflight-check) button').first();
  await shot('settings-compute', {
    marks: [check, page.getByRole('radiogroup').first(), page.getByRole('radiogroup').nth(1)],
  });

  await goto('/settings/privacy');
  const switches = page.getByRole('switch');
  await switches.first().waitFor();
  await shot('settings-privacy', {
    marks: [switches.nth(0), switches.nth(1), page.locator('input[type="number"]').first()],
  });

  await goto('/settings/storage');
  // The disk-usage scan walks every folder; wait for it to finish.
  await page.getByText(L('common.loading'), { exact: true }).first()
    .waitFor({ state: 'hidden', timeout: 180000 }).catch(() => {});
  await page.waitForTimeout(1000);
  await shot('settings-storage', {
    marks: [
      page.locator('[data-slot="settings-row"]').nth(0),
      page.locator('[data-slot="settings-row"]').nth(1),
      page.getByRole('button', { name: L('common.refresh') }).first(),
    ],
  });
}
