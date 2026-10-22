import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { CheckCircleIcon, TriangleAlertIcon, CircleXIcon, ScanSearchIcon } from 'lucide-react';
import type { GpuChoice, PreflightReport, PreflightRemote } from '@shared/api/setup-types';
import { apiJson } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { RaySettings } from './ray-settings';
import { SettingsRow, SettingsSection } from './settings-layout';

/** Per-viewer record that this user chose to keep running GPU engines on the CPU. */
export const GPU_CHOICE_KEY = 'voicestudio.gpu-choice';

function readCpuChoice() {
  try {
    return window.localStorage.getItem(GPU_CHOICE_KEY) === 'cpu';
  } catch {
    return false;
  }
}

function writeCpuChoice(cpu: boolean) {
  try {
    if (cpu) window.localStorage.setItem(GPU_CHOICE_KEY, 'cpu');
    else window.localStorage.removeItem(GPU_CHOICE_KEY);
  } catch {
    // Storage may be unavailable (private window, blocked site data); the
    // choice then lasts only for this view.
  }
}

/**
 * Offers the three ways forward when there is no usable local GPU: keep the
 * CPU, or set up a Ray cluster or Modal in place through the remote settings.
 */
function GpuChoices({ choices, onConfigured }: { choices: GpuChoice[]; onConfigured: () => void }) {
  const { t } = useTranslation();
  const [cpu, setCpu] = useState(readCpuChoice);
  const [provider, setProvider] = useState<'ray' | 'modal' | null>(null);
  const choose = (next: boolean) => {
    writeCpuChoice(next);
    setCpu(next);
  };
  return (
    <>
      {cpu ? (
        <p className="flex flex-wrap items-center gap-1 text-xs leading-5">
          <span>{t('setup.gpu_choice_using_cpu')}</span>
          <span aria-hidden="true">·</span>
          <Button
            type="button"
            variant="link"
            size="xs"
            className="h-auto p-0 text-xs"
            onClick={() => choose(false)}
          >
            {t('setup.gpu_choice_change')}
          </Button>
        </p>
      ) : (
        <div
          role="group"
          aria-label={t('setup.gpu_choice_label')}
          className="flex flex-wrap gap-2 pt-1"
        >
          {choices.includes('cpu') && (
            <Button type="button" size="sm" variant="outline" onClick={() => choose(true)}>
              {t('setup.gpu_choice_cpu')}
            </Button>
          )}
          {choices.includes('ray') && (
            <Button type="button" size="sm" variant="outline" onClick={() => setProvider('ray')}>
              {t('setup.gpu_choice_ray')}
            </Button>
          )}
          {choices.includes('modal') && (
            <Button type="button" size="sm" variant="outline" onClick={() => setProvider('modal')}>
              {t('setup.gpu_choice_modal')}
            </Button>
          )}
        </div>
      )}
      <Dialog
        open={provider !== null}
        onOpenChange={(open) => {
          if (open) return;
          setProvider(null);
          onConfigured();
        }}
      >
        <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{t('setup.gpu_choice_dialog_title')}</DialogTitle>
            <DialogDescription>{t('setup.gpu_choice_dialog_desc')}</DialogDescription>
          </DialogHeader>
          {provider && (
            <div className="@container flex min-w-0 flex-col gap-6">
              <RaySettings initialProvider={provider} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

export function SystemPreflight() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['setup-preflight'],
    queryFn: ({ signal }) => apiJson<PreflightReport>('/setup/preflight', { signal }),
    enabled: false,
    retry: false,
  });
  const checks = Array.isArray(query.data?.checks) ? query.data.checks : [];
  // The backend sends English text; checks it marks with a stable id are shown
  // from the translation catalog instead.
  const remoteDetail = (remote: PreflightRemote) =>
    remote.provider === 'modal'
      ? t('setup.gpu_remote_modal', {
          count: remote.engines,
          gpu: remote.gpu || t('setup.gpu_remote_cpu'),
        })
      : t('setup.gpu_remote_ray', { count: remote.engines });
  const localized = (check: (typeof checks)[number]) =>
    check.id === 'arch'
      ? {
          label: t('setup.check_arch_label'),
          detail: t('setup.check_arch_detail'),
          fix: t('setup.check_arch_fix'),
        }
      : check.id === 'gpu' && check.remote
        ? { label: check.label, detail: remoteDetail(check.remote), fix: check.fix }
        : { label: check.label, detail: check.detail, fix: check.fix };
  // After the remote settings dialog closes, re-probe so the GPU check shows
  // where GPU work now goes, and refresh the settings page's copy.
  const afterRemoteSetup = () => {
    void queryClient.invalidateQueries({ queryKey: ['ray-settings'] });
    void query.refetch();
  };
  return (
    <SettingsSection title={t('setup.system_preflight')} icon={ScanSearchIcon}>
      <SettingsRow
        id="system-preflight-check"
        title={t('setup.system_check')}
        description={t('setup.system_check_desc')}
      >
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          {t(
            query.isFetching
              ? 'setup.probing'
              : query.data
                ? 'setup.recheck'
                : 'setup.system_check',
          )}
        </Button>
      </SettingsRow>
      {query.isError && (
        <p role="alert" className="px-4 py-3 text-sm text-destructive">
          {t('backend.retry')}
        </p>
      )}
      {checks.length > 0 && (
        <ul className="divide-y divide-border/50 px-4">
          {checks.map((check) => {
            const Icon =
              check.status === 'pass'
                ? CheckCircleIcon
                : check.status === 'warn'
                  ? TriangleAlertIcon
                  : CircleXIcon;
            const text = localized(check);
            return (
              <li key={check.id} className="flex items-start gap-3 py-3">
                <Icon
                  aria-hidden="true"
                  className={
                    'mt-0.5 size-4 shrink-0 ' +
                    (check.status === 'pass'
                      ? 'text-success'
                      : check.status === 'warn'
                        ? 'text-warning'
                        : 'text-destructive')
                  }
                />
                <div className="min-w-0 space-y-1">
                  <h3 className="text-sm font-medium">{text.label}</h3>
                  <p className="break-words text-xs leading-5 text-muted-foreground">
                    {text.detail}
                  </p>
                  {text.fix && <p className="break-words text-xs leading-5">{text.fix}</p>}
                  {check.id === 'gpu' &&
                    Array.isArray(check.choices) &&
                    check.choices.length > 0 && (
                      <GpuChoices choices={check.choices} onConfigured={afterRemoteSetup} />
                    )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SettingsSection>
  );
}
