import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';

const mock = vi.hoisted(() => ({ apiJson: vi.fn() }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
}));
vi.mock('@/lib/api/client', async (original) => ({
  ...(await original<typeof import('@/lib/api/client')>()),
  apiJson: mock.apiJson,
}));
vi.mock('./convert-voice', () => ({ ConvertVoice: () => null }));
vi.mock('@/components/app-shell/workspace-header', () => ({
  WorkspaceHeader: ({ children }: { children: ReactNode }) => <header>{children}</header>,
}));
vi.mock('@/components/workspace-sidebar', () => ({
  SecondarySidebar: ({ children }: { children: ReactNode }) => <nav>{children}</nav>,
}));
vi.mock('./compare-voices', () => ({ CompareVoices: () => null }));
vi.mock('@/features/clone/language-picker', () => ({ LanguagePicker: () => null }));

import { ToolsPage, toolErrorMessage } from './tools-page';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${String(options.message)}` : key;

it('maps every speech-rate and direction code to a translated message', () => {
  for (const [code, key] of [
    ['no-llm', 'tools.rate_fit_no_llm'],
    ['already-fits', 'tools.rate_fit_already_fits'],
    ['fit-skip-short', 'tools.rate_fit_skip_short'],
    ['fit-provider-failed', 'tools.rate_fit_provider_failed'],
    ['fit-unchanged', 'tools.rate_fit_unchanged'],
    ['fit-diverged', 'tools.rate_fit_diverged'],
    ['invalid-timing', 'tools.rate_fit_invalid_timing'],
    ['fit-budget', 'tools.rate_fit_budget'],
    ['llm-parse-failed', 'tools.direction_llm_parse_failed'],
    ['llm-invalid-json', 'tools.direction_llm_invalid_json'],
  ]) {
    expect(toolErrorMessage('rate-fit', code, t)).toBe(key);
  }
  expect(toolErrorMessage('rate-fit', 'new-code', t)).toBe('tools.fit_failed:new-code');
  expect(toolErrorMessage('probe', 'no such file', t)).toBe('tools.probe_failed:no such file');
});

it('shows a human message instead of the raw speech-rate fit code', async () => {
  mock.apiJson.mockResolvedValue({ text: 'Hello', rate_ratio: 1.4, attempts: 0, error: 'no-llm' });
  render(<ToolsPage />);
  fireEvent.click(screen.getByRole('button', { name: /tools.speech_rate_fit/ }));
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Hello' } });
  fireEvent.click(screen.getByRole('button', { name: 'tools.fit' }));
  expect((await screen.findAllByText('tools.rate_fit_no_llm')).length).toBeGreaterThan(0);
  expect(screen.queryByText('no-llm')).not.toBeInTheDocument();
});
