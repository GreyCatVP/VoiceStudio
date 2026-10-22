type CheckStatus = 'pass' | 'warn' | 'fail';

interface PreflightCheck {
  id: string;
  label: string;
  status: CheckStatus;
  detail: string;
  fix: string | null;
  /** GPU check only: offered when there is no local GPU and no remote GPU is set up. */
  choices?: GpuChoice[];
  /** GPU check only: where GPU work goes while remote execution is active. */
  remote?: PreflightRemote;
}

export type GpuChoice = 'cpu' | 'ray' | 'modal';

export interface PreflightRemote {
  provider: 'ray' | 'modal';
  /** Modal GPU type; null for Ray, or when Modal runs GPU engines on CPU. */
  gpu: string | null;
  /** Number of engines routed to the remote provider. */
  engines: number;
}

interface PreflightDevice {
  os: string;
  arch: string;
  gpu_vendor: 'nvidia' | 'amd' | 'apple' | 'intel' | 'unknown' | 'none';
  gpu_backend: 'cuda' | 'rocm' | 'mps' | 'cpu';
  gpu_available: boolean;
  gpu_driver: string | null;
  gpu_device_name: string | null;
  ram_gb: number;
  disk_free_gb: number;
}

export interface PreflightReport {
  ok: boolean;
  has_warnings: boolean;
  checks: PreflightCheck[];
  device: PreflightDevice;
}
