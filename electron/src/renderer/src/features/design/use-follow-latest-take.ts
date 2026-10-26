import { useEffect, useRef } from 'react';
import type { HistoryItem } from '@/lib/api/types';
import { useHistory } from '@/hooks/use-history';
import { useLatestOutput } from '@/lib/store/output';
import { openTake, useSelectedTake } from '@/lib/store/takes';

/**
 * The take an open take pane should switch to once a new take of the same
 * kind is in the history, or null to leave it alone.
 */
export function nextOpenTake(
  open: HistoryItem | null,
  rendered: string | null,
  history: readonly HistoryItem[] | undefined,
): HistoryItem | null {
  if (!open || !rendered || open.id === rendered) return null;
  const take = history?.find((item) => item.id === rendered);
  return take && take.mode === open.mode ? take : null;
}

/**
 * Keeps the open take pane on the newest take. Without this the pane went on
 * showing the take it was opened on, so a new render beside it looked as if
 * it had used that old take's language and style.
 */
export function useFollowLatestTake() {
  const open = useSelectedTake();
  const latest = useLatestOutput().result?.id ?? null;
  const history = useHistory().data;
  // Only a render made while this page is mounted moves the pane: an output
  // left over from earlier must not replace a take the user just opened.
  const seen = useRef(latest);
  const pending = useRef<string | null>(null);
  useEffect(() => {
    if (latest !== seen.current) {
      seen.current = latest;
      pending.current = latest;
    }
    const next = nextOpenTake(open, pending.current, history);
    if (next) {
      pending.current = null;
      openTake(next);
    } else if (!open) pending.current = null;
  }, [latest, open, history]);
}
