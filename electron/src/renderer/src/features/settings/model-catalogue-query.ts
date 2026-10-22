import { useQuery } from '@tanstack/react-query';
import { apiJson } from '@/lib/api/client';
import { useBackendStatus } from '@/hooks/use-backend-status';
import { isBackendReachable } from '@shared/utils/backendStage';
import type { ModelLicenseInfo, ModelLicenceAcceptance } from './model-license-contract';

export interface CatalogueModel {
  repo_id: string;
  label: string;
  role: string;
  families?: string[];
  size_gb: number;
  installed: boolean;
  supported: boolean;
  dictation_id?: string;
  required?: boolean;
  curated?: boolean;
  incomplete?: boolean;
  size_on_disk_bytes?: number;
  note?: string;
  /** ISO 639-1 codes of a language-specific model (models.yaml `languages`). */
  languages?: string[];
  gated?: boolean;
  requires_hf_token?: boolean;
  access_url?: string;
  prerequisite_repo_id?: string;
  prerequisite_access_url?: string;
  failure_topic?: string;
  /** Versioned disclosure; absence is unverified, never a permission grant. */
  license_info?: ModelLicenseInfo;
  license_acceptance?: ModelLicenceAcceptance;
}

export interface ModelCatalogueResponse {
  models: CatalogueModel[];
  total_installed_bytes?: number;
  disk_free_gb?: number;
  /** Free space the backend keeps on top of every model download. */
  disk_headroom_gb?: number;
}

/** Repos the faster-whisper engines load: CTranslate2 builds, or a checkpoint
 * they convert on first use (backend `faster_whisper_selectable`). */
export const isFasterWhisperModel = (repoId: string) =>
  repoId.startsWith('Systran/faster-') ||
  repoId === 'deepdml/faster-whisper-large-v3-turbo-ct2' ||
  repoId === 'typhoon-ai/typhoon-whisper-turbo';

export function useModelCatalogue() {
  const status = useBackendStatus();
  return useQuery({
    queryKey: ['model-catalogue'],
    queryFn: () => apiJson<ModelCatalogueResponse>('/models'),
    staleTime: 30_000,
    enabled: isBackendReachable(status.stage),
  });
}
