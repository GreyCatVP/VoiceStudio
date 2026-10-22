// Chapter "transcribe": file transcription for real, plus the dictation and ASR settings.
const CLIP = '/tmp/claude-0/-root-voicestudio/a001375f-0ebe-488d-b999-ba1df3548c39/scratchpad/h200_clip0.wav';

export default async function capture({ page, goto, shot, t, L }) {
  await goto('/transcriptions');
  const main = page.locator('main[data-slot="workspace-content"]');
  const modes = main.locator('[role="group"]').first();
  const fast = main.getByRole('button', { name: L('transcriptions.mode_fast'), exact: true });
  const upload = main.getByRole('button', { name: L('clone.upload_audio') }).first();
  await upload.waitFor({ timeout: 30000 });
  await page.waitForFunction((button) => !button.disabled, await upload.elementHandle(), { timeout: 60000 });
  await shot('transcribe-start', {
    marks: [modes, fast.locator('xpath=../following-sibling::span[1]'), upload,
      main.getByRole('button', { name: L('clone.record'), exact: true }).first()],
  });

  // A real transcription of the sample clip, through the page's own file input.
  await main.locator('input[type="file"]').setInputFiles(CLIP);
  const copy = main.getByRole('button', { name: L('transcriptions.copy'), exact: true }).first();
  await copy.waitFor({ timeout: 300000 });
  const entry = page.locator('button[aria-pressed="true"]').filter({ hasText: /\S/ }).first();
  await shot('transcribe-result', {
    marks: [entry, main.locator('article p.text-base').first(), copy,
      main.getByRole('button', { name: L('transcriptions.export'), exact: true }).first(),
      main.getByRole('button', { name: L('clone.history_reuse') })],
  });

  const segments = main.locator('article details summary').last();
  await segments.click();
  await shot('transcribe-segments', {
    marks: [main.locator('article details').last(), main.locator('div.border-t').last()],
  });

  const exportAll = page.getByRole('button', { name: L('transcriptions.export_title') });
  await shot('transcribe-verify', {
    marks: [entry, main.locator('article p.text-base').first(), exportAll],
  });

  await goto('/settings/models/asr');
  // The active engine is the row that names its model (e.g. Systran/faster-whisper-large-v3).
  const active = page.locator('[data-slot="settings-row"]').filter({ hasText: /\b[\w-]+\/[\w.-]*whisper/i }).first();
  await active.waitFor({ timeout: 30000 });
  await shot('transcribe-asr-settings', { marks: [active] });

  await goto('/settings/models/dictation');
  const mode = page.locator('[data-slot="settings-row"]:has(#dictation-mode)').first();
  await mode.scrollIntoViewIfNeeded();
  await shot('transcribe-dictation-settings', {
    marks: [mode,
      page.locator('[data-slot="settings-row"]:has(#dictation-prompt)').first()],
  });
}
