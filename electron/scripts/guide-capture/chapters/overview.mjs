// Chapter "overview": the main window and the system check.
export default async function capture({ page, goto, shot, t }) {
  await goto('/');
  await shot('overview-main', {
    marks: [
      '[data-slot="workspace-navigation"]',
      'main[data-slot="workspace-content"] > section, main[data-slot="workspace-content"] section',
      'main[data-slot="workspace-content"] header.workspace-titlebar',
    ],
  });

  await goto('/settings/performance');
  // By row id: the button's label changes once the check has run.
  const check = page.locator('div:has(> div > h3#system-preflight-check) button').first();
  await check.click();
  const gpu = page.locator('li', { hasText: t({ en: 'GPU acceleration', th: 'GPU' }) }).first();
  await gpu.waitFor({ timeout: 120000 });
  await gpu.scrollIntoViewIfNeeded();
  await shot('overview-system-check', { marks: [check, gpu] });
}
