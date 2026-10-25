import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon, TriangleAlertIcon, WrenchIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useTtsReadiness } from '@/hooks/use-tts-readiness';
import { useModelInstall } from '@/hooks/use-model-install';
import { InstallProgress } from '@/components/model-install-progress';
import { apiJson, describeError } from '@/lib/api/client';
import { openRepairAgent } from '@/lib/repair-agent-events';
import type { EnginesResponse } from '@/lib/api/types';
import type { ModelCatalogueResponse } from '@/features/settings/model-catalogue-query';

interface RecommendedModel {
  repo_id: string;
  role: string;
  required: boolean;
  installed: boolean;
}

interface ModelRecommendations {
  models: RecommendedModel[];
}

export function EngineNotice({
  operation = 'tts',
  compact = false,
}: {
  operation?: string;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [fixing, setFixing] = useState(false);
  const blocker = useTtsReadiness(operation);

  const refreshReadiness = useCallback(
    () =>
      Promise.all(
        ['model-install-jobs', 'model-catalogue', 'model-recommendations', 'engines'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
    [client],
  );

  const repair = useCallback(
    (detail: string) => {
      openRepairAgent(
        `ACTION_REQUEST: Restore text-to-speech readiness for operation "${operation}". ${detail}`,
        true,
      );
    },
    [operation],
  );

  const activateAvailableEngine = useCallback(
    async (known?: EnginesResponse): Promise<boolean> => {
      const engines = known ?? (await apiJson<EnginesResponse>('/engines'));
      const current = engines.tts.backends.find((backend) => backend.id === engines.tts.active);
      if (current?.available) {
        await refreshReadiness();
        return true;
      }
      const available = engines.tts.backends.filter(
        (backend) => backend.available && backend.routing_status !== 'unavailable',
      );
      const candidate = available.find((backend) => backend.id === 'omnivoice') ?? available[0];
      if (!candidate) return false;
      await apiJson('/engines/select', {
        method: 'POST',
        body: JSON.stringify({ family: 'tts', backend_id: candidate.id }),
      });
      await refreshReadiness();
      return true;
    },
    [refreshReadiness],
  );

  const install = useModelInstall(undefined, {
    onReady: () => {
      void (async () => {
        try {
          if (!(await activateAvailableEngine())) {
            repair('The model installed, but no compatible local TTS engine became available.');
          }
        } catch (error) {
          repair(`The model installed, but activation failed: ${describeError(error)}`);
        }
      })();
    },
    // A full disk or a gated repository has an exact next step on screen;
    // only an unexplained failure goes to the repair agent.
    onFailed: (view) => {
      if (!view.problem) repair(view.detail || 'The model installer stopped before completion.');
    },
  });

  if (blocker !== 'engine') return null;
  const startInstall = async (repo: string) => {
    if ((await install.start(repo)) === 'started')
      toast.success(t('models.started_downloading', { count: 1 }));
  };
  const fix = async () => {
    setFixing(true);
    try {
      // Readiness also blocks when the selected engine is available but the
      // model chosen for it is not downloaded. Download that model first,
      // keeping the user's engine choice; a recommended model alone would not
      // unblock that engine.
      const engines = await apiJson<EnginesResponse>('/engines');
      const active = engines.tts?.backends?.find((backend) => backend.id === engines.tts.active);
      const selectedModel = active?.available ? engines.tts.active_model : null;
      if (selectedModel) {
        const catalogue = await apiJson<ModelCatalogueResponse>('/models');
        const entry = catalogue.models?.find((model) => model.repo_id === selectedModel);
        if (entry && (!entry.installed || entry.incomplete)) {
          await startInstall(selectedModel);
          return;
        }
      }
      const recommendation = await apiJson<ModelRecommendations>('/setup/recommendations');
      const missing = recommendation.models.find(
        (item) => item.required && item.role.toLowerCase() === 'tts' && !item.installed,
      );
      if (missing) {
        await startInstall(missing.repo_id);
        return;
      }
      if (!(await activateAvailableEngine(engines))) {
        repair(
          'The required model is installed, but no compatible engine is ready. Diagnose the live engine state and complete supported app-level recovery.',
        );
      }
    } catch (error) {
      repair(`Automatic model setup failed: ${describeError(error)}`);
    } finally {
      setFixing(false);
    }
  };
  const view = install.view;
  const action =
    view && view.stage !== 'ready' && view.stage !== 'cancelled' ? (
      <InstallProgress
        className={compact ? 'min-w-48 flex-1 basis-full' : 'mt-2'}
        view={view}
        busy={install.busy}
        onCancel={() => void install.cancel()}
        onRetry={() => void install.retry()}
        onDismiss={view.stage === 'failed' ? install.dismiss : undefined}
      />
    ) : (
      <Button
        type="button"
        size="sm"
        className={compact ? 'shrink-0' : 'mt-2'}
        disabled={fixing || install.busy}
        onClick={fix}
      >
        {fixing ? (
          <LoaderCircleIcon className="animate-spin motion-reduce:animate-none" />
        ) : (
          <WrenchIcon />
        )}
        {t('repairAgent.fix')}
      </Button>
    );
  if (compact) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-3 rounded-lg border border-warning/30 bg-warning/8 px-3 py-2 text-sm">
        <TriangleAlertIcon className="size-4 shrink-0 text-warning" />
        <div className="min-w-48 flex-1">
          <p className="font-medium text-foreground">{t('engines.none_ready_title')}</p>
          <p className="text-xs leading-5 text-muted-foreground">{t('engines.none_ready_body')}</p>
        </div>
        {action}
      </div>
    );
  }
  return (
    <Alert className="border-warning/40 bg-warning/10 text-foreground">
      <TriangleAlertIcon className="text-warning" />
      <AlertTitle>{t('engines.none_ready_title')}</AlertTitle>
      <AlertDescription>
        <p>{t('engines.none_ready_body')}</p>
        {action}
      </AlertDescription>
    </Alert>
  );
}
