import { KeyRoundIcon } from 'lucide-react';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { apiJson } from '@/lib/api/client';
import { SettingsSection, SettingsRow } from './settings-layout';
import { useSettingsAction } from './use-settings-action';
import { PROVIDER_FIELDS } from '@shared/utils/translationProviderFields';
interface TokenState {
  active: string | null;
  sources: {
    source: 'openbao' | 'app' | 'env' | 'hf-cli';
    set: boolean;
    masked?: string;
    whoami_ok?: boolean | null;
    whoami_user?: string | null;
    /** OpenBao only: why the secret could not be read. */
    error?: string | null;
  }[];
}
export interface OpenBaoConfig {
  enabled: boolean;
  addr: string;
  mount: string;
  path: string;
  field: string;
  has_token: boolean;
  env_pinned: string[];
}
interface OpenBaoTest {
  ok: boolean;
  kind: string;
  masked?: string;
  ttl?: number | null;
}
const sourceKeys = {
  openbao: 'openbao',
  app: 'app',
  env: 'env',
  'hf-cli': 'cli',
};
const OPENBAO_ERRORS = ['unreachable', 'sealed', 'denied', 'not_found', 'not_configured'];
const openBaoError = (kind: string) =>
  'settings.openbao_error_' + (OPENBAO_ERRORS.includes(kind) ? kind : 'error');
export function CredentialSettings() {
  return (
    <>
      <HuggingFaceToken />
      <OpenBaoSource />
      <TranslationCredentials />
    </>
  );
}
export function HuggingFaceToken() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['hf-token-state'],
    queryFn: ({ signal }) => apiJson<TokenState>('/api/settings/hf-token/state', { signal }),
  });
  const action = useSettingsAction();
  const [token, setToken] = useState('');
  const [clearOpen, setClearOpen] = useState(false);
  const [clearCli, setClearCli] = useState(false);
  const refresh = () => client.invalidateQueries({ queryKey: ['hf-token-state'] });
  const save = () =>
    action.run(async () => {
      await apiJson('/api/settings/hf-token', {
        method: 'POST',
        body: JSON.stringify({ token: token.trim() }),
      });
      setToken('');
      await refresh();
    });
  const clear = () =>
    action.run(async () => {
      await apiJson('/api/settings/hf-token' + (clearCli ? '?also_clear_hf_cli=true' : ''), {
        method: 'DELETE',
      });
      setClearOpen(false);
      setClearCli(false);
      await refresh();
    });
  const busy = action.busy || query.isFetching;
  return (
    <SettingsSection icon={KeyRoundIcon} title={t('settings.hf_token_input')}>
      <div className="flex items-center justify-between gap-4 p-4">
        <p className="text-sm text-muted-foreground">{t('settings.hf_token_sources')}</p>
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() =>
            void action.run(async () => {
              const state = await apiJson<TokenState>('/api/settings/hf-token/state?fresh=1');
              client.setQueryData(['hf-token-state'], state);
            }, false)
          }
        >
          {t('settings.hf_token_test_now')}
        </Button>
      </div>
      {query.isPending && (
        <p role="status" className="p-4 text-sm">
          {t('common.loading')}
        </p>
      )}
      {query.data?.sources.map((source) => (
        <SettingsRow
          key={source.source}
          id={'token-' + source.source}
          title={t('settings.hf_source_' + sourceKeys[source.source] + '_label')}
        >
          <span className="text-xs text-muted-foreground">
            {t(source.set ? 'settings.hf_token_set' : 'settings.hf_token_not_set')}
          </span>
          {source.set && source.masked && <code className="text-xs">{source.masked}</code>}
          {!source.set && source.error && (
            <span className="text-xs text-destructive">{t(openBaoError(source.error))}</span>
          )}
          {source.set && (
            <span className="text-xs text-muted-foreground">
              {source.whoami_ok == null
                ? t('settings.hf_token_not_checked')
                : source.whoami_ok
                  ? source.whoami_user || t('settings.hf_token_verified')
                  : t('settings.hf_token_whoami_failed')}
            </span>
          )}
          {query.data?.active === source.source && (
            <span className="rounded bg-primary/10 px-2 py-1 text-xs text-primary">
              {t('settings.hf_token_active')}
            </span>
          )}
        </SettingsRow>
      ))}
      <form
        className="flex flex-wrap gap-2 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (token.trim() && !busy) void save();
        }}
      >
        <Input
          className="min-w-48 flex-1"
          type="password"
          aria-label={t('settings.hf_token_input')}
          value={token}
          autoComplete="new-password"
          spellCheck={false}
          disabled={busy}
          onChange={(event) => {
            setToken(event.target.value);
            action.reset();
          }}
        />
        <Button type="submit" size="sm" disabled={busy || !token.trim()}>
          {t('common.save')}
        </Button>
        {query.data?.sources.some((source) => source.source !== 'env' && source.set) && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => setClearOpen(true)}
          >
            {t('settings.hf_token_clear_btn')}
          </Button>
        )}
      </form>
      {clearOpen && (
        <div className="space-y-3 p-4">
          <p className="text-sm">{t('settings.hf_token_clear_confirm')}</p>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={clearCli} disabled={busy} onCheckedChange={setClearCli} />
            {t('settings.hf_token_also_clear')}
          </label>
          <div className="flex gap-2">
            <Button size="sm" variant="destructive" disabled={busy} onClick={() => void clear()}>
              {t('settings.hf_token_clear_btn')}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setClearOpen(false);
                setClearCli(false);
              }}
            >
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}
      {(action.error || query.isError) && (
        <p role="alert" className="p-4 text-sm text-destructive">
          {t('common.error')}{' '}
          <Button variant="ghost" size="sm" onClick={() => void query.refetch()}>
            {t('common.retry')}
          </Button>
        </p>
      )}
      {action.saved && (
        <p role="status" className="p-4 text-sm text-muted-foreground">
          {t('credentials.saved')}
        </p>
      )}
    </SettingsSection>
  );
}
export function OpenBaoSource() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['openbao-settings'],
    queryFn: ({ signal }) => apiJson<OpenBaoConfig>('/api/settings/openbao', { signal }),
  });
  const action = useSettingsAction();
  const [draft, setDraft] = useState<Partial<OpenBaoConfig>>({});
  const [token, setToken] = useState('');
  const [result, setResult] = useState<OpenBaoTest | null>(null);
  const cfg = query.data;
  if (!cfg) return null;
  const value = { ...cfg, ...draft };
  const pinned = (field: string) => cfg.env_pinned.includes(field);
  const put = async (body: Record<string, unknown>) => {
    const next = await apiJson<OpenBaoConfig>('/api/settings/openbao', {
      method: 'PUT',
      body: JSON.stringify(body),
    });
    client.setQueryData(['openbao-settings'], next);
    setDraft({});
    setToken('');
    await client.invalidateQueries({ queryKey: ['hf-token-state'] });
  };
  const fields = () => ({
    ...(pinned('addr') ? {} : { addr: value.addr }),
    mount: value.mount,
    path: value.path,
    field: value.field,
    ...(token.trim() && !pinned('token') ? { token: token.trim() } : {}),
  });
  const edit = (patch: Partial<OpenBaoConfig>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setResult(null);
    action.reset();
  };
  const text = (field: 'addr' | 'mount' | 'path' | 'field', placeholder?: string) => (
    <SettingsRow
      id={'openbao-' + field}
      title={t('settings.openbao_' + field)}
      description={
        pinned(field)
          ? t('settings.openbao_env_pinned')
          : field === 'addr'
            ? t('settings.openbao_addr_help')
            : undefined
      }
    >
      <Input
        className="w-64"
        aria-label={t('settings.openbao_' + field)}
        value={value[field]}
        placeholder={placeholder}
        spellCheck={false}
        disabled={action.busy || pinned(field)}
        onChange={(event) => edit({ [field]: event.target.value })}
      />
    </SettingsRow>
  );
  return (
    <SettingsSection icon={KeyRoundIcon} title={t('settings.openbao_title')}>
      <SettingsRow
        id="openbao-enabled"
        title={t('settings.openbao_enabled')}
        description={t('settings.openbao_desc')}
      >
        <Switch
          aria-label={t('settings.openbao_enabled')}
          checked={cfg.enabled}
          disabled={action.busy}
          onCheckedChange={(enabled) => void action.run(() => put({ enabled }), false)}
        />
      </SettingsRow>
      {text('addr')}
      {text('mount')}
      {text('path', 'voicestudio/hf')}
      {text('field')}
      <SettingsRow
        id="openbao-token"
        title={t('settings.openbao_token')}
        description={
          pinned('token') ? t('settings.openbao_env_pinned') : t('settings.openbao_token_help')
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          {cfg.has_token && (
            <span className="text-xs text-muted-foreground">
              {t('settings.openbao_token_saved')}
            </span>
          )}
          <Input
            className="w-64"
            type="password"
            aria-label={t('settings.openbao_token')}
            value={token}
            autoComplete="new-password"
            spellCheck={false}
            disabled={action.busy || pinned('token')}
            onChange={(event) => {
              setToken(event.target.value);
              setResult(null);
              action.reset();
            }}
          />
          {cfg.has_token && !pinned('token') && (
            <Button
              size="sm"
              variant="ghost"
              disabled={action.busy}
              onClick={() => void action.run(() => put({ token: '' }))}
            >
              {t('settings.openbao_token_remove')}
            </Button>
          )}
        </div>
      </SettingsRow>
      <div className="flex flex-wrap items-center gap-2 p-4">
        <Button
          size="sm"
          disabled={action.busy}
          onClick={() => void action.run(() => put(fields()))}
        >
          {t('common.save')}
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={action.busy}
          onClick={() =>
            void action.run(async () => {
              await put(fields());
              setResult(
                await apiJson<OpenBaoTest>('/api/settings/openbao/test', {
                  method: 'POST',
                }),
              );
            }, false)
          }
        >
          {t('settings.openbao_test')}
        </Button>
        {result && (
          <span
            role="status"
            className={'text-sm ' + (result.ok ? 'text-muted-foreground' : 'text-destructive')}
          >
            {result.ok
              ? t('settings.openbao_test_ok', { masked: result.masked ?? '' })
              : t(openBaoError(result.kind))}
            {result.ok && !!result.ttl && (
              <>
                {' '}
                ·{' '}
                {t('settings.openbao_ttl', {
                  hours: Math.floor(result.ttl / 3600),
                })}
              </>
            )}
          </span>
        )}
      </div>
      {action.error && (
        <p role="alert" className="px-4 pb-3 text-sm text-destructive">
          {t('common.error')}
        </p>
      )}
      {action.saved && (
        <p role="status" className="px-4 pb-3 text-sm text-muted-foreground">
          {t('credentials.saved')}
        </p>
      )}
    </SettingsSection>
  );
}
function TranslationCredentials() {
  const { t } = useTranslation();
  return (
    <SettingsSection icon={KeyRoundIcon} title={t('settings.translation_providers')}>
      <p className="p-4 text-sm text-muted-foreground">
        {t('settings.translation_providers_desc')}
      </p>
      {PROVIDER_FIELDS.map((field) => (
        <ProviderCredential key={field.key} field={field} />
      ))}
    </SettingsSection>
  );
}
function ProviderCredential({ field }: { field: (typeof PROVIDER_FIELDS)[number] }) {
  const { t } = useTranslation();
  const label = (field.labelPrefix ? field.labelPrefix + ' · ' : '') + t(field.labelKey);
  const client = useQueryClient();
  const [value, setValue] = useState('');
  const action = useSettingsAction();
  const save = () =>
    action.run(async () => {
      await apiJson('/system/set-env', {
        method: 'POST',
        body: JSON.stringify({ key: field.key, value: value.trim() }),
      });
      setValue('');
      await client.invalidateQueries({ queryKey: ['translation-engines'] });
    });
  return (
    <div>
      <SettingsRow id={'credential-' + field.key} title={label} description={t(field.helpKey)}>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (value.trim()) void save();
          }}
        >
          <Input
            type={field.isPassword ? 'password' : 'text'}
            autoComplete="new-password"
            spellCheck={false}
            aria-label={label}
            value={value}
            disabled={action.busy}
            onChange={(event) => {
              setValue(event.target.value);
              action.reset();
            }}
          />
          <Button size="sm" type="submit" disabled={action.busy || !value.trim()}>
            {t('common.save')}
          </Button>
        </form>
      </SettingsRow>
      {action.error && (
        <p role="alert" className="px-4 pb-3 text-sm text-destructive">
          {t('common.error')}
        </p>
      )}
      {action.saved && (
        <p role="status" className="px-4 pb-3 text-sm text-muted-foreground">
          {t('credentials.saved')}
        </p>
      )}
    </div>
  );
}
