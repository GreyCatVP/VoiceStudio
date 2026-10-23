import { useEffect, useState } from 'react';
import { apiJson } from '@/lib/api/client';

/** The dub job's glossary size, known before the glossary panel is opened
 * (the panel reports changes through the returned setter). A failed count is 0. */
export function useGlossaryCount(jobId: string | null | undefined) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    setCount(0);
    if (!jobId) return;
    const controller = new AbortController();
    void apiJson<unknown[]>(`/glossary/${encodeURIComponent(jobId)}`, { signal: controller.signal })
      .then((terms) => {
        if (!controller.signal.aborted && Array.isArray(terms)) setCount(terms.length);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [jobId]);
  return [count, setCount] as const;
}
