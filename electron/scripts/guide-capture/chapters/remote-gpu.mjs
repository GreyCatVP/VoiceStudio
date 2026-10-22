// Chapter "remote-gpu": Settings → Remote GPU (Ray and an unsaved Modal draft),
// the no-GPU choice card, a routed engine and a live Ray job.
// Never saves: other chapters use the shared backend's Ray provider meanwhile.
const API = (process.env.GUIDE_API_URL || 'http://127.0.0.1:3920').replace(/\/$/, '');

export default async function capture({ page, goto, shot, t, L }) {
  const row = (id) => page.locator(`[data-slot="settings-row"]:has(h3#${id})`);
  const control = (id) => page.locator(`[role="group"][aria-labelledby="${id}"]`);

  await page.setViewportSize({ width: 1280, height: 1000 });
  await goto('/settings/ray');
  await row('ray-dashboard-url').waitFor();
  // Reveal the token field with its switch (an unsaved draft; reloaded below).
  await control('ray-use-token').getByRole('switch').click();
  await row('ray-token').waitFor();
  await shot('remote-gpu-connection', {
    marks: [
      control('remote-provider'),
      control('ray-enabled'),
      control('ray-dashboard-url'),
      control('ray-use-token'),
      control('ray-token'),
      control('ray-use-cf'),
    ],
  });
  await page.reload({ waitUntil: 'networkidle' }); // drop the draft: Test connection needs saved settings
  await row('ray-dashboard-url').waitFor();

  // Test connection runs a real probe job on the cluster (up to 3 minutes).
  const test = control('ray-test').locator('button');
  await test.scrollIntoViewIfNeeded();
  await test.click();
  const details = page.locator('dl').filter({ hasText: L('settings.ray_info_version') });
  await details.waitFor({ timeout: 240000 });
  await row('remote-provider').scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 260);
  await shot('remote-gpu-test', {
    marks: [test, page.locator('[role="status"]').filter({ hasText: /Ray/ }), page.locator('[role="alert"]').first(), details],
  });

  await page.locator('#ray-engines-tts').evaluate((node) => node.scrollIntoView({ block: 'start' }));
  await page.mouse.wheel(0, -40);
  await shot('remote-gpu-engines', {
    marks: [page.locator('[role="group"][aria-labelledby="ray-engines-tts"]'), page.locator('[role="group"][aria-labelledby="ray-engines-asr"]')],
  });

  await page.locator('h3#ray-num-gpus').scrollIntoViewIfNeeded();
  // A short real generation on a routed engine: its Ray job shows in the list.
  const generation = page.request
    .post(`${API}/generate`, {
      multipart: { text: 'This sentence was rendered on the remote GPU.', language: 'en', engine: 'omnivoice' },
      timeout: 600000,
    })
    .catch((error) => console.warn(`  ! generate: ${error.message}`));
  const running = page.locator('tbody tr').filter({ hasText: /RUNNING|PENDING/ }).first();
  await running.waitFor({ timeout: 180000 });
  await page.locator('h3#ray-jobs').scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 400);
  await shot('remote-gpu-jobs', {
    marks: [control('ray-num-gpus'), control('ray-num-cpus'), running],
  });
  await generation;

  // Modal: an unsaved draft only (switch the provider, never press Save).
  await page.reload({ waitUntil: 'networkidle' });
  await control('remote-provider').getByRole('button', { name: 'Modal' }).first().click()
    .catch(() => control('remote-provider').getByText('Modal').click());
  await row('modal-token-id').waitFor();
  await shot('remote-gpu-modal', {
    marks: [control('remote-provider'), control('modal-token-id'), control('modal-token-secret'), control('ray-test')],
  });
  await page.locator('h3#modal-gpu').scrollIntoViewIfNeeded();
  await shot('remote-gpu-modal-resources', {
    marks: [control('modal-gpu'), control('modal-app'), control('modal-volume')],
  });

  // The no-GPU choice card appears only while no remote GPU is set up; the
  // capture backend has one, so its GPU check is shown as on a fresh machine.
  await page.route('**/setup/preflight', async (route) => {
    const response = await route.fetch();
    const report = await response.json();
    for (const check of report.checks ?? []) {
      if (check.id !== 'gpu') continue;
      delete check.remote;
      Object.assign(check, {
        status: 'warn',
        detail: 'No compatible GPU detected — running CPU-only.',
        fix: 'Everything works on CPU, just ~10× slower than a GPU — integrated graphics are not used for AI. For the best CPU experience pick a lightweight voice engine (KittenTTS, Supertonic-3, PocketTTS) and a small Whisper model in the Model Catalogue. If you have an NVIDIA/AMD card, check drivers are installed.',
        choices: ['cpu', 'ray', 'modal'],
      });
    }
    await route.fulfill({ response, json: report });
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await goto('/settings/performance');
  await page.locator('div:has(> div > h3#system-preflight-check) button').first().click();
  const choices = page.locator('[role="group"]').filter({ hasText: L('setup.gpu_choice_cpu') }).first();
  await choices.waitFor({ timeout: 120000 });
  await choices.scrollIntoViewIfNeeded();
  const gpu = page.locator('li').filter({ has: choices });
  await shot('remote-gpu-choice', {
    marks: [choices.getByRole('button').nth(0), choices.getByRole('button').nth(1), choices.getByRole('button').nth(2)],
    target: gpu,
  });
  await choices.getByRole('button').nth(1).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('h3#ray-dashboard-url').waitFor();
  await shot('remote-gpu-choice-dialog', {
    marks: [dialog.locator('h2').first(), dialog.locator('[role="group"][aria-labelledby="remote-provider"]')],
  });
  await page.keyboard.press('Escape'); // closes without saving

  // A routed engine reports where it runs: "network" in the engine list.
  await goto('/settings/models/tts');
  const routed = page.getByText('network', { exact: true });
  await routed.first().waitFor({ timeout: 60000 });
  await shot('remote-gpu-network', { marks: [routed.nth(0), routed.nth(1)] });
}
