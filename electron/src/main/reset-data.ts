import { lstat, readdir, realpath, rm } from 'node:fs/promises';
import { lstatSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, isAbsolute, join, parse, relative, resolve, sep } from 'node:path';

export const FRONTEND_RESET_SCOPES = ['ui_prefs', 'history'] as const;
export const DISK_RESET_SCOPES = [
  'settings',
  'content',
  'engines',
  'tools',
  'models',
  'caches',
  'logs',
] as const;
export type DiskResetScope = (typeof DISK_RESET_SCOPES)[number];

export interface ResetRoots {
  data: string;
  models: string;
  logs: string | null;
  temp: string;
}

export interface ResetScope {
  key: string;
  paths: string[];
  size_bytes: number;
  exists: boolean;
  shared: boolean;
  needs_restart: boolean;
}

export interface ResetReport {
  removed: string[];
  failed: string[];
  refused: string[];
  freed_bytes: number;
  restarted: boolean;
}

async function stat(path: string) {
  try {
    return await lstat(path);
  } catch {
    return null;
  }
}

export async function directorySize(path: string): Promise<number> {
  const info = await stat(path);
  if (!info || info.isSymbolicLink()) return 0;
  if (info.isFile()) return info.size;
  if (!info.isDirectory()) return 0;
  let children;
  try {
    children = await readdir(path, { withFileTypes: true });
  } catch {
    return 0;
  }
  const sizes = await Promise.all(
    children.map((entry) => (entry.isSymbolicLink() ? 0 : directorySize(join(path, entry.name)))),
  );
  return sizes.reduce((sum, size) => sum + size, 0);
}

async function prefixedChildren(path: string, prefix: string): Promise<string[]> {
  try {
    return (await readdir(path, { withFileTypes: true }))
      .filter((entry) => entry.name.startsWith(prefix))
      .map((entry) => join(path, entry.name))
      .sort();
  } catch {
    return [];
  }
}

function components(path: string): string[] {
  const root = parse(path).root;
  return path
    .slice(root.length)
    .split(/[\\/]+/)
    .filter(Boolean);
}

export function normalized(path: string): string {
  const value = resolve(path);
  return process.platform === 'win32' ? value.toLocaleLowerCase('en-US') : value;
}

export async function physicalPath(path: string): Promise<string | null> {
  if (!isAbsolute(path)) return null;
  try {
    return normalized(await realpath(path));
  } catch {
    return null;
  }
}

export function within(path: string, root: string): boolean {
  const rel = relative(normalized(root), normalized(path));
  return rel === '' || (rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

async function hasAppSignature(path: string, includeCacheMarkers = true): Promise<boolean> {
  if (
    hasRuntimeProjectSignature(path) ||
    hasRuntimeProjectSignature(join(path, 'project')) ||
    hasRuntimeProjectSignature(join(path, 'runtime', 'project'))
  )
    return true;
  for (const marker of ['omnivoice.db', 'prefs.json', 'voices', 'outputs', 'engines']) {
    if (await stat(join(path, marker))) return true;
  }
  if (!includeCacheMarkers) return false;
  const hub = await stat(join(path, 'hub'));
  if (hub?.isDirectory()) return true;
  try {
    return (await readdir(path)).some((name) => name.startsWith('models--'));
  } catch {
    return false;
  }
}

function hasRuntimeProjectSignature(project: string): boolean {
  try {
    if (
      !lstatSync(project).isDirectory() ||
      !lstatSync(join(project, 'backend')).isDirectory() ||
      !lstatSync(join(project, 'backend', 'main.py')).isFile() ||
      !lstatSync(join(project, 'uv.lock')).isFile()
    )
      return false;
    const ready = join(project, '.runtime-ready');
    const metadata = join(project, 'pyproject.toml');
    const readyInfo = lstatSync(ready);
    const metadataInfo = lstatSync(metadata);
    if (
      !readyInfo.isFile() ||
      readyInfo.size > 128 ||
      !metadataInfo.isFile() ||
      metadataInfo.size > 65536
    )
      return false;
    if (!/^[a-f0-9]{64}$/.test(readFileSync(ready, 'utf8').trim())) return false;
    let inProject = false;
    for (const raw of readFileSync(metadata, 'utf8').split(/\r?\n/)) {
      const line = raw.split('#', 1)[0].trim();
      if (line.startsWith('[')) inProject = line === '[project]';
      else if (inProject && /^name\s*=\s*(["'])omnivoice\1$/.test(line)) return true;
    }
  } catch {
    return false;
  }
  return false;
}

function isAppRoot(path: string): boolean {
  return [
    'omnivoice',
    '.omnivoice',
    'voicestudio',
    'com.debpalash.omnivoice-studio',
    'omnivoicestudio-data',
  ].includes(basename(path).toLocaleLowerCase('en-US'));
}

function isPrivateCacheRoot(path: string): boolean {
  return (
    ['models', 'hf_cache'].includes(basename(path).toLocaleLowerCase('en-US')) &&
    (isAppRoot(dirname(path)) || hasRuntimeProjectSignature(join(dirname(path), 'project')))
  );
}

function isManagedLayout(path: string, includeSharedCaches = true): boolean {
  const name = basename(path).toLocaleLowerCase('en-US');
  const parent = dirname(path);
  const parentName = basename(parent).toLocaleLowerCase('en-US');
  if (name === 'hub')
    return (includeSharedCaches && parentName === 'huggingface') || isPrivateCacheRoot(parent);
  const runtimeChildren = ['project', '.uv-cache', '.python', '.tmp', 'tmp'];
  if (runtimeChildren.includes(name) && parentName === 'runtime' && isAppRoot(dirname(parent)))
    return true;
  return (
    ['data', 'logs', 'runtime', 'models', 'hf_cache', ...runtimeChildren].includes(name) &&
    (isAppRoot(parent) || hasRuntimeProjectSignature(join(parent, 'project')))
  );
}

export async function isValidVoiceStudioRoot(path: string, home: string | null): Promise<boolean> {
  if (!isAbsolute(path)) return false;
  const [candidate, physicalHome] = await Promise.all([
    physicalPath(path),
    home ? physicalPath(home) : null,
  ]);
  if (!candidate || (home && !physicalHome)) return false;
  if (dirname(candidate) === candidate || components(candidate).length < 2) return false;
  if (physicalHome && candidate === physicalHome) return false;
  return (
    isAppRoot(candidate) ||
    basename(candidate).toLocaleLowerCase('en-US') === 'huggingface' ||
    isManagedLayout(candidate) ||
    hasAppSignature(candidate)
  );
}

export async function modelsAreShared(
  models: string,
  data: string,
  home: string | null = homedir(),
): Promise<boolean> {
  const [candidate, physicalData, physicalHome] = await Promise.all([
    physicalPath(models),
    physicalPath(data),
    home ? physicalPath(home) : null,
  ]);
  if (!candidate || (home && !physicalHome) || candidate === physicalHome) return true;
  if (
    physicalData &&
    within(candidate, physicalData) &&
    (await isAppOwnedRoot(physicalData, physicalHome))
  )
    return false;
  return !(
    isPrivateCacheRoot(candidate) ||
    (basename(candidate).toLocaleLowerCase('en-US') === 'hub' &&
      isPrivateCacheRoot(dirname(candidate)))
  );
}

export async function isAppOwnedRoot(path: string, home: string | null): Promise<boolean> {
  const candidate = await physicalPath(path);
  return Boolean(
    candidate &&
    (await isValidVoiceStudioRoot(candidate, home)) &&
    (isAppRoot(candidate) ||
      isManagedLayout(candidate, false) ||
      (await hasAppSignature(candidate, false))),
  );
}

async function scopeTargets(key: DiskResetScope, roots: ResetRoots): Promise<string[]> {
  switch (key) {
    case 'settings':
      return [join(roots.data, 'prefs.json')];
    case 'content':
      return [
        join(roots.data, 'voices'),
        join(roots.data, 'outputs'),
        join(roots.data, 'dub_jobs'),
        join(roots.data, 'batch'),
        join(roots.data, 'preview'),
        ...(await prefixedChildren(roots.data, 'omnivoice.db')),
      ];
    case 'engines':
      return [join(roots.data, 'engines')];
    case 'tools':
      return [join(roots.data, 'media_tools')];
    case 'models':
      return [roots.models];
    case 'caches':
      return [
        join(roots.data, 'gallery_cache'),
        join(roots.data, 'gallery_sources.json'),
        ...(await prefixedChildren(roots.temp, 'omnivoice')),
      ];
    case 'logs':
      return [
        join(roots.data, 'crash_log.txt'),
        join(roots.data, 'error_journal.jsonl'),
        ...(await prefixedChildren(roots.data, 'omnivoice.log')),
        ...(roots.logs ? [roots.logs] : []),
      ];
  }
}

async function allowedTarget(
  path: string,
  key: DiskResetScope,
  roots: ResetRoots,
  home: string | null,
): Promise<boolean> {
  if (key === 'models')
    return within(path, roots.models) && isValidVoiceStudioRoot(roots.models, home);
  if (
    key === 'caches' &&
    normalized(dirname(path)) === normalized(roots.temp) &&
    basename(path).toLocaleLowerCase('en-US').startsWith('omnivoice')
  ) {
    return true;
  }
  for (const root of [roots.data, roots.logs].filter((value): value is string => Boolean(value))) {
    if (within(path, root) && (await isAppOwnedRoot(root, home))) return true;
  }
  return false;
}

async function overlapsSharedModels(path: string, models: string | null): Promise<boolean> {
  if (!models) return false;
  const candidate = await physicalPath(path);
  return Boolean(candidate && (within(candidate, models) || within(models, candidate)));
}

export async function scanResetScopes(
  roots: ResetRoots,
  home: string | null = homedir(),
): Promise<ResetScope[]> {
  const scopes: ResetScope[] = FRONTEND_RESET_SCOPES.map((key) => ({
    key,
    paths: [],
    size_bytes: 0,
    exists: true,
    shared: false,
    needs_restart: false,
  }));
  const sharedModels = await modelsAreShared(roots.models, roots.data, home);
  const sharedModelRoot = sharedModels ? await physicalPath(roots.models) : null;
  for (const key of DISK_RESET_SCOPES) {
    const targets = await scopeTargets(key, roots);
    const present: string[] = [];
    for (const target of targets) if (await stat(target)) present.push(target);
    const sizes = await Promise.all(present.map(directorySize));
    scopes.push({
      key,
      paths: present,
      size_bytes: sizes.reduce((sum, size) => sum + size, 0),
      exists: present.length > 0,
      shared:
        key === 'models'
          ? sharedModels
          : (
              await Promise.all(present.map((path) => overlapsSharedModels(path, sharedModelRoot)))
            ).some(Boolean),
      needs_restart: true,
    });
  }
  return scopes;
}

export async function purgeResetScopes(
  roots: ResetRoots,
  requested: string[],
  home: string | null,
): Promise<ResetReport> {
  const report: ResetReport = {
    removed: [],
    failed: [],
    refused: [],
    freed_bytes: 0,
    restarted: false,
  };
  const wanted = DISK_RESET_SCOPES.filter((key) => requested.includes(key));
  const modelsSelected = wanted.includes('models');
  const sharedModelRoot = (await modelsAreShared(roots.models, roots.data, home))
    ? await physicalPath(roots.models)
    : null;
  const targets: string[] = [];
  for (const key of wanted) {
    for (const target of await scopeTargets(key, roots)) {
      if (!(await stat(target))) continue;
      if (
        !(await allowedTarget(target, key, roots, home)) ||
        (!modelsSelected && (await overlapsSharedModels(target, sharedModelRoot)))
      ) {
        report.refused.push(target);
        continue;
      }
      targets.push(target);
    }
  }
  for (const target of targets) {
    const size = await directorySize(target);
    try {
      await rm(target, { recursive: true, force: true, maxRetries: 2, retryDelay: 100 });
      report.removed.push(target);
      report.freed_bytes += size;
    } catch {
      report.failed.push(target);
    }
  }
  return report;
}
