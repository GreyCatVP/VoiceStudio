import {
  CheckCircle2Icon,
  CpuIcon,
  ListChecksIcon,
  LoaderCircleIcon,
  PlugIcon,
  RefreshCwIcon,
  ServerCogIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  SquareIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { apiJson, describeError } from "@/lib/api/client";
import { SettingsActionError } from "./settings-action-error";
import { SettingsRow, SettingsSection } from "./settings-layout";

export interface RayConfig {
  enabled: boolean;
  dashboard_url: string;
  cf_access_client_id: string;
  engines: string[];
  num_gpus: number;
  num_cpus: number;
  cache_dir: string;
  python: string;
  keep_failed_jobs: boolean;
  has_token: boolean;
  has_cf_secret: boolean;
  env_pinned: string[];
  available_engines: RayEngine[];
  /** Older backends omit the Modal fields; they only know the Ray provider. */
  provider?: RemoteProvider;
  /** One of `modal_gpus`, or '' when GPU engines run on CPU. */
  modal_gpu?: string;
  modal_gpus?: string[];
  modal_app?: string;
  modal_volume?: string;
  has_modal_token?: boolean;
}

export type RemoteProvider = "ray" | "modal";

export interface RayEngine {
  id: string;
  gpu: boolean;
  /** Older backends omit `kind`; missing or unknown kinds count as text to speech. */
  kind?: RayEngineKind;
}

export type RayEngineKind =
  "tts" | "asr" | "translation" | "diarization" | "separation";

const RAY_ENGINE_KINDS: readonly RayEngineKind[] = [
  "tts",
  "asr",
  "translation",
  "diarization",
  "separation",
];

/** Missing or unknown kinds (older or newer backends) count as text to speech. */
function engineKind(engine: RayEngine): RayEngineKind {
  const kind = engine.kind as string | undefined;
  return RAY_ENGINE_KINDS.find((known) => known === kind) ?? "tts";
}

type RayKind =
  | "ok"
  | "not_configured"
  | "auth"
  | "network"
  | "not_found"
  | "http"
  | "protocol"
  | "job_failed"
  | "timeout"
  | "error";

interface RayGpu {
  name: string;
  total_mb: number;
  used_mb: number;
  free_mb: number;
}

interface RayTestResult {
  ok: boolean;
  kind: RayKind;
  message?: string;
  warnings?: string[];
  ray_version?: string;
  authentication_mode?: string;
  cluster_python?: string;
  cluster_status?: string;
  node?: {
    python?: string;
    platform?: string;
    cuda_visible_devices?: string;
    cache_dir?: string;
    cache_free_gb?: number;
    gpus?: RayGpu[];
  };
  latency_ms?: number;
}

interface RayJob {
  submission_id: string;
  status: string;
  engine?: string | null;
  op?: string | null;
  start_time?: number | null;
  end_time?: number | null;
  message?: string | null;
}

interface RayJobsResponse {
  ok: boolean;
  jobs?: RayJob[];
  kind?: RayKind;
  message?: string;
}

interface RayStopResponse {
  ok: boolean;
  stopped?: boolean;
  kind?: RayKind;
  message?: string;
}

const SETTINGS_KEY = ["ray-settings"] as const;
const JOBS_KEY = ["ray-jobs"] as const;
const SECRET_MASK = "••••••••";
const STOPPABLE = new Set(["RUNNING", "PENDING"]);
/** Select sentinel for `modal_gpu: ''` (Base UI treats '' as no selection). */
const MODAL_CPU = "__cpu__";

interface Draft {
  enabled: boolean;
  dashboardUrl: string;
  cfClientId: string;
  engines: string[];
  numGpus: string;
  numCpus: string;
  cacheDir: string;
  python: string;
  keepFailed: boolean;
  token: string;
  cfSecret: string;
  clearToken: boolean;
  clearCfSecret: boolean;
  /** The auth fields show only for the method(s) the cluster uses. */
  useToken: boolean;
  useCfAccess: boolean;
  provider: RemoteProvider;
  modalGpu: string;
  modalApp: string;
  modalVolume: string;
  modalTokenId: string;
  modalTokenSecret: string;
  clearModalToken: boolean;
}

function draftFrom(config: RayConfig): Draft {
  return {
    provider: config.provider ?? "ray",
    modalGpu: config.modal_gpu ?? "",
    modalApp: config.modal_app ?? "",
    modalVolume: config.modal_volume ?? "",
    modalTokenId: "",
    modalTokenSecret: "",
    clearModalToken: false,
    enabled: config.enabled,
    dashboardUrl: config.dashboard_url || "",
    cfClientId: config.cf_access_client_id || "",
    engines: [...config.engines],
    numGpus: String(config.num_gpus),
    numCpus: String(config.num_cpus),
    cacheDir: config.cache_dir || "",
    python: config.python || "",
    keepFailed: config.keep_failed_jobs,
    token: "",
    cfSecret: "",
    clearToken: false,
    clearCfSecret: false,
    useToken: config.has_token || config.env_pinned.includes("token"),
    useCfAccess: Boolean(config.cf_access_client_id) || config.has_cf_secret,
  };
}

const sameSet = (a: string[], b: string[]) =>
  a.length === b.length && a.every((item) => b.includes(item));

/** Only the fields the user changed; secrets are sent only when typed or cleared. */
export function rayChanges(
  config: RayConfig,
  draft: Draft,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  const pinned = new Set(config.env_pinned);
  if (draft.provider !== (config.provider ?? "ray"))
    body.provider = draft.provider;
  if (draft.enabled !== config.enabled) body.enabled = draft.enabled;
  if (
    !pinned.has("dashboard_url") &&
    draft.dashboardUrl.trim() !== (config.dashboard_url || "")
  )
    body.dashboard_url = draft.dashboardUrl.trim();
  // Turning a method off removes its stored credentials on save.
  const cfClientId = draft.useCfAccess ? draft.cfClientId.trim() : "";
  if (cfClientId !== (config.cf_access_client_id || ""))
    body.cf_access_client_id = cfClientId;
  if (!sameSet(draft.engines, config.engines)) body.engines = draft.engines;
  if (Number(draft.numGpus) !== config.num_gpus)
    body.num_gpus = Number(draft.numGpus);
  if (Number(draft.numCpus) !== config.num_cpus)
    body.num_cpus = Number(draft.numCpus);
  if (draft.cacheDir.trim() !== (config.cache_dir || ""))
    body.cache_dir = draft.cacheDir.trim();
  if (draft.python.trim() !== (config.python || ""))
    body.python = draft.python.trim();
  if (draft.keepFailed !== config.keep_failed_jobs)
    body.keep_failed_jobs = draft.keepFailed;
  if (!pinned.has("token")) {
    if (draft.useToken && draft.token) body.auth_token = draft.token;
    else if (draft.clearToken || (!draft.useToken && config.has_token))
      body.auth_token = "";
  }
  if (draft.useCfAccess && draft.cfSecret)
    body.cf_access_client_secret = draft.cfSecret;
  else if (draft.clearCfSecret || (!draft.useCfAccess && config.has_cf_secret))
    body.cf_access_client_secret = "";
  if (draft.modalGpu !== (config.modal_gpu ?? ""))
    body.modal_gpu = draft.modalGpu;
  if (draft.modalApp.trim() !== (config.modal_app ?? ""))
    body.modal_app = draft.modalApp.trim();
  if (draft.modalVolume.trim() !== (config.modal_volume ?? ""))
    body.modal_volume = draft.modalVolume.trim();
  // The Modal token is one credential pair: clearing removes both halves.
  if (draft.modalTokenId) body.modal_token_id = draft.modalTokenId;
  else if (draft.clearModalToken) body.modal_token_id = "";
  if (draft.modalTokenSecret) body.modal_token_secret = draft.modalTokenSecret;
  else if (draft.clearModalToken) body.modal_token_secret = "";
  return body;
}

const gb = (mb: number) => (mb / 1024).toFixed(1);

function formatTime(value?: number | null) {
  if (!value) return "—";
  // Ray reports epoch milliseconds; tolerate seconds as well.
  const ms = value < 1e12 ? value * 1000 : value;
  return new Date(ms).toLocaleString();
}

export function RaySettings({
  initialProvider,
}: { initialProvider?: RemoteProvider } = {}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const config = useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: ({ signal }) =>
      apiJson<RayConfig>("/api/settings/ray", { signal }),
  });
  const [server, setServer] = useState<RayConfig | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [testResult, setTestResult] = useState<RayTestResult | null>(null);
  const [stopping, setStopping] = useState<string | null>(null);
  // `initialProvider` preselects the provider once, as an unsaved draft change.
  const preselect = useRef(initialProvider);

  useEffect(() => {
    if (!config.data) return;
    setServer(config.data);
    const next = draftFrom(config.data);
    if (preselect.current) next.provider = preselect.current;
    preselect.current = undefined;
    setDraft(next);
  }, [config.data]);

  // Modal has no job list; only a saved, enabled Ray provider is polled.
  const rayJobs =
    Boolean(server?.enabled) && (server?.provider ?? "ray") === "ray";
  const jobs = useQuery({
    queryKey: JOBS_KEY,
    queryFn: ({ signal }) =>
      apiJson<RayJobsResponse>("/api/settings/ray/jobs", { signal }),
    enabled: rayJobs,
    refetchInterval: rayJobs ? 5000 : false,
  });

  const update = (patch: Partial<Draft>) => {
    setDraft((current) => (current ? { ...current, ...patch } : current));
    setSaved(false);
    setTestResult(null);
  };

  const changes = server && draft ? rayChanges(server, draft) : {};
  const dirty = Object.keys(changes).length > 0;
  const pinned = new Set(server?.env_pinned ?? []);
  const busy = config.isPending || saving || testing;
  const modal = draft?.provider === "modal";
  const savedModal = (server?.provider ?? "ray") === "modal";

  const save = async () => {
    if (saving || !server || !draft) return false;
    const gpus = Number(draft.numGpus);
    const cpus = Number(draft.numCpus);
    if (
      !Number.isFinite(gpus) ||
      !Number.isFinite(cpus) ||
      draft.numGpus === "" ||
      draft.numCpus === ""
    ) {
      setError(t("settings.ray_invalid_number"));
      return false;
    }
    if (!dirty) return true;
    setSaving(true);
    setError("");
    try {
      const next = await apiJson<RayConfig>("/api/settings/ray", {
        method: "PUT",
        body: JSON.stringify(changes),
      });
      setServer(next);
      setDraft(draftFrom(next));
      setSaved(true);
      queryClient.setQueryData(SETTINGS_KEY, next);
      return true;
    } catch (reason) {
      setError(describeError(reason));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const testConnection = async () => {
    if (testing || saving || dirty) return;
    setTesting(true);
    setError("");
    setTestResult(null);
    try {
      setTestResult(
        await apiJson<RayTestResult>("/api/settings/ray/test", {
          method: "POST",
        }),
      );
    } catch (reason) {
      // A failed test request is a test result, not a save failure.
      setTestResult({
        ok: false,
        kind: "error",
        message: describeError(reason),
      });
    } finally {
      setTesting(false);
    }
  };

  const stopJob = async (id: string) => {
    if (stopping) return;
    setStopping(id);
    try {
      const result = await apiJson<RayStopResponse>(
        `/api/settings/ray/jobs/${encodeURIComponent(id)}/stop`,
        { method: "POST" },
      );
      if (result.ok && result.stopped !== false)
        toast.success(t("settings.ray_job_stop_requested", { id }));
      else if (result.ok) toast.info(t("settings.ray_job_not_running", { id }));
      else toast.error(result.message || kindMessage(result.kind ?? "error"));
    } catch (reason) {
      toast.error(t("settings.ray_job_stop_failed"), {
        description: describeError(reason),
      });
    } finally {
      setStopping(null);
      void queryClient.invalidateQueries({ queryKey: JOBS_KEY });
    }
  };

  const modalKindMessage = (kind: RayKind) => {
    switch (kind) {
      case "ok":
        return t("settings.modal_kind_ok");
      case "not_configured":
        return t("settings.modal_kind_not_configured");
      case "auth":
        return t("settings.modal_kind_auth");
      case "network":
        return t("settings.modal_kind_network");
      case "job_failed":
        return t("settings.modal_kind_job_failed");
      case "timeout":
        return t("settings.modal_kind_timeout");
      default:
        return t("settings.modal_kind_error");
    }
  };

  const kindMessage = (kind: RayKind) => {
    switch (kind) {
      case "ok":
        return t("settings.ray_kind_ok");
      case "not_configured":
        return t("settings.ray_kind_not_configured");
      case "auth":
        return t("settings.ray_kind_auth");
      case "network":
        return t("settings.ray_kind_network");
      case "not_found":
        return t("settings.ray_kind_not_found");
      case "http":
        return t("settings.ray_kind_http");
      case "protocol":
        return t("settings.ray_kind_protocol");
      case "job_failed":
        return t("settings.ray_kind_job_failed");
      case "timeout":
        return t("settings.ray_kind_timeout");
      default:
        return t("settings.ray_kind_error");
    }
  };

  const authDisabled =
    testResult?.warnings?.includes("cluster_auth_disabled") ?? false;
  const otherWarnings = (testResult?.warnings ?? []).filter(
    (w) => w !== "cluster_auth_disabled",
  );
  const saveButton = (
    <Button disabled={!dirty || busy} onClick={() => void save()}>
      {saving && <LoaderCircleIcon className="animate-spin" />}
      {saving ? t("common.saving") : t("common.save")}
    </Button>
  );
  const savedNote = (announce: boolean) =>
    saved &&
    !dirty && (
      <span
        role={announce ? "status" : undefined}
        className="inline-flex items-center gap-1 text-xs text-emerald-500"
      >
        <CheckCircle2Icon className="size-3.5" />
        {t(savedModal ? "settings.modal_saved" : "settings.ray_saved")}
      </span>
    );
  const pinnedNote = (
    <span className="block text-amber-600 dark:text-amber-400">
      {t("settings.ray_env_pinned")}
    </span>
  );
  const jobList = jobs.data?.jobs ?? [];
  const modalGpus = server?.modal_gpus ?? [];
  const gpuItems = [
    { value: MODAL_CPU, label: t("settings.modal_gpu_cpu") },
    ...modalGpus.map((gpu) => ({ value: gpu, label: gpu })),
  ];

  return (
    <>
      <SettingsSection
        icon={ServerCogIcon}
        title={t("settings.ray_connection")}
      >
        <SettingsRow
          id="remote-provider"
          title={t("settings.remote_provider")}
          description={t("settings.remote_provider_hint")}
        >
          <ToggleGroup
            aria-label={t("settings.remote_provider")}
            value={[draft?.provider ?? "ray"]}
            onValueChange={(values) => {
              const provider = (["ray", "modal"] as const).find(
                (p) => p === values[0],
              );
              if (provider) update({ provider });
            }}
            disabled={busy || !draft}
            className="rounded-xl border border-border/60 bg-muted/45 p-1"
          >
            <ToggleGroupItem value="ray">
              {t("settings.remote_provider_ray")}
            </ToggleGroupItem>
            <ToggleGroupItem value="modal">
              {t("settings.remote_provider_modal")}
            </ToggleGroupItem>
          </ToggleGroup>
        </SettingsRow>

        {modal && (
          <div className="p-4">
            <div
              role="note"
              className="flex gap-3 rounded-xl border border-border/60 bg-muted/40 p-4 text-sm"
            >
              <ShieldCheckIcon
                className="mt-0.5 size-5 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <div className="space-y-1">
                <p className="font-medium">
                  {t("settings.modal_privacy_title")}
                </p>
                <p className="text-muted-foreground">
                  {t("settings.modal_privacy_body")}
                </p>
              </div>
            </div>
          </div>
        )}

        <SettingsRow
          id="ray-enabled"
          title={t(modal ? "settings.modal_enabled" : "settings.ray_enabled")}
          description={t(modal ? "settings.modal_desc" : "settings.ray_desc")}
        >
          {config.isPending ? (
            <LoaderCircleIcon className="size-4 animate-spin text-muted-foreground" />
          ) : (
            <Switch
              aria-label={t(
                modal ? "settings.modal_enabled" : "settings.ray_enabled",
              )}
              checked={draft?.enabled ?? false}
              disabled={busy || !draft}
              onCheckedChange={(enabled) => update({ enabled })}
            />
          )}
        </SettingsRow>

        {(config.isError || error) && (
          <div className="p-4">
            <SettingsActionError
              title={t(
                config.isError && !error
                  ? "settings.ray_load_failed"
                  : "settings.ray_save_failed",
              )}
              detail={error || describeError(config.error)}
              onDismiss={error ? () => setError("") : undefined}
            />
          </div>
        )}

        {!modal && (
          <>
            <SettingsRow
              id="ray-dashboard-url"
              title={t("settings.ray_dashboard_url")}
              description={
                <>
                  {t("settings.ray_dashboard_url_hint")}
                  {pinned.has("dashboard_url") && pinnedNote}
                </>
              }
            >
              <Input
                aria-label={t("settings.ray_dashboard_url")}
                value={draft?.dashboardUrl ?? ""}
                className="w-full font-mono @2xl:w-96"
                placeholder="https://ray.example.com"
                readOnly={pinned.has("dashboard_url")}
                disabled={busy}
                onChange={(event) =>
                  update({ dashboardUrl: event.target.value })
                }
              />
            </SettingsRow>

            <SettingsRow
              id="ray-use-token"
              title={t("settings.ray_use_token")}
              description={
                !draft?.useToken && server?.has_token
                  ? t("settings.ray_secret_will_clear")
                  : t("settings.ray_use_token_hint")
              }
            >
              <Switch
                aria-label={t("settings.ray_use_token")}
                checked={draft?.useToken ?? false}
                disabled={busy || !draft || pinned.has("token")}
                onCheckedChange={(useToken) => update({ useToken })}
              />
            </SettingsRow>

            {draft?.useToken && (
              <SettingsRow
                id="ray-token"
                title={t("settings.ray_token")}
                description={
                  <>
                    {draft?.clearToken
                      ? t("settings.ray_secret_will_clear")
                      : server?.has_token
                        ? t("settings.ray_token_stored")
                        : t("settings.ray_token_hint")}
                    {pinned.has("token") && pinnedNote}
                  </>
                }
              >
                <Input
                  aria-label={t("settings.ray_token")}
                  type="password"
                  value={draft?.token ?? ""}
                  className="w-full font-mono @2xl:w-72"
                  placeholder={
                    server?.has_token && !draft?.clearToken ? SECRET_MASK : ""
                  }
                  autoComplete="off"
                  readOnly={pinned.has("token")}
                  disabled={busy}
                  onChange={(event) =>
                    update({ token: event.target.value, clearToken: false })
                  }
                />
                {server?.has_token && !pinned.has("token") && (
                  <Button
                    variant="ghost"
                    disabled={busy || draft?.clearToken}
                    onClick={() => update({ token: "", clearToken: true })}
                  >
                    {t("settings.ray_clear_token")}
                  </Button>
                )}
              </SettingsRow>
            )}

            <SettingsRow
              id="ray-use-cf"
              title={t("settings.ray_use_cf")}
              description={
                !draft?.useCfAccess &&
                (server?.has_cf_secret || server?.cf_access_client_id)
                  ? t("settings.ray_secret_will_clear")
                  : t("settings.ray_use_cf_hint")
              }
            >
              <Switch
                aria-label={t("settings.ray_use_cf")}
                checked={draft?.useCfAccess ?? false}
                disabled={busy || !draft}
                onCheckedChange={(useCfAccess) => update({ useCfAccess })}
              />
            </SettingsRow>

            {draft?.useCfAccess && (
              <>
                <SettingsRow
                  id="ray-cf-client-id"
                  title={t("settings.ray_cf_client_id")}
                  description={t("settings.ray_cf_hint")}
                >
                  <Input
                    aria-label={t("settings.ray_cf_client_id")}
                    value={draft?.cfClientId ?? ""}
                    className="w-full font-mono @2xl:w-72"
                    autoComplete="off"
                    disabled={busy}
                    onChange={(event) =>
                      update({ cfClientId: event.target.value })
                    }
                  />
                </SettingsRow>

                <SettingsRow
                  id="ray-cf-secret"
                  title={t("settings.ray_cf_client_secret")}
                  description={
                    draft?.clearCfSecret
                      ? t("settings.ray_secret_will_clear")
                      : server?.has_cf_secret
                        ? t("settings.ray_cf_secret_stored")
                        : t("settings.ray_cf_hint")
                  }
                >
                  <Input
                    aria-label={t("settings.ray_cf_client_secret")}
                    type="password"
                    value={draft?.cfSecret ?? ""}
                    className="w-full font-mono @2xl:w-72"
                    placeholder={
                      server?.has_cf_secret && !draft?.clearCfSecret
                        ? SECRET_MASK
                        : ""
                    }
                    autoComplete="off"
                    disabled={busy}
                    onChange={(event) =>
                      update({
                        cfSecret: event.target.value,
                        clearCfSecret: false,
                      })
                    }
                  />
                  {server?.has_cf_secret && (
                    <Button
                      variant="ghost"
                      disabled={busy || draft?.clearCfSecret}
                      onClick={() =>
                        update({ cfSecret: "", clearCfSecret: true })
                      }
                    >
                      {t("settings.ray_clear_cf_secret")}
                    </Button>
                  )}
                </SettingsRow>
              </>
            )}
          </>
        )}

        {modal && (
          <>
            <SettingsRow
              id="modal-token-id"
              title={t("settings.modal_token_id")}
              description={
                draft?.clearModalToken
                  ? t("settings.ray_secret_will_clear")
                  : server?.has_modal_token
                    ? t("settings.modal_token_stored")
                    : t("settings.modal_token_hint")
              }
            >
              <Input
                aria-label={t("settings.modal_token_id")}
                type="password"
                value={draft?.modalTokenId ?? ""}
                className="w-full font-mono @2xl:w-72"
                placeholder={
                  server?.has_modal_token && !draft?.clearModalToken
                    ? SECRET_MASK
                    : "ak-…"
                }
                autoComplete="off"
                disabled={busy}
                onChange={(event) =>
                  update({
                    modalTokenId: event.target.value,
                    clearModalToken: false,
                  })
                }
              />
            </SettingsRow>
            <SettingsRow
              id="modal-token-secret"
              title={t("settings.modal_token_secret")}
              description={
                draft?.clearModalToken
                  ? t("settings.ray_secret_will_clear")
                  : server?.has_modal_token
                    ? t("settings.modal_token_stored")
                    : t("settings.modal_token_hint")
              }
            >
              <Input
                aria-label={t("settings.modal_token_secret")}
                type="password"
                value={draft?.modalTokenSecret ?? ""}
                className="w-full font-mono @2xl:w-72"
                placeholder={
                  server?.has_modal_token && !draft?.clearModalToken
                    ? SECRET_MASK
                    : "as-…"
                }
                autoComplete="off"
                disabled={busy}
                onChange={(event) =>
                  update({
                    modalTokenSecret: event.target.value,
                    clearModalToken: false,
                  })
                }
              />
              {server?.has_modal_token && (
                <Button
                  variant="ghost"
                  disabled={busy || draft?.clearModalToken}
                  onClick={() =>
                    update({
                      modalTokenId: "",
                      modalTokenSecret: "",
                      clearModalToken: true,
                    })
                  }
                >
                  {t("settings.modal_clear_token")}
                </Button>
              )}
            </SettingsRow>
          </>
        )}

        <SettingsRow
          id="ray-save"
          title={t("settings.ray_save_title")}
          description={t("settings.ray_save_hint")}
        >
          {saveButton}
          {savedNote(true)}
        </SettingsRow>

        <SettingsRow
          id="ray-test"
          title={t("settings.ray_test")}
          description={t(
            modal ? "settings.modal_test_hint" : "settings.ray_test_hint",
          )}
        >
          <Button
            variant="outline"
            disabled={
              busy ||
              dirty ||
              (modal
                ? !server?.has_modal_token
                : !(draft?.dashboardUrl ?? "").trim())
            }
            onClick={() => void testConnection()}
          >
            {testing ? (
              <LoaderCircleIcon className="animate-spin" />
            ) : (
              <PlugIcon />
            )}
            {testing ? t("settings.ray_testing") : t("settings.ray_test")}
          </Button>
          {dirty && !testing && (
            <span className="text-xs text-muted-foreground">
              {t("settings.ray_test_save_first")}
            </span>
          )}
          {testResult && (
            <span
              role="status"
              title={testResult.message}
              className={
                testResult.ok
                  ? "text-xs text-emerald-500"
                  : "text-xs text-destructive"
              }
            >
              {(savedModal ? modalKindMessage : kindMessage)(
                testResult.ok ? "ok" : testResult.kind,
              )}
            </span>
          )}
        </SettingsRow>

        {authDisabled && !savedModal && (
          <div className="p-4">
            <div
              role="alert"
              className="flex gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-destructive"
            >
              <ShieldAlertIcon
                className="mt-0.5 size-5 shrink-0"
                aria-hidden="true"
              />
              <div className="space-y-1">
                <p className="text-sm font-semibold">
                  {t("settings.ray_auth_disabled_title")}
                </p>
                <p className="text-sm">
                  {t("settings.ray_auth_disabled_body")}
                </p>
              </div>
            </div>
          </div>
        )}

        {testResult &&
          (testResult.message ||
            otherWarnings.length > 0 ||
            testResult.ray_version ||
            testResult.node) && (
            <div className="space-y-3 p-4 text-sm">
              {testResult.message && !testResult.ok && (
                <p className="whitespace-pre-wrap break-words font-mono text-xs text-muted-foreground">
                  {testResult.message}
                </p>
              )}
              {otherWarnings.map((warning) => (
                <p
                  key={warning}
                  className="text-xs text-amber-600 dark:text-amber-400"
                >
                  {t("settings.ray_warning", { warning })}
                </p>
              ))}
              <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-xs">
                {testResult.ray_version && (
                  <>
                    <dt className="text-muted-foreground">
                      {t("settings.ray_info_version")}
                    </dt>
                    <dd className="font-mono">{testResult.ray_version}</dd>
                  </>
                )}
                {(testResult.cluster_python || testResult.node?.python) && (
                  <>
                    <dt className="text-muted-foreground">
                      {t("settings.ray_info_python")}
                    </dt>
                    <dd className="font-mono">
                      {testResult.cluster_python || testResult.node?.python}
                    </dd>
                  </>
                )}
                {testResult.cluster_status && (
                  <>
                    <dt className="text-muted-foreground">
                      {t("settings.ray_info_status")}
                    </dt>
                    <dd className="max-h-48 overflow-auto whitespace-pre-wrap font-mono">
                      {testResult.cluster_status}
                    </dd>
                  </>
                )}
                {testResult.node && (
                  <>
                    <dt className="text-muted-foreground">
                      {t("settings.ray_info_gpus")}
                    </dt>
                    <dd>
                      {testResult.node.gpus?.length ? (
                        <ul className="space-y-0.5">
                          {testResult.node.gpus.map((gpu, index) => (
                            <li key={`${gpu.name}-${index}`}>
                              {t("settings.ray_info_gpu_free", {
                                name: gpu.name,
                                free: gb(gpu.free_mb),
                                total: gb(gpu.total_mb),
                              })}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        t("settings.ray_info_no_gpu")
                      )}
                    </dd>
                  </>
                )}
                {testResult.node?.cache_free_gb != null && (
                  <>
                    <dt className="text-muted-foreground">
                      {t("settings.ray_info_cache")}
                    </dt>
                    <dd>
                      {t("settings.ray_info_cache_free", {
                        free: testResult.node.cache_free_gb.toFixed(1),
                        path: testResult.node.cache_dir || "—",
                      })}
                    </dd>
                  </>
                )}
                {testResult.latency_ms != null && (
                  <>
                    <dt className="text-muted-foreground">
                      {t("settings.ray_info_latency")}
                    </dt>
                    <dd>
                      {t("settings.ray_info_ms", {
                        ms: Math.round(testResult.latency_ms),
                      })}
                    </dd>
                  </>
                )}
              </dl>
            </div>
          )}
      </SettingsSection>

      <SettingsSection icon={CpuIcon} title={t("settings.ray_engines")}>
        <SettingsRow
          id="ray-engines"
          title={t(
            modal
              ? "settings.modal_engines_title"
              : "settings.ray_engines_title",
          )}
          description={
            <>
              <span className="block">
                {t(
                  modal
                    ? "settings.modal_engines_hint"
                    : "settings.ray_engines_hint",
                )}
              </span>
              <span className="block">
                {t(
                  modal
                    ? "settings.modal_engines_first_run"
                    : "settings.ray_engines_first_run",
                )}
              </span>
            </>
          }
        >
          {server && server.available_engines.length === 0 && (
            <span className="text-xs text-muted-foreground">
              {t("settings.ray_engines_none")}
            </span>
          )}
        </SettingsRow>
        {(
          [
            { kind: "tts", title: t("settings.ray_engines_group_tts") },
            {
              kind: "asr",
              title: t("settings.ray_engines_group_asr"),
              hint: t("settings.ray_engines_asr_hint"),
            },
            {
              kind: "translation",
              title: t("settings.ray_engines_group_translation"),
              hint: t("settings.ray_engines_translation_hint"),
            },
            {
              kind: "diarization",
              title: t("settings.ray_engines_group_diarization"),
              hint: t("settings.ray_engines_diarization_hint"),
            },
            {
              kind: "separation",
              title: t("settings.ray_engines_group_separation"),
              hint: t("settings.ray_engines_separation_hint"),
            },
          ] satisfies { kind: RayEngineKind; title: string; hint?: string }[]
        ).map((group) => {
          const engines = (server?.available_engines ?? []).filter(
            (engine) => engineKind(engine) === group.kind,
          );
          if (engines.length === 0) return null;
          return (
            <div
              key={group.kind}
              role="group"
              aria-labelledby={`ray-engines-${group.kind}`}
              aria-describedby={
                group.hint ? `ray-engines-${group.kind}-hint` : undefined
              }
              className="py-1"
            >
              <h3
                id={`ray-engines-${group.kind}`}
                className="px-4 pt-2 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase"
              >
                {group.title}
              </h3>
              {engines.map((engine) => (
                <label
                  key={engine.id}
                  className="flex cursor-pointer items-center gap-3 px-4 py-2.5 text-sm"
                >
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-primary"
                    checked={draft?.engines.includes(engine.id) ?? false}
                    disabled={busy}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      const current = draft?.engines ?? [];
                      update({
                        engines: checked
                          ? [...current, engine.id]
                          : current.filter((id) => id !== engine.id),
                      });
                    }}
                  />
                  <span className="font-mono">{engine.id}</span>
                  <Badge variant={engine.gpu ? "default" : "secondary"}>
                    {engine.gpu
                      ? t("settings.ray_badge_gpu")
                      : t("settings.ray_badge_cpu")}
                  </Badge>
                </label>
              ))}
              {group.hint && (
                <p
                  id={`ray-engines-${group.kind}-hint`}
                  className="px-4 pt-1 pb-2 text-xs text-muted-foreground"
                >
                  {group.hint}
                </p>
              )}
            </div>
          );
        })}
      </SettingsSection>

      <SettingsSection icon={ServerCogIcon} title={t("settings.ray_resources")}>
        {modal && (
          <SettingsRow
            id="modal-gpu"
            title={t("settings.modal_gpu")}
            description={t("settings.modal_gpu_hint")}
          >
            <Select
              items={gpuItems}
              value={draft?.modalGpu || MODAL_CPU}
              disabled={busy || !draft}
              onValueChange={(value) => {
                if (typeof value !== "string") return;
                update({ modalGpu: value === MODAL_CPU ? "" : value });
              }}
            >
              <SelectTrigger
                aria-label={t("settings.modal_gpu")}
                className="w-44"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {gpuItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </SettingsRow>
        )}
        {!modal && (
          <SettingsRow
            id="ray-num-gpus"
            title={t("settings.ray_num_gpus")}
            description={t("settings.ray_num_gpus_hint")}
          >
            <Input
              aria-label={t("settings.ray_num_gpus")}
              type="number"
              min={0}
              max={8}
              step={0.05}
              value={draft?.numGpus ?? ""}
              className="w-28 font-mono"
              disabled={busy}
              onChange={(event) => update({ numGpus: event.target.value })}
            />
          </SettingsRow>
        )}
        <SettingsRow
          id="ray-num-cpus"
          title={t("settings.ray_num_cpus")}
          description={t("settings.ray_num_cpus_hint")}
        >
          <Input
            aria-label={t("settings.ray_num_cpus")}
            type="number"
            min={0.1}
            max={64}
            step={0.5}
            value={draft?.numCpus ?? ""}
            className="w-28 font-mono"
            disabled={busy}
            onChange={(event) => update({ numCpus: event.target.value })}
          />
        </SettingsRow>
        {modal && (
          <>
            <SettingsRow
              id="modal-app"
              title={t("settings.modal_app")}
              description={t("settings.modal_app_hint")}
            >
              <Input
                aria-label={t("settings.modal_app")}
                value={draft?.modalApp ?? ""}
                className="w-full font-mono @2xl:w-72"
                placeholder="voicestudio"
                disabled={busy}
                onChange={(event) => update({ modalApp: event.target.value })}
              />
            </SettingsRow>
            <SettingsRow
              id="modal-volume"
              title={t("settings.modal_volume")}
              description={t("settings.modal_volume_hint")}
            >
              <Input
                aria-label={t("settings.modal_volume")}
                value={draft?.modalVolume ?? ""}
                className="w-full font-mono @2xl:w-72"
                placeholder="voicestudio-cache"
                disabled={busy}
                onChange={(event) =>
                  update({ modalVolume: event.target.value })
                }
              />
            </SettingsRow>
          </>
        )}
        {!modal && (
          <>
            <SettingsRow
              id="ray-cache-dir"
              title={t("settings.ray_cache_dir")}
              description={t("settings.ray_cache_dir_hint")}
            >
              <Input
                aria-label={t("settings.ray_cache_dir")}
                value={draft?.cacheDir ?? ""}
                className="w-full font-mono @2xl:w-96"
                placeholder="/mnt/cache/voicestudio"
                disabled={busy}
                onChange={(event) => update({ cacheDir: event.target.value })}
              />
            </SettingsRow>
            <SettingsRow
              id="ray-python"
              title={t("settings.ray_python")}
              description={t("settings.ray_python_hint")}
            >
              <Input
                aria-label={t("settings.ray_python")}
                value={draft?.python ?? ""}
                className="w-full font-mono @2xl:w-72"
                placeholder="python3"
                disabled={busy}
                onChange={(event) => update({ python: event.target.value })}
              />
            </SettingsRow>
            <SettingsRow
              id="ray-keep-failed"
              title={t("settings.ray_keep_failed")}
              description={t("settings.ray_keep_failed_hint")}
            >
              <Switch
                aria-label={t("settings.ray_keep_failed")}
                checked={draft?.keepFailed ?? false}
                disabled={busy || !draft}
                onCheckedChange={(keepFailed) => update({ keepFailed })}
              />
            </SettingsRow>
          </>
        )}
        <SettingsRow
          id="ray-save-resources"
          title={t("settings.ray_save_title")}
          titleHidden
        >
          {saveButton}
          {savedNote(false)}
        </SettingsRow>
      </SettingsSection>

      {!modal && (
        <SettingsSection icon={ListChecksIcon} title={t("settings.ray_jobs")}>
          <SettingsRow
            id="ray-jobs"
            title={t("settings.ray_jobs_title")}
            description={
              server?.enabled
                ? t("settings.ray_jobs_hint")
                : t("settings.ray_jobs_disabled")
            }
          >
            <Button
              variant="outline"
              disabled={!server?.enabled || jobs.isFetching}
              onClick={() => void jobs.refetch()}
            >
              {jobs.isFetching ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <RefreshCwIcon />
              )}
              {t("common.refresh")}
            </Button>
          </SettingsRow>
          {rayJobs && jobs.isError && (
            <div className="p-4">
              <SettingsActionError
                title={t("settings.ray_jobs_failed")}
                detail={describeError(jobs.error)}
              />
            </div>
          )}
          {rayJobs && jobs.data && !jobs.data.ok && (
            <div className="p-4">
              <SettingsActionError
                title={kindMessage(jobs.data.kind ?? "error")}
                detail={jobs.data.message}
              />
            </div>
          )}
          {rayJobs && jobs.data?.ok && jobList.length === 0 && (
            <p className="px-4 py-3 text-sm text-muted-foreground">
              {t("settings.ray_jobs_empty")}
            </p>
          )}
          {rayJobs && jobList.length > 0 && (
            <div className="overflow-x-auto p-2">
              <table className="w-full min-w-[40rem] text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5 font-medium">
                      {t("settings.ray_job_status")}
                    </th>
                    <th className="px-2 py-1.5 font-medium">
                      {t("settings.ray_job_engine")}
                    </th>
                    <th className="px-2 py-1.5 font-medium">
                      {t("settings.ray_job_op")}
                    </th>
                    <th className="px-2 py-1.5 font-medium">
                      {t("settings.ray_job_started")}
                    </th>
                    <th className="px-2 py-1.5 font-medium">
                      {t("settings.ray_job_ended")}
                    </th>
                    <th className="px-2 py-1.5 font-medium">
                      {t("settings.ray_job_message")}
                    </th>
                    <th className="px-2 py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {jobList.map((job) => (
                    <tr
                      key={job.submission_id}
                      className="border-t border-border/50 align-top"
                    >
                      <td
                        className="px-2 py-1.5 font-mono"
                        title={job.submission_id}
                      >
                        {job.status}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {job.engine || "—"}
                      </td>
                      <td className="px-2 py-1.5 font-mono">{job.op || "—"}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap">
                        {formatTime(job.start_time)}
                      </td>
                      <td className="px-2 py-1.5 whitespace-nowrap">
                        {formatTime(job.end_time)}
                      </td>
                      <td className="max-w-64 break-words px-2 py-1.5 text-muted-foreground">
                        {job.message || ""}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        {STOPPABLE.has(job.status) && (
                          <Button
                            size="sm"
                            variant="outline"
                            aria-label={t("settings.ray_job_stop", {
                              id: job.submission_id,
                            })}
                            disabled={stopping !== null}
                            onClick={() => void stopJob(job.submission_id)}
                          >
                            {stopping === job.submission_id ? (
                              <LoaderCircleIcon className="animate-spin" />
                            ) : (
                              <SquareIcon />
                            )}
                            {t("common.stop")}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SettingsSection>
      )}
    </>
  );
}
