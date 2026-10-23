import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), save: vi.fn(), bridge: null as object | null }));
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<object>()),
  apiFetch: mock.fetch,
}));
vi.mock('@/components/bridge', () => ({ getBridge: () => mock.bridge }));
vi.mock('sonner', () => ({ toast: { success: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
import { PersonaExport, personaBundle } from './persona-export';
import { ApiError } from '@/lib/api/client';
import { setCloneSetting } from '@/lib/store/clone-settings';
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mock.bridge = null;
  setCloneSetting('personaIncludeReference', false);
});
const noAudio = () =>
  new ApiError(422, 'no audio', {
    detail: { code: 'persona_no_audio', message: 'x' },
  });
function open() {
  render(<PersonaExport profile={{ id: 'voice', name: 'Voice' }} />);
  fireEvent.click(screen.getByText('voice_profile.persona_export', { selector: 'summary' }));
}
const exportButton = () => screen.getByRole('button', { name: 'voice_profile.persona_export' });
it('starts without the reference clip by default (Settings default off)', async () => {
  mock.fetch.mockResolvedValue({ blob: async () => new Blob(['bundle']) });
  URL.createObjectURL = vi.fn(() => 'blob:x');
  open();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  fireEvent.click(exportButton());
  await waitFor(() =>
    expect(mock.fetch).toHaveBeenCalledWith('/personas/export/voice?include_reference=false', {
      method: 'POST',
    }),
  );
});
it('starts from the Settings preference and can be overridden for one export', async () => {
  setCloneSetting('personaIncludeReference', true);
  mock.fetch.mockResolvedValue({ blob: async () => new Blob(['bundle']) });
  URL.createObjectURL = vi.fn(() => 'blob:x');
  open();
  const check = screen.getByRole('checkbox');
  expect(check).toBeChecked();
  fireEvent.click(check);
  fireEvent.click(exportButton());
  await waitFor(() =>
    expect(mock.fetch).toHaveBeenCalledWith('/personas/export/voice?include_reference=false', {
      method: 'POST',
    }),
  );
  const { cloneSettingsStore } = await import('@/lib/store/clone-settings');
  expect(cloneSettingsStore.state.personaIncludeReference).toBe(true);
});
it('says the export failed, why, and what to do when there is no audio', async () => {
  mock.fetch.mockRejectedValue(noAudio());
  open();
  fireEvent.click(exportButton());
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('voice_profile.persona_export_failed');
  expect(alert).toHaveTextContent('voice_profile.persona_export_no_audio');
  expect(alert).toHaveTextContent('voice_profile.persona_export_no_audio_fix');
  expect(screen.queryByText('voice_profile.persona_exported')).toBeNull();
});
it('does not blame missing audio for unrelated failures', async () => {
  mock.fetch.mockRejectedValue(new ApiError(503, 'Could not build the persona bundle'));
  open();
  fireEvent.click(exportButton());
  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('voice_profile.persona_export_failed');
  expect(alert).toHaveTextContent('Could not build the persona bundle');
  expect(alert).not.toHaveTextContent('voice_profile.persona_export_no_audio');
});
it('sends the explicit reference choice and safely encodes profile identifiers', async () => {
  mock.fetch.mockResolvedValue({ blob: async () => new Blob(['bundle']) });
  await personaBundle('voice/id', false);
  expect(mock.fetch).toHaveBeenCalledWith('/personas/export/voice%2Fid?include_reference=false', {
    method: 'POST',
  });
});
it('keeps the reference opt-in state after an export fails and allows retry', async () => {
  mock.fetch.mockRejectedValue(noAudio());
  open();
  const check = screen.getByRole('checkbox');
  expect(check).not.toBeChecked();
  fireEvent.click(check);
  fireEvent.click(exportButton());
  await waitFor(() =>
    expect(screen.getByRole('alert')).toHaveTextContent('voice_profile.persona_export_no_audio'),
  );
  expect(check).toBeChecked();
  expect(screen.getByRole('button', { name: 'voice_profile.persona_export' })).not.toBeDisabled();
});
it('uses the native Save As path for persona bundles in Electron', async () => {
  mock.bridge = { files: { saveAudio: mock.save } };
  mock.save.mockResolvedValue({ canceled: false, path: 'C:\\Voice.ovsvoice' });
  setCloneSetting('personaIncludeReference', true);
  render(<PersonaExport profile={{ id: 'voice/id', name: 'Voice' }} />);
  fireEvent.click(screen.getByText('voice_profile.persona_export', { selector: 'summary' }));
  fireEvent.click(screen.getByRole('button', { name: 'voice_profile.persona_export' }));
  await waitFor(() =>
    expect(mock.save).toHaveBeenCalledWith({
      url: '/api/personas/export/voice%2Fid?include_reference=true',
      suggestedName: 'Voice.ovsvoice',
      method: 'POST',
    }),
  );
  expect(mock.fetch).not.toHaveBeenCalled();
});
