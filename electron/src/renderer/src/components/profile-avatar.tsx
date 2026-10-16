import { useState } from 'react';
import { cn } from '@/lib/utils';
import { apiPath } from '@/lib/api/client';

// The first letter or digit of a word, so "(Crying)" gives "C" and separators like "·" give nothing.
const initialOf = (word: string) => Array.from(word).find((ch) => /[\p{L}\p{N}]/u.test(ch));

export function profileInitials(name: string): string {
  const letters = name
    .trim()
    .split(/\s+/)
    .map(initialOf)
    .filter((ch): ch is string => !!ch);
  return letters.length
    ? [letters[0], ...(letters.length > 1 ? [letters.at(-1)!] : [])].join('').toLocaleUpperCase()
    : '♪';
}

export function ProfileAvatar({
  name,
  imageUrl,
  className,
}: {
  name: string;
  imageUrl?: string | null;
  className?: string;
}) {
  const [failed, setFailed] = useState<string | null>(null);
  const src = imageUrl?.startsWith('/profiles/') ? apiPath(imageUrl) : imageUrl;
  return (
    <span
      aria-hidden="true"
      className={cn(
        'relative flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary/12 text-xs font-semibold text-primary ring-1 ring-foreground/15',
        className,
      )}
    >
      {src && failed !== src ? (
        <>
          <img src={src} alt="" className="size-full object-cover" onError={() => setFailed(src)} />
          <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent pt-2 pb-0.5 text-center text-[10px] leading-none font-semibold text-white">
            {profileInitials(name)}
          </span>
        </>
      ) : (
        profileInitials(name)
      )}
    </span>
  );
}
