// Saved voices named in "Group · Name" or "Prefix · Group · Name" form (e.g. "HI · Family · Didi")
// get a category from the name itself, so a large library can be filtered without extra metadata.
const SEPARATOR = /\s+·\s+/;

export function voiceCategory(name: string): string | null {
  const parts = name
    .split(SEPARATOR)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length >= 3) return parts[1]!;
  if (parts.length === 2) return parts[0]!;
  return null;
}

/** Categories present in `names`, A–Z with their counts; names without a category are skipped. */
export function voiceCategories(names: string[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const name of names) {
    const category = voiceCategory(name);
    if (category) counts.set(category, (counts.get(category) ?? 0) + 1);
  }
  return [...counts]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
