// Chapter "workflows": build a batch-narration workflow from a template, run it for real,
// and show that a call draft only dials after confirmation.
export default async function capture({ page, goto, shot, t, L }) {
  await goto('/calls');
  const rail = page.locator('aside.workflow-rail');
  // The canvas chunk is large; on a busy dev server the first load can come up blank.
  await rail.waitFor({ timeout: 30000 }).catch(async () => {
    await page.reload({ waitUntil: 'networkidle' });
    await rail.waitFor({ timeout: 60000 });
  });
  await shot('workflows-canvas', {
    marks: [
      rail.locator('.workflow-library-list'),
      rail.locator('.workflow-templates'),
      rail.locator('.workflow-palette'),
      page.locator('section.workflow-stage'),
      page.locator('.workflow-intro__actions button').first(),
    ],
  });

  // Template: Start (scripts) -> Speak -> End, with the Start step selected.
  const template = rail.locator('.workflow-templates button').first();
  await template.click();
  const scripts = page.locator('#workflow-scripts');
  await scripts.waitFor({ timeout: 10000 });
  await scripts.fill(t({
    en: 'Welcome to this lesson. Let’s get started.\n---\nEach clip is spoken by the voice you choose.',
    th: 'ยินดีต้อนรับสู่บทเรียนนี้ มาเริ่มกันเลย\n---\nแต่ละคลิปจะพูดด้วยเสียงที่คุณเลือก',
  }));
  await shot('workflows-template', {
    marks: [template, page.locator('section.workflow-stage .react-flow__node').first(), scripts],
  });

  // Pick a saved voice on the Speak step.
  await page.locator('section.workflow-stage .react-flow__node').nth(1).click();
  const inspector = page.locator('aside.workflow-inspector');
  const voice = inspector.locator('.workflow-select-trigger').first();
  await voice.click();
  await page.locator('.workflow-shared-select').getByText('Narrator', { exact: true }).first().click();
  await page.waitForTimeout(400);
  await shot('workflows-speak', {
    marks: [page.locator('section.workflow-stage .react-flow__node').nth(1), voice,
      inspector.locator('.workflow-select-trigger').nth(1)],
  });

  // Run it for real; speech runs on the configured TTS engine.
  await page.locator('.workflow-intro__actions button').first().click();
  const runner = page.locator('section.workflow-runner');
  await runner.waitFor({ timeout: 10000 });
  const start = runner.locator('.flex.gap-2 button').first();
  await page.waitForFunction((button) => !button.disabled, await start.elementHandle(), { timeout: 60000 });
  await start.click();
  await runner.locator('[role="status"]').waitFor({ timeout: 30000 });
  await page.waitForFunction(() => {
    const status = document.querySelector('section.workflow-runner [role="status"]')?.textContent || '';
    const match = status.match(/(\d+)\s*\/\s*(\d+)/);
    return (match && match[1] === match[2]) || document.querySelector('section.workflow-runner [role="alert"]');
  }, null, { timeout: 900000, polling: 2000 });
  await shot('workflows-run', {
    marks: [runner.locator('[role="status"]'), runner.locator('article.workflow-run-output').first(),
      runner.locator('article.workflow-run-output button').first()],
  });

  // A call step is a local draft: Calls opens a form, and dialing needs a confirmation.
  await page.getByRole('button', { name: L('nav.calls'), exact: true }).first().click();
  await page.waitForTimeout(1500);
  await shot('workflows-calls', {
    marks: [page.getByRole('button', { name: L('workflows.canvas') }).first(),
      page.locator(`[aria-label="${L('calls.new_call')}"]`).first()],
  });
}
