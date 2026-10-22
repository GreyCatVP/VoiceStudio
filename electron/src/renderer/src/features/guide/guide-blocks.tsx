import { Fragment, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CircleCheckIcon,
  ImageOffIcon,
  InfoIcon,
  LightbulbIcon,
  ListChecksIcon,
  TriangleAlertIcon,
} from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { DIAGRAMS } from './diagrams/specs';
import { FlowDiagram } from './diagrams/flow-diagram';
import { shotUrl } from './guide-content';
import type { GuideBlock, GuideLanguage, GuideStep } from './guide-types';

/** **bold** and `code`; everything else is plain text. */
export function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return (
    <>
      {parts.map((part, index) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={index} className="font-semibold text-foreground">
            {part.slice(2, -2)}
          </strong>
        ) : part.startsWith('`') && part.endsWith('`') ? (
          <code key={index} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
            {part.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function Screenshot({ language, id, caption }: { language: GuideLanguage; id: string; caption: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const url = shotUrl(language, id);
  if (!url) {
    return (
      <figure className="flex items-center gap-2 rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
        <ImageOffIcon className="size-4 shrink-0" aria-hidden="true" />
        {t('guide.missing_shot')} — {caption}
      </figure>
    );
  }
  return (
    <figure className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="block w-full cursor-zoom-in overflow-hidden rounded-lg border border-border/70 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t('guide.enlarge', { caption })}
      >
        <img src={url} alt={caption} loading="lazy" className="block h-auto w-full" />
      </button>
      <figcaption className="text-xs text-muted-foreground">
        <Inline text={caption} />
      </figcaption>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-auto p-2 sm:max-w-[min(1400px,calc(100%-2rem))]">
          <DialogTitle className="sr-only">{caption}</DialogTitle>
          <img src={url} alt={caption} className="h-auto w-full rounded-md" />
        </DialogContent>
      </Dialog>
    </figure>
  );
}

function Diagram({ id, text, caption }: { id: string; text: Record<string, string>; caption: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const spec = DIAGRAMS[id];
  if (!spec) return null;
  return (
    <figure className="space-y-2 rounded-xl border border-border/70 bg-background p-3">
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="block w-full cursor-zoom-in rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t('guide.enlarge', { caption })}
      >
        <FlowDiagram spec={spec} text={text} label={caption} />
      </button>
      <figcaption className="text-xs text-muted-foreground">
        <Inline text={caption} />
      </figcaption>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-auto bg-background p-4 sm:max-w-[min(1400px,calc(100%-2rem))]">
          <DialogTitle className="sr-only">{caption}</DialogTitle>
          <FlowDiagram spec={spec} text={text} label={caption} />
        </DialogContent>
      </Dialog>
    </figure>
  );
}

function Steps({ language, items }: { language: GuideLanguage; items: GuideStep[] }) {
  const { t } = useTranslation();
  return (
    <ol className="space-y-5">
      {items.map((step, index) => (
        <li key={index} className="grid grid-cols-[2rem_1fr] gap-3">
          <span
            aria-hidden="true"
            className="flex size-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
          >
            {index + 1}
          </span>
          <div className="min-w-0 space-y-2">
            <h4 className="text-sm font-semibold">
              <span className="sr-only">{t('guide.step', { n: index + 1 })}: </span>
              <Inline text={step.title} />
            </h4>
            {step.text && (
              <p className="text-sm leading-6 text-muted-foreground">
                <Inline text={step.text} />
              </p>
            )}
            {step.shot && <Screenshot language={language} id={step.shot} caption={step.title} />}
            {step.check && (
              <p className="flex items-start gap-2 rounded-md bg-emerald-500/10 px-3 py-2 text-sm">
                <CircleCheckIcon className="mt-0.5 size-4 shrink-0 text-emerald-500" aria-hidden="true" />
                <span>
                  <span className="font-medium">{t('guide.expected')}: </span>
                  <Inline text={step.check} />
                </span>
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

const NOTE = {
  info: { icon: InfoIcon, className: 'border-sky-500/40 bg-sky-500/8' },
  tip: { icon: LightbulbIcon, className: 'border-emerald-500/40 bg-emerald-500/8' },
  warn: { icon: TriangleAlertIcon, className: 'border-amber-500/50 bg-amber-500/10' },
} as const;

export function GuideBlockView({ block, language }: { block: GuideBlock; language: GuideLanguage }): ReactNode {
  const { t } = useTranslation();
  switch (block.kind) {
    case 'p':
      return (
        <p className="text-sm leading-7">
          <Inline text={block.text} />
        </p>
      );
    case 'list': {
      const List = block.ordered ? 'ol' : 'ul';
      return (
        <List className={cn('space-y-1.5 pl-5 text-sm leading-6', block.ordered ? 'list-decimal' : 'list-disc')}>
          {block.items.map((item, index) => (
            <li key={index}>
              <Inline text={item} />
            </li>
          ))}
        </List>
      );
    }
    case 'note': {
      const { icon: Icon, className } = NOTE[block.tone];
      return (
        <aside className={cn('flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-sm leading-6', className)}>
          <Icon className="mt-1 size-4 shrink-0" aria-hidden="true" />
          <span>
            <Inline text={block.text} />
          </span>
        </aside>
      );
    }
    case 'code':
      return (
        <pre className="overflow-x-auto rounded-lg bg-muted px-4 py-3 font-mono text-xs leading-5">
          {block.text}
        </pre>
      );
    case 'table':
      return (
        <div className="overflow-x-auto rounded-lg border border-border/70">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/60">
              <tr>
                {block.head.map((cell, index) => (
                  <th key={index} className="px-3 py-2 font-medium">
                    <Inline text={cell} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {block.rows.map((row, index) => (
                <tr key={index}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-3 py-2 align-top leading-6">
                      <Inline text={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case 'diagram':
      return <Diagram id={block.id} text={block.text} caption={block.caption} />;
    case 'shot':
      return <Screenshot language={language} id={block.id} caption={block.caption} />;
    case 'steps':
      return <Steps language={language} items={block.items} />;
    case 'verify':
      return (
        <section className="space-y-3 rounded-xl border border-emerald-500/40 bg-emerald-500/[0.06] p-4">
          <h4 className="flex items-center gap-2 text-sm font-semibold">
            <ListChecksIcon className="size-4 text-emerald-500" aria-hidden="true" />
            {t('guide.verify')}
          </h4>
          <ul className="space-y-1.5 text-sm leading-6">
            {block.items.map((item, index) => (
              <li key={index} className="flex items-start gap-2">
                <CircleCheckIcon className="mt-1 size-3.5 shrink-0 text-emerald-500" aria-hidden="true" />
                <span>
                  <Inline text={item} />
                </span>
              </li>
            ))}
          </ul>
          {block.shot && <Screenshot language={language} id={block.shot} caption={t('guide.verify')} />}
        </section>
      );
  }
}
