import { renderHook, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useGlossaryCount } from './use-glossary-count';

const api = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api/client', () => ({ apiJson: api }));

it('loads the job glossary size before the panel opens', async () => {
  api.mockResolvedValue([{ id: 'a' }, { id: 'b' }]);
  const { result } = renderHook(() => useGlossaryCount('job/1'));
  await waitFor(() => expect(result.current[0]).toBe(2));
  expect(api).toHaveBeenCalledWith('/glossary/job%2F1', expect.objectContaining({ signal: expect.any(AbortSignal) }));
});

it('shows 0 without a job or when the count fails', async () => {
  api.mockReset();
  expect(renderHook(() => useGlossaryCount(null)).result.current[0]).toBe(0);
  expect(api).not.toHaveBeenCalled();
  api.mockRejectedValue(new Error('offline'));
  const { result } = renderHook(() => useGlossaryCount('job'));
  await waitFor(() => expect(api).toHaveBeenCalled());
  expect(result.current[0]).toBe(0);
});
