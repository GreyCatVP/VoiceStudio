import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { Button, buttonVariants } from '@/components/ui/button';
import { useEngines } from '@/hooks/use-engines';
import type { CloneBlocker } from '@/lib/clone-readiness';
import { openTake } from '@/lib/store/takes';
import { setWorkspace } from '@/lib/store/workspace';

/**
 * Why Generate is unavailable on the Clone page, with the next step. A model
 * that cannot clone but designs voices from a description (e.g. Qwen3-TTS
 * VoiceDesign) points to Voice Design instead of a dead end.
 */
export function CloneReadinessNotice({
  id,
  blocker,
  demo,
}: {
  id: string;
  blocker: NonNullable<CloneBlocker>;
  demo: boolean;
}) {
  const { t } = useTranslation();
  const { activeTts } = useEngines();
  const designInstead = activeTts?.supports_voice_design !== false;
  return (
    <div
      id={id}
      className="mb-3 flex flex-wrap items-center justify-between gap-2 px-1 text-sm text-muted-foreground"
    >
      <span role="status">
        {t(
          blocker === 'cloning'
            ? designInstead
              ? 'clone.cannotCloneUseDesign'
              : 'convert.cloning_required'
            : blocker === 'engine'
              ? demo
                ? 'demo.prerendered_chip'
                : 'engines.none_ready_title'
              : blocker === 'reference'
                ? 'tts_errors.upload_or_select'
                : blocker === 'text'
                  ? 'tts_errors.enter_text'
                  : 'preferences.loading',
        )}
      </span>
      {blocker === 'reference' && (
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="xs"
            onClick={() => {
              openTake(null);
              setWorkspace({ panel: 'voice' });
            }}
          >
            {t('clone.reference_audio')}
          </Button>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => setWorkspace({ libraryOpen: true, libraryTab: 'voices' })}
          >
            {t('clone.saved_profiles')}
          </Button>
        </div>
      )}
      {blocker === 'cloning' && designInstead && (
        <Link to="/design" className={buttonVariants({ variant: 'ghost', size: 'xs' })}>
          {t('nav.design')}
        </Link>
      )}
      {(blocker === 'engine' || blocker === 'cloning') && !demo && (
        <Link
          to="/settings/models/$family"
          params={{ family: 'tts' }}
          className={buttonVariants({ variant: 'ghost', size: 'xs' })}
        >
          {t('engineSidebar.tts')}
        </Link>
      )}
    </div>
  );
}
