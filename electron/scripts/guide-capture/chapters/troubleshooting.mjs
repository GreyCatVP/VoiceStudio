// Chapter "troubleshooting": self-check, logs, an error card, the bug report
// button and the remote GPU job list.
export default async function capture({ page, goto, shot, t, L }) {
  // 1. Settings → System preflight: the About facts, then the self-check.
  await goto('/settings/diagnostics');
  const row = (id) => page.locator('[data-slot="settings-row"]', { has: page.locator(`#diagnostics-${id}`) });
  await row('python').getByText(/\d+\.\d+/).waitFor({ timeout: 60000 });
  await shot('troubleshooting-about', {
    marks: [row('version'), row('device'), row('tts'), row('data-directory')],
  });

  const run = page.getByRole('button', { name: L('about.self_check') });
  await run.scrollIntoViewIfNeeded();
  await run.click();
  const warning = page.locator('li', { hasText: L('about.self_check_warn') }).first();
  await warning.waitFor({ timeout: 180000 });
  await run.evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await page.mouse.wheel(0, -40);
  await shot('troubleshooting-self-check', {
    marks: [
      run,
      page.getByRole('button', { name: L('about.save_bundle') }),
      page.getByRole('button', { name: L('about.copy_diagnostics') }),
      warning,
    ],
  });

  // 2. An error card, produced for real: probe a file that does not exist.
  await goto('/tools');
  await page.getByRole('button', { name: L('tools.probe_file'), exact: true }).click();
  const main = page.locator('main[data-slot="workspace-content"] section.overflow-y-auto').first();
  await main.locator('input').first().fill('/home/me/Videos/missing-interview.mp4');
  await main.getByRole('button', { name: L('tools.probe'), exact: true }).click();
  const card = main.getByRole('alert');
  await card.waitFor({ timeout: 60000 });
  await shot('troubleshooting-error-card', { marks: [card] });

  // 3. Settings → Logs, filtered to warnings.
  await goto('/settings/logs');
  const logs = page.getByRole('region', { name: L('settings.uninstall_target_logs'), exact: true });
  const search = logs.locator('input[type="search"]');
  await search.fill('WARNING');
  await page.waitForTimeout(1500);
  await shot('troubleshooting-logs', {
    marks: [
      logs.getByRole('button', { name: L('common.backend'), exact: true }),
      search,
      logs.getByRole('button', { name: L('repairAgent.title') }),
    ],
  });

  // 4. Settings → Support: the prefilled GitHub issue button (not clicked).
  await goto('/settings/support');
  const report = page.getByRole('button', { name: L('contact.bug_title') });
  await report.scrollIntoViewIfNeeded();
  await shot('troubleshooting-report', {
    marks: [report],
  });

  // 5. Settings → Remote GPU: the connection test.
  await goto('/settings/ray');
  const jobs = page.getByText(L('settings.ray_jobs_title'), { exact: true }).first();
  await jobs.waitFor({ timeout: 60000 });
  const test = page.getByRole('button', { name: L('settings.remote_backend_test') });
  await test.evaluate((element) => element.scrollIntoView({ block: 'center' }));
  await test.click();
  const outcome = page.getByText(L('settings.ray_kind_ok'));
  await outcome.first().waitFor({ timeout: 240000 });
  await outcome.first().scrollIntoViewIfNeeded();
  // Crop to the test row: the dashboard address above it is private to this machine's owner.
  await shot('troubleshooting-remote-test', {
    target: page.locator('[data-slot="settings-row"]', { has: test }),
    marks: [test, outcome.first()],
  });
}
