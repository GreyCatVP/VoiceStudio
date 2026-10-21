import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

import { RaySettings, type RayConfig } from './ray-settings';

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
    { id: 'voxcpm2', gpu: true },
    { id: 'supertonic3', gpu: false },
  ],
};

function renderSettings(
  overrides: Partial<RayConfig> = {},
  handlers: Record<string, (init?: RequestInit) => unknown> = {},
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
      <RaySettings />
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
  expect(mock.api).toHaveBeenCalledWith('/api/settings/ray/jobs', expect.anything());
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
  fireEvent.change(input('settings.ray_cf_client_secret'), { target: { value: 'cf-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'settings.ray_clear_token' }));
  fireEvent.click(screen.getAllByRole('button', { name: 'common.save' })[0]);

  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/ray', {
      method: 'PUT',
      body: JSON.stringify({ auth_token: '', cf_access_client_secret: 'cf-secret' }),
    }),
  );
  await waitFor(() => expect(input('settings.ray_cf_client_secret')).toHaveValue(''));
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
