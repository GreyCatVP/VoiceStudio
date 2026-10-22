import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
const mock = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api/client', () => ({ apiJson: mock.api }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('./ray-settings', () => ({
  RaySettings: ({ initialProvider }: { initialProvider?: string }) => (
    <div>remote settings: {initialProvider}</div>
  ),
}));
import { GPU_CHOICE_KEY, SystemPreflight } from './system-preflight';
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
});
function mount(client = new QueryClient()) {
  render(
    <QueryClientProvider client={client}>
      <SystemPreflight />
    </QueryClientProvider>,
  );
}
it('runs only on explicit request and renders backend diagnostics and fixes', async () => {
  mock.api.mockResolvedValue({
    checks: [
      { id: 'ram', label: 'Memory', status: 'warn', detail: '8 GB', fix: 'Use a smaller model' },
    ],
  });
  mount();
  expect(mock.api).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  await screen.findByText('Use a smaller model');
  expect(mock.api).toHaveBeenCalledWith(
    '/setup/preflight',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'setup.recheck' }));
  await waitFor(() => expect(mock.api).toHaveBeenCalledTimes(2));
});
it('shows failure and permits an explicit retry without automatic probes', async () => {
  mock.api.mockRejectedValue(new Error('unreachable'));
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  await screen.findByRole('alert');
  expect(mock.api).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'setup.system_check' })).toBeEnabled();
});
it('renders the Windows-on-ARM notice from the translation catalog, not backend text', async () => {
  mock.api.mockResolvedValue({
    checks: [
      {
        id: 'arch',
        label: 'Windows on ARM',
        status: 'warn',
        detail: 'English detail',
        fix: 'English fix',
      },
    ],
  });
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  await screen.findByText('setup.check_arch_label');
  expect(screen.getByText('setup.check_arch_detail')).toBeTruthy();
  expect(screen.getByText('setup.check_arch_fix')).toBeTruthy();
  expect(screen.queryByText('English detail')).toBeNull();
});

const NO_GPU = {
  id: 'gpu',
  label: 'GPU acceleration',
  status: 'warn',
  detail: 'No GPU detected',
  fix: 'Use a small model',
  choices: ['cpu', 'ray', 'modal'],
};
it('offers CPU, Ray and Modal when there is no GPU, and remembers keeping the CPU', async () => {
  mock.api.mockResolvedValue({ checks: [NO_GPU] });
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  const group = await screen.findByRole('group', { name: 'setup.gpu_choice_label' });
  expect(group).toHaveTextContent('setup.gpu_choice_ray');
  expect(group).toHaveTextContent('setup.gpu_choice_modal');
  fireEvent.click(screen.getByRole('button', { name: 'setup.gpu_choice_cpu' }));
  expect(screen.getByText('setup.gpu_choice_using_cpu')).toBeTruthy();
  expect(screen.queryByRole('group', { name: 'setup.gpu_choice_label' })).toBeNull();
  expect(window.localStorage.getItem(GPU_CHOICE_KEY)).toBe('cpu');
  fireEvent.click(screen.getByRole('button', { name: 'setup.gpu_choice_change' }));
  expect(screen.getByRole('group', { name: 'setup.gpu_choice_label' })).toBeTruthy();
  expect(window.localStorage.getItem(GPU_CHOICE_KEY)).toBeNull();
});
it('starts collapsed when this viewer already chose the CPU', async () => {
  window.localStorage.setItem(GPU_CHOICE_KEY, 'cpu');
  mock.api.mockResolvedValue({ checks: [NO_GPU] });
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  await screen.findByText('setup.gpu_choice_using_cpu');
  expect(screen.queryByRole('button', { name: 'setup.gpu_choice_modal' })).toBeNull();
});
it('opens the remote settings for the chosen provider and re-probes after closing', async () => {
  mock.api.mockResolvedValue({ checks: [NO_GPU] });
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  mount(client);
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  fireEvent.click(await screen.findByRole('button', { name: 'setup.gpu_choice_modal' }));
  const dialog = await screen.findByRole('dialog');
  expect(dialog).toHaveTextContent('remote settings: modal');
  expect(dialog).toHaveTextContent('setup.gpu_choice_dialog_title');
  expect(mock.api).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(dialog, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  await waitFor(() => expect(mock.api).toHaveBeenCalledTimes(2));
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['ray-settings'] });

  fireEvent.click(await screen.findByRole('button', { name: 'setup.gpu_choice_ray' }));
  expect(await screen.findByRole('dialog')).toHaveTextContent('remote settings: ray');
});
it('describes active remote GPU work from the catalog instead of the backend text', async () => {
  mock.api.mockResolvedValue({
    checks: [
      {
        id: 'gpu',
        label: 'GPU acceleration',
        status: 'pass',
        detail: 'No local GPU — 4 engine(s) run on Modal (L4)',
        fix: null,
        remote: { provider: 'modal', gpu: 'L4', engines: 4 },
      },
    ],
  });
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'setup.system_check' }));
  await screen.findByText('setup.gpu_remote_modal');
  expect(screen.queryByText(/run on Modal/)).toBeNull();
  expect(screen.queryByRole('group', { name: 'setup.gpu_choice_label' })).toBeNull();
});
