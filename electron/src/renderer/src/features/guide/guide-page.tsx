import { useEffect, useRef } from 'react';
import { Link, useParams } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { BookMarkedIcon, ChevronLeftIcon, ChevronRightIcon } from 'lucide-react';
import { WorkspaceHeader } from '@/components/app-shell/workspace-header';
import { SecondarySidebar } from '@/components/workspace-sidebar';
import { cn } from '@/lib/utils';
import { GuideBlockView, Inline } from './guide-blocks';
import { GUIDE, guideLanguage } from './guide-content';

export function GuidePage() {
  const { t, i18n } = useTranslation();
  const params = useParams({ strict: false }) as { chapterId?: string };
  // `language`, not `resolvedLanguage`: a lazily loaded locale resolves to English until it arrives.
  const language = guideLanguage(i18n.language);
  const chapters = GUIDE[language];
  const index = Math.max(0, chapters.findIndex((chapter) => chapter.id === params.chapterId));
  const chapter = chapters[index];
  const scroller = useRef<HTMLElement>(null);
  const localized = (i18n.language ?? 'en').toLowerCase().split('-')[0];

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 }); // a new chapter starts at its top
  }, [chapter?.id]);

  if (!chapter) return null;
  const previous = chapters[index - 1];
  const next = chapters[index + 1];
  return (
    <div className="flex h-full min-h-0 flex-col">
      <WorkspaceHeader>
        <h1 className="text-sm font-medium">{t('guide.title')}</h1>
      </WorkspaceHeader>
      <div className="flex min-h-0 flex-1 @max-[40rem]:flex-col">
        <SecondarySidebar title={t('guide.contents')} icon={BookMarkedIcon} variant="navigation">
          <nav aria-label={t('guide.contents')} className="space-y-0.5">
            {chapters.map((item, position) => {
              const current = item.id === chapter.id;
              return (
                <div key={item.id}>
                  <Link
                    to="/guide/$chapterId"
                    params={{ chapterId: item.id }}
                    aria-current={current ? 'page' : undefined}
                    className={cn(
                      'flex h-8 items-center gap-2 rounded-md px-2.5 text-sm outline-none hover:bg-accent/55 focus-visible:ring-2 focus-visible:ring-ring',
                      current && 'bg-accent/80 font-medium',
                    )}
                  >
                    <span className="w-5 shrink-0 text-xs tabular-nums text-muted-foreground">
                      {position + 1}.
                    </span>
                    <span className="truncate">{item.title}</span>
                  </Link>
                  {current && (
                    <ul className="mb-1 ml-7 space-y-0.5 border-l border-border/60 pl-2">
                      {item.sections.map((section) => (
                        <li key={section.id}>
                          <button
                            type="button"
                            onClick={() =>
                              // The app routes by URL hash, so sections scroll instead of linking.
                              document.getElementById(section.id)?.scrollIntoView({ behavior: 'smooth' })
                            }
                            className="block w-full truncate rounded px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent/40 hover:text-foreground"
                          >
                            {section.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </nav>
        </SecondarySidebar>
        <section ref={scroller} className="min-w-0 flex-1 overflow-y-auto px-6 py-8">
          <article className="mx-auto max-w-5xl space-y-10" lang={language}>
            {localized !== language && localized !== 'en' && (
              <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
                {t('guide.language_note')}
              </p>
            )}
            <header className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t('guide.chapter', { n: index + 1 })}
              </p>
              <h2 className="text-2xl font-semibold tracking-tight">{chapter.title}</h2>
              <p className="text-sm leading-6 text-muted-foreground">
                <Inline text={chapter.summary} />
              </p>
            </header>
            {chapter.sections.map((section) => (
              <section key={section.id} id={section.id} className="scroll-mt-6 space-y-4">
                <h3 className="text-lg font-semibold tracking-tight">{section.title}</h3>
                {section.blocks.map((block, blockIndex) => (
                  <GuideBlockView key={blockIndex} block={block} language={language} />
                ))}
              </section>
            ))}
            <nav className="flex items-center justify-between gap-3 border-t border-border/60 pt-6 text-sm">
              {previous ? (
                <Link
                  to="/guide/$chapterId"
                  params={{ chapterId: previous.id }}
                  className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
                >
                  <ChevronLeftIcon className="size-4" aria-hidden="true" />
                  {previous.title}
                </Link>
              ) : (
                <span />
              )}
              {next && (
                <Link
                  to="/guide/$chapterId"
                  params={{ chapterId: next.id }}
                  className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
                >
                  {next.title}
                  <ChevronRightIcon className="size-4" aria-hidden="true" />
                </Link>
              )}
            </nav>
          </article>
        </section>
      </div>
    </div>
  );
}
