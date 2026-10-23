import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({ api: vi.fn() }));

vi.mock('@/lib/api/client', async (load) => {
  const actual = await load<typeof import('@/lib/api/client')>();
  return { ...actual, apiJson: mock.api };
});
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { CredentialSettings } from './credential-settings';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const BAO = {
  enabled: false,
  addr: 'http://127.0.0.1:8200',
  mount: 'secret',
  path: '',
  field: 'token',
  has_token: false,
  env_pinned: [] as string[],
};

function renderSettings(
  bao = BAO,
  test: Record<string, unknown> = {
    ok: true,
    kind: 'ok',
    masked: 'hf_…XYZ',
    ttl: 7200,
  },
  sources: unknown[] = [],
) {
  let saved = { ...bao };
  mock.api.mockImplementation((path: string, init?: RequestInit) => {
    if (path === '/api/settings/hf-token/state') return Promise.resolve({ active: null, sources });
    if (path === '/api/settings/openbao') {
      if (init?.method === 'PUT') {
        const body = JSON.parse(String(init.body));
        // Mirrors the backend: the token is write-only, only has_token comes back.
        const { token, ...rest } = body;
        saved = {
          ...saved,
          ...rest,
          has_token: token === undefined ? saved.has_token : !!token,
        };
      }
      return Promise.resolve(saved);
    }
    if (path === '/api/settings/openbao/test') return Promise.resolve(test);
    return Promise.resolve({ ok: true });
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <CredentialSettings />
    </QueryClientProvider>,
  );
  return client;
}

it('stores DeepL and Microsoft credentials only after an explicit save', async () => {
  const client = renderSettings();
  const invalidate = vi.spyOn(client, 'invalidateQueries');

  const deepL = document.querySelector<HTMLInputElement>(
    'input[aria-label="credentials.deepl_key"]',
  )!;
  const microsoft = document.querySelector<HTMLInputElement>(
    'input[aria-label="credentials.microsoft_base_url"]',
  )!;
  expect(mock.api).not.toHaveBeenCalledWith('/system/set-env', expect.anything());

  fireEvent.change(deepL, { target: { value: '  deepl-secret  ' } });
  fireEvent.click(within(deepL.closest('form')!).getByRole('button', { name: 'common.save' }));
  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/system/set-env', {
      method: 'POST',
      body: JSON.stringify({ key: 'DEEPL_API_KEY', value: 'deepl-secret' }),
    }),
  );

  fireEvent.change(microsoft, {
    target: { value: '  https://translator.example  ' },
  });
  fireEvent.click(
    within(microsoft.closest('form')!).getByRole('button', {
      name: 'common.save',
    }),
  );
  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/system/set-env', {
      method: 'POST',
      body: JSON.stringify({
        key: 'MICROSOFT_BASE_URL',
        value: 'https://translator.example',
      }),
    }),
  );
  expect(invalidate).toHaveBeenCalledWith({
    queryKey: ['translation-engines'],
  });
});

it('turns the OpenBao source on only when the user flips it', async () => {
  renderSettings();
  const toggle = await screen.findByRole('switch', {
    name: 'settings.openbao_enabled',
  });
  expect(mock.api).not.toHaveBeenCalledWith('/api/settings/openbao/test', expect.anything());
  expect(mock.api).not.toHaveBeenCalledWith(
    '/api/settings/openbao',
    expect.objectContaining({ method: 'PUT' }),
  );
  fireEvent.click(toggle);
  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/openbao', {
      method: 'PUT',
      body: JSON.stringify({ enabled: true }),
    }),
  );
});

it('sends the OpenBao token write-only and shows only the masked test result', async () => {
  renderSettings({ ...BAO, enabled: true });
  const token = (await screen.findByLabelText('settings.openbao_token', {
    selector: 'input',
  })) as HTMLInputElement;
  expect(token.type).toBe('password');
  const path = document.querySelector<HTMLInputElement>(
    'input[aria-label="settings.openbao_path"]',
  )!;
  fireEvent.change(path, { target: { value: 'voicestudio/hf' } });
  fireEvent.change(token, { target: { value: ' s.secret-bao ' } });
  fireEvent.click(screen.getByRole('button', { name: 'settings.openbao_test' }));
  await waitFor(() =>
    expect(mock.api).toHaveBeenCalledWith('/api/settings/openbao', {
      method: 'PUT',
      body: JSON.stringify({
        addr: 'http://127.0.0.1:8200',
        mount: 'secret',
        path: 'voicestudio/hf',
        field: 'token',
        token: 's.secret-bao',
      }),
    }),
  );
  await waitFor(() => expect(document.body.textContent).toContain('settings.openbao_test_ok'));
  expect(mock.api).toHaveBeenCalledWith('/api/settings/openbao/test', {
    method: 'POST',
  });
  expect(token.value).toBe('');
  expect(document.body.textContent).toContain('settings.openbao_token_saved');
  expect(document.body.innerHTML).not.toContain('s.secret-bao');
});

it('reports a sealed OpenBao and a failed source row clearly', async () => {
  renderSettings(
    { ...BAO, enabled: true, path: 'voicestudio/hf', has_token: true },
    { ok: false, kind: 'sealed' },
    [
      {
        source: 'openbao',
        set: false,
        masked: null,
        whoami_ok: false,
        error: 'denied',
      },
    ],
  );
  await waitFor(() => expect(document.body.textContent).toContain('settings.openbao_error_denied'));
  fireEvent.click(screen.getByRole('button', { name: 'settings.openbao_test' }));
  await waitFor(() => expect(document.body.textContent).toContain('settings.openbao_error_sealed'));
});

it('locks OpenBao fields pinned by environment variables', async () => {
  renderSettings({ ...BAO, env_pinned: ['addr', 'token'] });
  const addr = (await screen.findByLabelText('settings.openbao_addr', {
    selector: 'input',
  })) as HTMLInputElement;
  expect(addr.disabled).toBe(true);
  expect(
    document.querySelector<HTMLInputElement>('input[aria-label="settings.openbao_token"]')!
      .disabled,
  ).toBe(true);
});
