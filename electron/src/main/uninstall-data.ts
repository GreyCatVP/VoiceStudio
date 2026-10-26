import { lstat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { isAbsolute } from 'node:path';
import {
  directorySize,
  isAppOwnedRoot,
  isValidVoiceStudioRoot,
  modelsAreShared,
  normalized,
  physicalPath,
  within,
} from './reset-data';

export interface UninstallRoots {
  data: string;
  environment: string;
  /** The runtime Electron created; a list when data/models share its folder and must stay separate targets. */
  runtimeEnvironment?: string | string[] | null;
  logs: string | null;
  userEnvironment: string;
  models: string;
}

export interface UninstallTarget {
  key: 'data' | 'env' | 'logs' | 'userenv' | 'models';
  path: string;
  size_bytes: number;
  exists: boolean;
  shared: boolean;
}

export interface UninstallPlan {
  paths: string[];
  refused: string[];
  size_bytes: number;
}

async function exists(path: string): Promise<boolean> {
  try {
    await lstat(path);
    return true;
  } catch {
    return false;
  }
}

async function protectSharedTargets<T extends { path: string; shared: boolean }>(values: T[]) {
  const targets = await Promise.all(
    values.map(async (target) => ({
      ...target,
      physical: await physicalPath(target.path),
    })),
  );
  const pending = targets.filter((target) => target.shared && target.physical);
  while (pending.length) {
    const shared = pending.pop()!;
    for (const target of targets) {
      if (
        !target.shared &&
        target.physical &&
        shared.physical &&
        (within(target.physical, shared.physical) || within(shared.physical, target.physical))
      ) {
        target.shared = true;
        pending.push(target);
      }
    }
  }
  return targets;
}

async function uniqueRoots<T extends Pick<UninstallTarget, 'key' | 'path' | 'shared'>>(
  values: T[],
  home: string | null,
) {
  const protectedTargets = await protectSharedTargets(values);
  const grouped = new Map<string, (typeof protectedTargets)[number]>();
  for (const target of protectedTargets) {
    const key = target.physical ?? normalized(target.path);
    const previous = grouped.get(key);
    if (!previous || (target.shared && target.key === 'models')) grouped.set(key, target);
    else previous.shared ||= target.shared;
  }
  const targets = [...grouped.values()];
  const owned = await Promise.all(targets.map(({ path }) => isValidVoiceStudioRoot(path, home)));
  return targets.filter((target, index) => {
    if (target.shared && target.key === 'models') return true;
    return !targets.some(
      (parent, other) =>
        other !== index &&
        owned[other] &&
        parent.shared === target.shared &&
        parent.physical &&
        target.physical &&
        within(target.physical, parent.physical),
    );
  });
}

export async function scanUninstallTargets(
  roots: UninstallRoots,
  home: string | null = homedir(),
): Promise<UninstallTarget[]> {
  const sharedModels = await modelsAreShared(roots.models, roots.data, home);
  const candidates = await uniqueRoots(
    [
      { key: 'data', path: roots.data, shared: false },
      { key: 'env', path: roots.environment, shared: false },
      ...[roots.runtimeEnvironment ?? []].flat().map((path) => ({
        key: 'env' as const,
        path,
        shared: false,
      })),
      ...(roots.logs ? [{ key: 'logs' as const, path: roots.logs, shared: false }] : []),
      { key: 'userenv', path: roots.userEnvironment, shared: false },
      { key: 'models', path: roots.models, shared: sharedModels },
    ],
    home,
  );
  const targets: UninstallTarget[] = [];
  for (const { key, path, shared } of candidates) {
    const present = await exists(path);
    targets.push({
      key,
      path,
      shared,
      exists: present,
      size_bytes: present ? await directorySize(path) : 0,
    });
  }
  return targets;
}

export async function createUninstallPlan(
  targets: UninstallTarget[],
  includeModels: boolean,
  home: string | null,
): Promise<UninstallPlan> {
  const protectedTargets = await uniqueRoots(targets, home);
  const eligible = protectedTargets.filter(
    (target) => target.exists && (includeModels || !target.shared || target.key !== 'models'),
  );
  const refused: string[] = [];
  const accepted: Array<UninstallTarget & { physical: string }> = [];
  for (const target of eligible) {
    const physical = target.physical;
    const valid =
      physical &&
      (await (target.key === 'models'
        ? isValidVoiceStudioRoot(physical, home)
        : isAppOwnedRoot(physical, home)));
    if (!isAbsolute(target.path) || !physical || !valid) {
      refused.push(target.path);
    } else if (includeModels || !target.shared) {
      accepted.push({ ...target, physical });
    }
  }
  const selected = accepted.filter(
    (target, index) =>
      !accepted.some(
        (parent, other) =>
          other !== index &&
          within(target.physical, parent.physical) &&
          (parent.physical !== target.physical || other < index),
      ),
  );
  return {
    paths: selected.map((target) => target.path),
    refused,
    size_bytes: selected.reduce((sum, target) => sum + target.size_bytes, 0),
  };
}
