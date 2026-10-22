import { arch, cpus, release, totalmem, version } from 'node:os';
import { stat, statfs } from 'node:fs/promises';
import { dirname } from 'node:path';

export interface HostSnapshot {
  os: string;
  arch: string;
  cpu: string | null;
  ramGb: number;
  diskFreeGb: number | null;
  gpu: string | null;
  runtime: {
    pythonPresent: boolean | null;
    uvPresent: boolean | null;
    pathFlags: string[];
  };
}

export interface HostSnapshotInput {
  platform?: NodeJS.Platform;
  /** Runtime project directory (holds `.venv`); null when it cannot be resolved. */
  runtimeProject: string | null;
  runtimePython: string | null;
  uv: string | null;
  /** True when the uv search completed, so a null `uv` means "not installed". */
  uvSearched?: boolean;
  gpu?: () => Promise<string | null>;
}

/**
 * Path traits that explain launch failures (`spawn UNKNOWN`, access
 * violations, EPERM renames) without printing the path itself, which is
 * private. Stable tokens so triage can grep them.
 */
export function pathRiskFlags(
  path: string,
  platform: NodeJS.Platform = process.platform,
): string[] {
  const flags: string[] = [];
  if (/onedrive/i.test(path)) flags.push('onedrive');
  if (/[^\x00-\x7f]/.test(path)) flags.push('non-ascii');
  if (/\s/.test(path)) flags.push('spaces');
  if (platform === 'win32') {
    if (/^\\\\/.test(path)) flags.push('network-share');
    if (/[\\/]windows[\\/]system32/i.test(path)) flags.push('system32');
    else if (/[\\/]program files/i.test(path)) flags.push('program-files');
    if (path.length > 180) flags.push('long-path');
  }
  return flags;
}

async function exists(path: string | null): Promise<boolean | null> {
  if (!path) return null;
  try {
    return (await stat(path)).isFile();
  } catch {
    return false;
  }
}

async function freeGb(path: string | null): Promise<number | null> {
  if (!path) return null;
  // First run: the project dir does not exist yet, but its drive does.
  let probe = path;
  for (;;) {
    try {
      const fs = await statfs(probe);
      return Math.round(((fs.bavail * fs.bsize) / 1024 ** 3) * 10) / 10;
    } catch {
      const parent = dirname(probe);
      if (parent === probe) return null;
      probe = parent;
    }
  }
}

async function withTimeout<T>(task: Promise<T>, ms: number): Promise<T | null> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      task,
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), ms);
      }),
    ]);
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Machine and runtime facts read in the main process, so a bug report is
 * useful even when the backend never started and `/system/info` is unreachable. */
export async function collectHostSnapshot(input: HostSnapshotInput): Promise<HostSnapshot> {
  const platform = input.platform ?? process.platform;
  const [pythonPresent, uvPresent, diskFreeGb, gpu] = await Promise.all([
    withTimeout(exists(input.runtimePython), 1500),
    input.uv ? exists(input.uv) : Promise.resolve(input.uvSearched ? false : null),
    withTimeout(freeGb(input.runtimeProject), 1500),
    input.gpu ? withTimeout(input.gpu(), 1500) : Promise.resolve(null),
  ]);
  return {
    os: `${platform} ${version()} (${release()})`,
    arch: arch(),
    cpu: cpus()[0]?.model?.trim() || null,
    ramGb: Math.round((totalmem() / 1024 ** 3) * 10) / 10,
    diskFreeGb,
    gpu,
    runtime: {
      pythonPresent,
      uvPresent,
      pathFlags: input.runtimeProject ? pathRiskFlags(input.runtimeProject, platform) : [],
    },
  };
}
