// Chapter "getting-started": first-run setup, installing a model, licence
// acceptance, and the engine panel. Installs a small dictation model for real
// and removes it again at the end, so every language run starts clean.
const MODEL = 'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8';
const API = process.env.GUIDE_API_URL || 'http://127.0.0.1:3920';

async function resetModel(page) {
  await page.request.post(`${API}/models/licenses/revoke`, { data: { repo_id: MODEL } }).catch(() => {});
  await page.request.delete(`${API}/models/${MODEL}`).catch(() => {});
}

export default async function capture({ page, goto, shot, t, language, base, L }) {
  // ── First run: a context without the setup-complete flag ──────────────────
  const fresh = await page.context().browser().newContext({
    viewport: { width: 1280, height: 800 },
    locale: language,
  });
  await fresh.addInitScript((lang) => localStorage.setItem('voicestudio.locale', lang), language);
  const first = await fresh.newPage();
  try {
    await first.goto(`${base}/#/`, { waitUntil: 'networkidle' });
    const footer = first.locator('footer').last();
    const next = footer.getByRole('button').last();
    await first.getByText(t({ en: 'Operating system', th: 'Operating system' })).first().waitFor({ timeout: 120000 });
    await next.waitFor();
    await first.waitForFunction(() => {
      const buttons = [...document.querySelectorAll('footer button')];
      return buttons.length && !buttons.at(-1).disabled;
    }, null, { timeout: 120000 });
    await shotOn(first, language, 'getting-started-setup-check', [
      first.locator('nav').first(),
      first.getByRole('button', { name: L('engines.recheck') }),
      next,
    ]);

    await next.click();
    const packs = first.getByRole('group', { name: L('models.pack_title') });
    await packs.waitFor({ timeout: 60000 });
    await first.waitForTimeout(1500);
    const install = first.getByRole('button', { name: t({ en: /^Install .* pack/, th: /^ติดตั้งชุด/ }) });
    const stillNeeded = first.getByText(L('setup.still_needed')).first();
    await shotOn(first, language, 'getting-started-setup-packs', [packs, install, stillNeeded]);

    // The required voice model runs on the remote GPU here, so this machine
    // never "finishes" the model step; report it ready to reach the privacy step.
    await fresh.route('**/setup/status', async (route) => {
      const response = await route.fetch();
      const json = await response.json();
      await route.fulfill({ response, json: { ...json, models_ready: true, missing: [] } });
    });
    await first.waitForFunction(() => !document.querySelector('footer button:last-child')?.disabled, null, {
      timeout: 30000,
    });
    await next.click();
    const yes = first.getByRole('button', { name: L('consent.yes') });
    const no = first.getByRole('button', { name: L('consent.no') });
    await yes.waitFor({ timeout: 30000 });
    await shotOn(first, language, 'getting-started-setup-privacy', [yes, no]);
  } finally {
    await fresh.close();
  }

  // ── Model catalogue: install a model and accept its licence ──────────────
  await resetModel(page);
  await goto('/settings/models/dictation');
  const row = page.locator(`div[data-slot="settings-row"]:has(h3[id="model-${MODEL.replaceAll('/', '-')}"])`);
  await row.waitFor({ timeout: 60000 });
  await row.scrollIntoViewIfNeeded();
  const licence = row.getByRole('button', { name: t({ en: /^Licence:/, th: /^สัญญาอนุญาต:/ }) });
  const download = row.getByRole('button', { name: L('modelMaintenance.download') });
  await shot('getting-started-catalogue', {
    marks: [page.locator('nav a[href*="/settings/models"]').first(), row.locator('h3'), licence, download],
  });

  await download.click();
  const cancel = row.getByRole('button', { name: L('clone.cancel') });
  await cancel.waitFor({ timeout: 60000 });
  await page.waitForTimeout(2500);
  await shot('getting-started-downloading', { marks: [row.locator('[role="progressbar"], .h-1\\.5').first(), cancel] });

  const needsLicence = row.getByText(L('modelLicense.acceptNeeded'));
  await needsLicence.waitFor({ timeout: 600000 });
  await licence.click();
  const dialog = page.getByRole('dialog');
  const box = dialog.getByRole('checkbox');
  await box.waitFor({ timeout: 30000 });
  await box.check();
  const accept = dialog.getByRole('button', { name: L('modelLicense.accept') });
  await shot('getting-started-licence', { marks: [box, accept] });
  await accept.click();
  await dialog.getByRole('button', { name: L('modelLicense.revoke') }).waitFor({ timeout: 30000 });
  await page.keyboard.press('Escape');
  const installed = row.getByText(L('modelMaintenance.installed'), { exact: true });
  // The catalogue refetches after the acceptance; under load that can lag.
  if (!(await installed.isVisible().catch(() => false))) {
    await installed.waitFor({ timeout: 60000 }).catch(async () => {
      await page.reload({ waitUntil: 'networkidle' });
      await installed.waitFor({ timeout: 60000 });
    });
  }
  await row.scrollIntoViewIfNeeded();
  await shot('getting-started-installed', { marks: [installed] });

  // ── Engine panel and the speed / quality preset ──────────────────────────
  await goto('/clone');
  const panel = page.locator('footer:has(#sidebar-engine-details)');
  await panel.waitFor({ timeout: 30000 });
  await panel.locator('[data-slot="engine-view-toggle"] button').nth(1).click(); // "Models" view
  await page.waitForTimeout(1200);
  await shot('getting-started-engine-panel', {
    marks: [
      panel.locator('button[aria-label*=":"]').first(),
      panel.getByRole('radiogroup', { name: L('performanceProfile.title') }),
      panel.locator('[data-slot="engine-row"]').first(),
      panel.locator('[data-slot="engine-view-toggle"]'),
    ],
  });

  await goto('/settings/models/tts');
  const select = page.getByRole('button', { name: L('modelSettings.select'), exact: true }).first();
  await select.waitFor({ timeout: 30000 });
  const selected = page.getByText(L('modelSettings.selected'), { exact: true }).first();
  const test = page.getByRole('button', { name: L('engines.testEngine') }).nth(1);
  await shot('getting-started-engine-select', { marks: [selected, select, test] });

  await resetModel(page);
}

// Shoot a page that is not ctx.page, with the same marks and WebP output as run.mjs.
async function shotOn(target, language, id, marks) {
  const { execFileSync } = await import('node:child_process');
  const { mkdirSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { dirname, join } = await import('node:path');
  const { fileURLToPath } = await import('node:url');
  const assets = join(dirname(fileURLToPath(import.meta.url)), '../../../src/renderer/src/features/guide/assets');
  await target.waitForTimeout(400);
  const boxes = [];
  for (const [index, mark] of marks.entries()) {
    const box = await mark.first().boundingBox();
    if (box) boxes.push({ ...box, n: index + 1 });
    else console.warn(`  ! highlight ${index + 1} not visible`);
  }
  await target.evaluate((items) => {
    for (const item of items) {
      const frame = document.createElement('div');
      frame.dataset.guideMark = '';
      Object.assign(frame.style, {
        position: 'fixed', left: `${item.x - 4}px`, top: `${item.y - 4}px`,
        width: `${item.width + 8}px`, height: `${item.height + 8}px`, border: '3px solid #f43f5e',
        borderRadius: '10px', boxShadow: '0 0 0 4px rgb(244 63 94 / 0.25)', zIndex: 2147483646,
        pointerEvents: 'none',
      });
      const badge = document.createElement('div');
      badge.dataset.guideMark = '';
      badge.textContent = String(item.n);
      Object.assign(badge.style, {
        position: 'fixed', left: `${Math.max(2, item.x - 16)}px`, top: `${Math.max(2, item.y - 16)}px`,
        width: '26px', height: '26px', borderRadius: '13px', background: '#f43f5e', color: '#fff',
        font: '700 14px/26px system-ui, sans-serif', textAlign: 'center', zIndex: 2147483647,
        pointerEvents: 'none', boxShadow: '0 1px 4px rgb(0 0 0 / 0.4)',
      });
      document.body.append(frame, badge);
    }
  }, boxes);
  const png = join(tmpdir(), `guide-${language}-${id}.png`);
  await target.screenshot({ path: png, animations: 'disabled' });
  await target.evaluate(() => document.querySelectorAll('[data-guide-mark]').forEach((node) => node.remove()));
  mkdirSync(join(assets, language), { recursive: true });
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', png, '-c:v', 'libwebp', '-quality', '80', join(assets, language, `${id}.webp`)]);
  rmSync(png, { force: true });
  console.log(`  ✓ ${language}/${id}`);
}
