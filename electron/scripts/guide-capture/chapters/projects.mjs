// Chapter "projects": fill the library with real items (a transcript, a story project,
// a saved dubbing project), then browse, open and delete from it.
const CLIP = '/tmp/claude-0/-root-voicestudio/a001375f-0ebe-488d-b999-ba1df3548c39/scratchpad/h200_clip0.wav';
// A dubbing job that already exists in the capture data dir; the app restores its
// open dub from this draft key exactly as it does after a restart.
const DUB_JOB = { jobId: '5f15fb2c-91c2-4429-bf42-1afaba136067', filename: 'dialogue.mp4', duration: 74.28, segments: [] };

export default async function capture({ page, goto, shot, t, L }) {
  // A real transcript (Fast mode) so the Transcripts filter has an entry.
  await goto('/transcriptions');
  const main = page.locator('main[data-slot="workspace-content"]');
  const upload = main.getByRole('button', { name: L('clone.upload_audio') }).first();
  await page.waitForFunction((button) => !button.disabled, await upload.elementHandle(), { timeout: 60000 });
  await main.locator('input[type="file"]').setInputFiles(CLIP);
  await main.getByRole('button', { name: L('transcriptions.copy'), exact: true }).first().waitFor({ timeout: 300000 });

  // A story project, saved from the Stories workspace.
  await goto('/stories');
  const projectsPanel = page.locator('details:has(> summary)').filter({ hasText: L('stories.projectName') }).first();
  await projectsPanel.locator('summary').click();
  await projectsPanel.locator('input').fill(t({ en: 'Lighthouse story', th: 'เรื่องประภาคาร' }));
  await projectsPanel.getByRole('button', { name: L('clone.save'), exact: true }).click();
  await projectsPanel.locator('[role="status"]').waitFor({ timeout: 15000 });

  // An open dub: the Projects page offers to save it as a dubbing project.
  // Set before the app starts (it restores the dub session once, and saves it on unload).
  await page.context().addInitScript((draft) => localStorage.setItem('voicestudio.dub.session.v1', JSON.stringify(draft)), DUB_JOB);
  await goto('/projects');
  await page.reload({ waitUntil: 'networkidle' });
  const name = page.locator('#project-name');
  await name.waitFor({ timeout: 30000 });
  await name.fill(t({ en: 'Dialogue dub', th: 'พากย์บทสนทนา' }));
  const save = page.locator('form').getByRole('button', { name: L('clone.save'), exact: true });
  await shot('projects-save-dub', { marks: [name, save] });
  await save.click();
  await page.locator('form [role="status"]').waitFor({ timeout: 15000 });

  const sidebar = page.locator('main[data-slot="workspace-content"] aside').first();
  const search = page.getByPlaceholder(L('projects.search_placeholder'));
  const rows = page.locator('section article');
  await rows.first().waitFor({ timeout: 30000 });
  await shot('projects-library', {
    marks: [sidebar, search, page.locator('form').first(), rows.first()],
  });

  // Open the dubbing project: the row asks before replacing the current draft.
  await sidebar.getByRole('button', { name: L('projects.dub_projects') }).click();
  const dubRow = rows.filter({ hasText: t({ en: 'Dialogue dub', th: 'พากย์บทสนทนา' }) }).first();
  await dubRow.getByRole('button').filter({ hasText: t({ en: 'Dialogue dub', th: 'พากย์บทสนทนา' }) }).first().click();
  const confirmBar = dubRow.locator('.bg-muted\\/40');
  await confirmBar.waitFor({ timeout: 10000 });
  await shot('projects-open', {
    marks: [dubRow.getByRole('button').filter({ hasText: t({ en: 'Dialogue dub', th: 'พากย์บทสนทนา' }) }).first(),
      confirmBar.getByRole('button', { name: L('common.confirm') })],
  });
  await confirmBar.getByRole('button', { name: L('clone.cancel') }).click();

  // Story renders keep how they were made.
  await sidebar.getByRole('button', { name: L('nav.stories') }).click();
  const render = rows.filter({ has: page.locator('details') }).first();
  await render.locator('details summary').click();
  await page.waitForTimeout(400);
  await shot('projects-render', { marks: [rows.filter({ hasText: t({ en: 'Lighthouse story', th: 'เรื่องประภาคาร' }) }).first(), render.locator('details')] });

  // Delete asks first and says what is kept.
  await sidebar.getByRole('button', { name: L('projects.transcripts') }).click();
  const transcript = rows.first();
  await transcript.locator('input[type="checkbox"]').check();
  const deleteSelected = page.getByRole('button', { name: L.pattern('projects.delete_selected') }).first();
  await deleteSelected.click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor({ timeout: 10000 });
  await shot('projects-delete', { marks: [dialog] });
  await dialog.getByRole('button', { name: L('clone.cancel') }).click();
}
