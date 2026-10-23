import { cleanup, render, screen } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest';

const history = vi.hoisted(() =>
  Array.from({ length: 45 }, (_, i) => ({
    id: `take-${i}`,
    text: `Take number ${i}`,
    mode: 'clone',
    created_at: 1_700_000_000 + i,
    duration_seconds: 2,
  })),
);

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));
vi.mock('@/hooks/use-history', () => ({
  useHistory: () => ({ data: history, isPending: false, isError: false }),
  useDeleteHistoryItem: () => ({ mutate: vi.fn() }),
  useClearHistory: () => ({ mutateAsync: vi.fn() }),
  useToggleStarred: () => ({ mutate: vi.fn() }),
}));
vi.mock('@/hooks/use-profiles', () => ({
  useProfiles: () => ({ data: [] }),
  useDeleteProfile: () => ({ mutate: vi.fn() }),
}));
vi.mock('@/hooks/use-tts-readiness', () => ({ useTtsReadiness: () => null }));
vi.mock('@/lib/store/workspace', () => ({ setWorkspace: vi.fn() }));
vi.mock('@/lib/store/takes', () => ({
  openTake: vi.fn(),
  reuseTake: vi.fn(),
  useSelectedTake: () => null,
}));

import { VoicesSidebar } from './voices-sidebar';

// jsdom has no layout; give every element a real box so the virtualizer can size its viewport.
const offsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
const offsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 400 });
  Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 280 });
});
afterAll(() => {
  if (offsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', offsetHeight);
  if (offsetWidth) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', offsetWidth);
});
afterEach(cleanup);

it('renders a virtualized Recent takes list when it mounts with its data already cached', () => {
  // Switching the library tab remounts the sidebar with cached history, so the virtual
  // list mounts in the same commit as its scroll container.
  render(<VoicesSidebar initialTab="takes" />);
  expect(screen.getByText('Take number 0')).toBeInTheDocument();
});
