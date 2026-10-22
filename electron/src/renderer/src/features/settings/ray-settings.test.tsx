import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({ api: vi.fn(), success: vi.fn(), error: vi.fn(), info: vi.fn() }));

vi.mock('@/lib/api/client', async (load) => {
  const actual = await load<typeof import('@/lib/api/client')>();
  return { ...actual, apiJson: mock.api };
});
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactNode }) => <a href="#">{children}</a>,
}));
vi.mock('sonner', () => ({ toast: { success: mock.success, error: mock.error, info: mock.info } }));

import { RaySettings, rayChanges, type RayConfig, type RayEngineKind } from './ray-settings';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const BASE: RayConfig = {
  enabled: true,
  dashboard_url: 'https://ray.example.com',
  cf_access_client_id: '',
  engines: ['voxcpm2'],
  num_gpus: 1,
  num_cpus: 2,
  cache_dir: '',
  python: 'python3',
  keep_failed_jobs: false,
  has_token: true,
  has_cf_secret: false,
  env_pinned: [],
  available_engines: [
    { id: 'voxcpm2', gpu: true, kind: 'tts' },
    { id: 'supertonic3', gpu: false, kind: 'tts' },
  ],
};

function renderSettings(
  overrides: Partial<RayConfig> = {},
  handlers: Record<string, (init?: RequestInit) => unknown> = {},
  props: Parameters<typeof RaySettings>[0] = {},
) {
  const config = { ...BASE, ...overrides };
  mock.api.mockImplementation((path: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    const handler = handlers[`${method} ${path}`];
    if (handler) return Promise.resolve(handler(init));
    if (path === '/api/settings/ray' && method === 'GET') return Promise.resolve(config);
    if (path === '/api/settings/ray' && method === 'PUT')
      return Promise.resolve({ ...config, ...JSON.parse(String(init?.body)) });
    if (path === '/api/settings/ray/jobs') return Promise.resolve({ ok: true, jobs: [] });
    return Promise.resolve({ ok: true });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RaySettings {...props} />
    </QueryClientProvider>,
  );
}

const input = (label: string) =>
  document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;

it('loads and renders the saved state', async () => {
  renderSettings();
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  expect(input('settings.ray_token')).toHaveValue('');
  expect(input('settings.ray_token')).toHaveAttribute('placeholder', '••••••••');
  expect(input('settings.ray_python')).toHaveValue('python3');
  expect(screen.getByRole('switch', { name: 'settings.ray_enabled' })).toBeChecked();
  const boxes = screen.getAllByRole('checkbox');
  expect(boxes).toHaveLength(2);
  expect(boxes[0]).toBeChecked();
  expect(boxes[1]).not.toBeChecked();
  expect(screen.getByText('supertonic3')).toBeInTheDocument();
  expect(screen.getByText('settings.ray_badge_cpu')).toBeInTheDocument();
  // The jobs query starts once the settings have loaded: wait for it.
  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray/jobs', expect.anything()),
  );
});

it('groups engines into text to speech and speech recognition', async () => {
  renderSettings({
    engines: ['voxcpm2', 'faster-whisper-isolated'],
    available_engines: [
      { id: 'voxcpm2', gpu: true, kind: 'tts' },
      { id: 'supertonic3', gpu: false, kind: 'tts' },
      { id: 'faster-whisper-isolated', gpu: true, kind: 'asr' },
      // Older backends omit `kind`; those engines count as text to speech.
      { id: 'cosyvoice', gpu: true },
    ],
  });
  const tts = await screen.findByRole('group', { name: 'settings.ray_engines_group_tts' });
  const asr = screen.getByRole('group', { name: 'settings.ray_engines_group_asr' });

  const ids = (group: HTMLElement) =>
    within(group)
      .getAllByRole('checkbox')
      .map((box) => box.closest('label')?.querySelector('.font-mono')?.textContent);
  expect(ids(tts)).toEqual(['voxcpm2', 'supertonic3', 'cosyvoice']);
  expect(ids(asr)).toEqual(['faster-whisper-isolated']);
  expect(within(asr).getByRole('checkbox')).toBeChecked();
  expect(within(asr).getByText('settings.ray_badge_gpu')).toBeInTheDocument();
  expect(within(asr).getByText('settings.ray_engines_asr_hint')).toBeInTheDocument();
  expect(asr).toHaveAccessibleDescription('settings.ray_engines_asr_hint');
  expect(within(tts).queryByText('settings.ray_engines_asr_hint')).toBeNull();

  fireEvent.click(within(asr).getByRole('checkbox'));
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);
  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray', {
      method: 'PUT',
      body: JSON.stringify({ engines: ['voxcpm2'] }),
    }),
  );
});

it('puts translation, diarization and separation engines in their own groups', async () => {
  renderSettings({
    engines: ['pyannote'],
    available_engines: [
      { id: 'omnivoice', gpu: true, kind: 'tts' },
      { id: 'faster-whisper-isolated', gpu: true, kind: 'asr' },
      { id: 'nllb', gpu: true, kind: 'translation' },
      { id: 'pyannote', gpu: true, kind: 'diarization' },
      { id: 'demucs', gpu: true, kind: 'separation' },
      // A kind this build does not know yet still counts as text to speech.
      { id: 'future-engine', gpu: false, kind: 'something-new' as RayEngineKind },
    ],
  });
  await screen.findByRole('group', { name: 'settings.ray_engines_group_tts' });

  const ids = (group: HTMLElement) =>
    within(group)
      .getAllByRole('checkbox')
      .map((box) => box.closest('label')?.querySelector('.font-mono')?.textContent);
  // Settings rows are groups too; keep only the per-kind engine groups, in page order.
  const groups = screen
    .getAllByRole('group')
    .filter((group) => group.getAttribute('aria-labelledby')?.startsWith('ray-engines-'));
  expect(groups.map((group) => group.getAttribute('aria-labelledby'))).toEqual([
    'ray-engines-tts',
    'ray-engines-asr',
    'ray-engines-translation',
    'ray-engines-diarization',
    'ray-engines-separation',
  ]);
  const [tts, , translation, diarization, separation] = groups;
  expect(ids(tts)).toEqual(['omnivoice', 'future-engine']);
  expect(tts).not.toHaveAttribute('aria-describedby');
  for (const [group, kind, id] of [
    [translation, 'translation', 'nllb'],
    [diarization, 'diarization', 'pyannote'],
    [separation, 'separation', 'demucs'],
  ] as const) {
    expect(group).toHaveAccessibleName(`settings.ray_engines_group_${kind}`);
    expect(ids(group)).toEqual([id]);
    expect(group).toHaveAccessibleDescription(`settings.ray_engines_${kind}_hint`);
  }
  expect(within(diarization).getByRole('checkbox')).toBeChecked();
  expect(within(separation).getByRole('checkbox')).not.toBeChecked();
});

it('hides the text-to-speech group when only speech recognition engines exist', async () => {
  renderSettings({
    engines: [],
    available_engines: [{ id: 'faster-whisper-isolated', gpu: true, kind: 'asr' }],
  });
  const asr = await screen.findByRole('group', { name: 'settings.ray_engines_group_asr' });
  expect(within(asr).getAllByRole('checkbox')).toHaveLength(1);
  expect(screen.queryByRole('group', { name: 'settings.ray_engines_group_tts' })).toBeNull();
  expect(screen.queryByText('settings.ray_engines_group_tts')).toBeNull();
  expect(screen.queryByText('settings.ray_engines_none')).toBeNull();
});

it('hides the speech recognition group when no such engine is available', async () => {
  renderSettings();
  await screen.findByRole('group', { name: 'settings.ray_engines_group_tts' });
  expect(screen.queryByRole('group', { name: 'settings.ray_engines_group_asr' })).toBeNull();
  expect(screen.queryByText('settings.ray_engines_asr_hint')).toBeNull();
});

it('saves only the changed fields and never sends empty secrets', async () => {
  renderSettings();
  await waitFor(() => expect(input('settings.ray_python')).toHaveValue('python3'));

  fireEvent.change(input('settings.ray_python'), { target: { value: 'python3.11' } });
  fireEvent.click(screen.getAllByRole('checkbox')[1]);
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);

  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray', {
      method: 'PUT',
      body: JSON.stringify({ engines: ['voxcpm2', 'supertonic3'], python: 'python3.11' }),
    }),
  );
  expect(await screen.findByRole('status')).toHaveTextContent('settings.ray_saved');
});

it('sends a typed secret once, and an explicit clear as an empty string', async () => {
  renderSettings();
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  fireEvent.click(screen.getByRole('switch', { name: 'settings.ray_use_cf' }));
  fireEvent.change(input('settings.ray_cf_client_secret'), { target: { value: 'cf-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'settings.ray_clear_token' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);

  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray', {
      method: 'PUT',
      body: JSON.stringify({ auth_token: '', cf_access_client_secret: 'cf-secret' }),
    }),
  );
  // The typed secret is not kept (the field is empty, or hidden with its method off).
  await waitFor(() => expect(input('settings.ray_cf_client_secret')?.value ?? '').toBe(''));
});

it('shows the auth-disabled warning and node details from a test result', async () => {
  renderSettings(
    {},
    {
      'POST /api/settings/ray/test': () => ({
        ok: true,
        kind: 'ok',
        warnings: ['cluster_auth_disabled'],
        ray_version: '2.49.0',
        cluster_python: '3.11.9',
        node: {
          cache_dir: '/mnt/cache',
          cache_free_gb: 120.5,
          gpus: [{ name: 'L4', total_mb: 23034, used_mb: 0, free_mb: 23034 }],
        },
      }),
    },
  );
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  fireEvent.click(screen.getByRole('button', { name: 'settings.ray_test' }));

  expect(await screen.findByText('settings.ray_auth_disabled_title')).toBeInTheDocument();
  expect(screen.getByText('settings.ray_auth_disabled_body')).toBeInTheDocument();
  expect(screen.getByText('settings.ray_kind_ok')).toBeInTheDocument();
  expect(screen.getByText('2.49.0')).toBeInTheDocument();
  expect(screen.getByText('settings.ray_info_gpu_free')).toBeInTheDocument();
  expect(mock.api).toHaveBeenCalledWith('/api/settings/ray/test', { method: 'POST' });
  expect(mock.api).not.toHaveBeenCalledWith(
    '/api/settings/ray',
    expect.objectContaining({ method: 'PUT' }),
  );
});

it('reports a failed test request as a test result, not a save failure', async () => {
  renderSettings({}, { 'POST /api/settings/ray/test': () => Promise.reject(new Error('HTTP 403')) });
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  fireEvent.click(screen.getByRole('button', { name: 'settings.ray_test' }));

  expect(await screen.findByText(/HTTP 403/)).toBeInTheDocument();
  expect(screen.queryByText('settings.ray_save_failed')).not.toBeInTheDocument();
});

it('shows each auth method\'s fields only when it is switched on', async () => {
  renderSettings({ has_token: false });
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  // A cluster without auth needs no credentials, so none are asked for.
  expect(input('settings.ray_token')).toBeNull();
  expect(input('settings.ray_cf_client_id')).toBeNull();
  fireEvent.click(screen.getByRole('switch', { name: 'settings.ray_use_token' }));
  expect(input('settings.ray_token')).not.toBeNull();
  fireEvent.click(screen.getByRole('switch', { name: 'settings.ray_use_cf' }));
  expect(input('settings.ray_cf_client_id')).not.toBeNull();
  expect(input('settings.ray_cf_client_secret')).not.toBeNull();
});

it('turning an auth method off clears its stored credentials on save', async () => {
  renderSettings({ cf_access_client_id: 'cf-id', has_cf_secret: true });
  // Stored credentials switch their method on.
  await waitFor(() => expect(input('settings.ray_token')).not.toBeNull());
  expect(input('settings.ray_cf_client_id')).toHaveValue('cf-id');
  fireEvent.click(screen.getByRole('switch', { name: 'settings.ray_use_token' }));
  fireEvent.click(screen.getByRole('switch', { name: 'settings.ray_use_cf' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);

  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray', {
      method: 'PUT',
      body: JSON.stringify({ cf_access_client_id: '', auth_token: '', cf_access_client_secret: '' }),
    }),
  );
});

const RUNNING_JOBS = {
  'GET /api/settings/ray/jobs': () => ({
    ok: true,
    jobs: [
      {
        submission_id: 'vs-run-1',
        status: 'RUNNING',
        engine: 'voxcpm2',
        op: 'generate',
        start_time: 1_760_000_000_000,
        end_time: null,
        message: '',
      },
    ],
  }),
};

it('does not test the connection while changes are unsaved', async () => {
  renderSettings();
  await waitFor(() => expect(input('settings.ray_python')).toHaveValue('python3'));
  fireEvent.click(screen.getByRole('switch', { name: 'settings.ray_enabled' }));

  expect(screen.getByRole('button', { name: 'settings.ray_test' })).toBeDisabled();
  expect(screen.getByText('settings.ray_test_save_first')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'settings.ray_test' }));
  expect(mock.api).not.toHaveBeenCalledWith('/api/settings/ray/test', expect.anything());
  expect(mock.api).not.toHaveBeenCalledWith(
    '/api/settings/ray',
    expect.objectContaining({ method: 'PUT' }),
  );
});

it('shows a Ray-specific error title when the settings fail to load', async () => {
  mock.api.mockRejectedValue(new Error('boom'));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RaySettings />
    </QueryClientProvider>,
  );
  expect(await screen.findByText('settings.ray_load_failed')).toBeInTheDocument();
});

it('reports a job that already finished instead of claiming the stop was requested', async () => {
  renderSettings(
    {},
    {
      ...RUNNING_JOBS,
      'POST /api/settings/ray/jobs/vs-run-1/stop': () => ({ ok: true, stopped: false }),
    },
  );
  fireEvent.click(await screen.findByRole('button', { name: 'settings.ray_job_stop' }));
  await waitFor(() => expect(mock.info).toHaveBeenCalledWith('settings.ray_job_not_running'));
  expect(mock.success).not.toHaveBeenCalled();
});

it('stops a running job through the stop endpoint', async () => {
  renderSettings(
    {},
    {
      'GET /api/settings/ray/jobs': () => ({
        ok: true,
        jobs: [
          {
            submission_id: 'vs-run-1',
            status: 'RUNNING',
            engine: 'voxcpm2',
            op: 'generate',
            start_time: 1_760_000_000_000,
            end_time: null,
            message: '',
          },
          {
            submission_id: 'vs-done-2',
            status: 'SUCCEEDED',
            engine: 'voxcpm2',
            op: 'generate',
            start_time: 1_760_000_000_000,
            end_time: 1_760_000_100_000,
            message: 'done',
          },
        ],
      }),
      'POST /api/settings/ray/jobs/vs-run-1/stop': () => ({ ok: true, stopped: true }),
    },
  );

  const stop = await screen.findByRole('button', { name: 'settings.ray_job_stop' });
  expect(screen.getAllByRole('button', { name: 'settings.ray_job_stop' })).toHaveLength(1);
  fireEvent.click(stop);

  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray/jobs/vs-run-1/stop', {
      method: 'POST',
    }),
  );
  await waitFor(() => expect(mock.success).toHaveBeenCalledWith('settings.ray_job_stop_requested'));
});

it('marks environment-pinned fields read-only and does not poll jobs when disabled', async () => {
  renderSettings({ enabled: false, env_pinned: ['dashboard_url', 'token'] });
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveAttribute('readonly'));
  expect(input('settings.ray_token')).toHaveAttribute('readonly');
  expect(screen.getAllByText('settings.ray_env_pinned')).toHaveLength(2);
  expect(screen.queryByRole('button', { name: 'settings.ray_clear_token' })).toBeNull();
  expect(screen.getByText('settings.ray_jobs_disabled')).toBeInTheDocument();
  expect(mock.api).not.toHaveBeenCalledWith('/api/settings/ray/jobs', expect.anything());
});

const MODAL: Partial<RayConfig> = {
  provider: 'modal',
  modal_gpu: 'L4',
  modal_gpus: ['T4', 'L4', 'H100'],
  modal_app: 'voicestudio',
  modal_volume: 'voicestudio-cache',
  has_modal_token: false,
};

const lastPut = () => {
  const call = mock.api.mock.calls.find(([, init]) => init?.method === 'PUT');
  return call ? JSON.parse(String(call[1].body)) : undefined;
};

it('switching to Modal shows Modal rows and hides the Ray-only rows and jobs', async () => {
  renderSettings({ ...MODAL, provider: 'ray' });
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  expect(screen.getByText('settings.ray_jobs_title')).toBeInTheDocument();
  expect(input('settings.modal_token_id')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'settings.remote_provider_modal' }));

  expect(input('settings.ray_dashboard_url')).toBeNull();
  expect(input('settings.ray_token')).toBeNull();
  expect(input('settings.ray_num_gpus')).toBeNull();
  expect(input('settings.ray_cache_dir')).toBeNull();
  expect(screen.queryByText('settings.ray_jobs_title')).toBeNull();
  expect(input('settings.modal_token_id')).toBeInTheDocument();
  expect(input('settings.modal_token_secret')).toBeInTheDocument();
  expect(input('settings.modal_app')).toHaveValue('voicestudio');
  expect(input('settings.modal_volume')).toHaveValue('voicestudio-cache');
  expect(input('settings.ray_num_cpus')).toHaveValue(2);
  expect(screen.getByText('settings.modal_privacy_body')).toBeInTheDocument();
  expect(screen.getByRole('switch', { name: 'settings.modal_enabled' })).toBeChecked();

  fireEvent.click(screen.getByRole('button', { name: 'settings.remote_provider_ray' }));
  expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url);
  expect(input('settings.modal_token_id')).toBeNull();
});

it('saves the provider and typed Modal credentials', async () => {
  renderSettings({ ...MODAL, provider: 'ray' });
  await waitFor(() => expect(input('settings.ray_dashboard_url')).toHaveValue(BASE.dashboard_url));
  fireEvent.click(screen.getByRole('button', { name: 'settings.remote_provider_modal' }));
  fireEvent.change(input('settings.modal_token_id'), { target: { value: 'ak-123' } });
  fireEvent.change(input('settings.modal_token_secret'), { target: { value: 'as-456' } });
  fireEvent.change(input('settings.modal_app'), { target: { value: ' my-app ' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);

  await waitFor(() =>
    expect(lastPut()).toEqual({
      provider: 'modal',
      modal_app: 'my-app',
      modal_token_id: 'ak-123',
      modal_token_secret: 'as-456',
    }),
  );
});

it('computes Modal changes, including the CPU-only GPU and a token clear', () => {
  const config = { ...BASE, ...MODAL, has_modal_token: true } as RayConfig;
  const draft = {
    enabled: true,
    dashboardUrl: BASE.dashboard_url,
    cfClientId: '',
    engines: ['voxcpm2'],
    numGpus: '1',
    numCpus: '2',
    cacheDir: '',
    python: 'python3',
    keepFailed: false,
    token: '',
    cfSecret: '',
    clearToken: false,
    clearCfSecret: false,
    useToken: true,
    useCfAccess: false,
    provider: 'modal' as const,
    modalGpu: '',
    modalApp: 'voicestudio',
    modalVolume: 'shared-cache',
    modalTokenId: '',
    modalTokenSecret: '',
    clearModalToken: true,
  };
  expect(rayChanges(config, draft)).toEqual({
    modal_gpu: '',
    modal_volume: 'shared-cache',
    modal_token_id: '',
    modal_token_secret: '',
  });
  // Older backends without the Modal fields see no Modal changes from an untouched draft.
  const legacy = { ...BASE };
  expect(
    rayChanges(legacy, {
      ...draft,
      provider: 'ray',
      modalApp: '',
      modalVolume: '',
      clearModalToken: false,
    }),
  ).toEqual({});
});

it('never prefills a stored Modal token and clears typed secrets after saving', async () => {
  renderSettings({ ...MODAL, enabled: true, has_modal_token: true });
  await waitFor(() => expect(input('settings.modal_token_id')).toBeInTheDocument());
  for (const label of ['settings.modal_token_id', 'settings.modal_token_secret']) {
    expect(input(label)).toHaveValue('');
    expect(input(label)).toHaveAttribute('type', 'password');
    expect(input(label)).toHaveAttribute('placeholder', '••••••••');
  }
  expect(screen.getAllByText('settings.modal_token_stored')).toHaveLength(2);

  fireEvent.change(input('settings.modal_token_secret'), { target: { value: 'as-new' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);
  await waitFor(() => expect(lastPut()).toEqual({ modal_token_secret: 'as-new' }));
  await waitFor(() => expect(input('settings.modal_token_secret')).toHaveValue(''));

  fireEvent.click(screen.getByRole('button', { name: 'settings.modal_clear_token' }));
  expect(screen.getAllByText('settings.ray_secret_will_clear')).toHaveLength(2);
});

it('hides the jobs panel and never polls jobs for an enabled Modal provider', async () => {
  renderSettings({ ...MODAL, enabled: true });
  await waitFor(() => expect(input('settings.modal_token_id')).toBeInTheDocument());
  expect(screen.queryByText('settings.ray_jobs_title')).toBeNull();
  expect(screen.queryByText('settings.ray_jobs')).toBeNull();
  expect(mock.api).not.toHaveBeenCalledWith('/api/settings/ray/jobs', expect.anything());
});

it('preselects the initial provider as an unsaved change', async () => {
  renderSettings({ ...MODAL, provider: 'ray', enabled: false }, {}, { initialProvider: 'modal' });
  await waitFor(() => expect(input('settings.modal_token_id')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'settings.remote_provider_modal' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(mock.api).not.toHaveBeenCalledWith(
    '/api/settings/ray',
    expect.objectContaining({ method: 'PUT' }),
  );
  fireEvent.click(screen.getByRole('switch', { name: 'settings.modal_enabled' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);
  await waitFor(() => expect(lastPut()).toEqual({ provider: 'modal', enabled: true }));
});
