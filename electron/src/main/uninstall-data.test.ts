// @vitest-environment node
import { mkdtemp, mkdir, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, expect, it } from 'vitest';
import {
  createUninstallPlan,
  scanUninstallTargets,
  type UninstallRoots,
  type UninstallTarget,
} from './uninstall-data';
import { within } from './reset-data';

const created: string[] = [];
afterEach(async () => {
  await Promise.allSettled(
    created.splice(0).map((path) => rm(path, { recursive: true, force: true })),
  );
});

async function fixture(): Promise<UninstallRoots & { root: string }> {
  const root = await mkdtemp(join(tmpdir(), 'VoiceStudio-uninstall-test-'));
  created.push(root);
  const roots = {
    root,
    data: join(root, 'OmniVoice', 'data'),
    environment: join(root, 'appdata', 'VoiceStudio'),
    logs: join(root, 'OmniVoice', 'logs'),
    userEnvironment: join(root, '.config', 'omnivoice'),
    models: join(root, '.cache', 'huggingface'),
  };
  for (const path of Object.values(roots).filter((value) => value !== root)) {
    await mkdir(path, { recursive: true });
    await writeFile(join(path, 'fixture.bin'), 'data');
  }
  await mkdir(join(root, 'home'));
  return roots;
}

it('scans every install-owned location and keeps a shared model cache opt-in', async () => {
  const roots = await fixture();
  const targets = await scanUninstallTargets(roots);
  expect(targets.map((target) => target.key)).toEqual(['data', 'env', 'logs', 'userenv', 'models']);
  expect(targets.every((target) => target.exists && target.size_bytes === 4)).toBe(true);
  expect(targets.find((target) => target.key === 'models')?.shared).toBe(true);
  expect((await createUninstallPlan(targets, false, join(roots.root, 'home'))).paths).not.toContain(
    roots.models,
  );
  expect((await createUninstallPlan(targets, true, join(roots.root, 'home'))).paths).toContain(
    roots.models,
  );
});

it('refuses unsigned arbitrary roots and collapses descendants under an owned parent', async () => {
  const roots = await fixture();
  const arbitrary = join(roots.root, 'personal', 'documents');
  await mkdir(arbitrary, { recursive: true });
  const targets = await scanUninstallTargets({
    ...roots,
    data: arbitrary,
    logs: join(roots.environment, 'logs'),
  });
  const plan = await createUninstallPlan(targets, false, join(roots.root, 'home'));
  expect(plan.refused).toContain(arbitrary);
  expect(plan.paths).toContain(roots.environment);
  expect(plan.paths).not.toContain(join(roots.environment, 'logs'));
});

it('does not offer a nested private model directory as a separately shared target', async () => {
  const roots = await fixture();
  await mkdir(join(roots.environment, 'models'));
  const targets = await scanUninstallTargets({
    ...roots,
    models: join(roots.environment, 'models'),
  });
  expect(targets.some((target) => target.key === 'models')).toBe(false);
});

it('lists a setup-chosen location by its runtime folders so data and models stay separate choices (#2971)', async () => {
  const roots = await fixture();
  const chosen = join(roots.root, 'E', 'VoiceStudio');
  const data = join(chosen, 'data');
  const entries = [join(chosen, 'project'), join(chosen, '.uv-cache')];
  for (const path of [data, ...entries]) await mkdir(path, { recursive: true });
  const targets = await scanUninstallTargets({
    ...roots,
    data,
    models: join(chosen, 'models'),
    runtimeEnvironment: entries,
  });
  const paths = targets.map((target) => target.path);
  expect(paths).toEqual(expect.arrayContaining([data, ...entries]));
  expect(paths).not.toContain(chosen);
  const plan = await createUninstallPlan(
    targets.filter((t) => t.path !== data),
    false,
    null,
  );
  expect(plan.paths).toEqual(expect.arrayContaining(entries));
  expect(plan.paths).not.toContain(data);
});

it('keeps a shared cache opt-in beneath an app-named workspace ancestor', async () => {
  const roots = await fixture();
  const models = join(roots.root, 'VoiceStudio', 'personal', '.cache', 'huggingface');
  await mkdir(models, { recursive: true });
  const targets = await scanUninstallTargets({ ...roots, models });
  expect(targets.find((target) => target.key === 'models')?.shared).toBe(true);
  expect((await createUninstallPlan(targets, false, null)).paths).not.toContain(models);
  expect((await createUninstallPlan(targets, true, null)).paths).toContain(models);
});

it('preserves custom owned runtime entries without selecting sibling user data', async () => {
  const roots = await fixture();
  const runtime = join(roots.root, 'Votest', 'VoiceStudio-AMD-20261025', 'runtime');
  const project = join(runtime, 'project');
  const entries = ['project', '.uv-cache', '.python', '.tmp', 'tmp'].map((name) =>
    join(runtime, name),
  );
  for (const path of [...entries, join(project, 'backend')]) await mkdir(path, { recursive: true });
  const python = join(runtime, '.python', 'cpython-3.12-windows-x86_64-none-3.12.12');
  await mkdir(python);
  await symlink(
    python,
    join(runtime, '.python', 'cpython-3.12-windows-x86_64-none'),
    process.platform === 'win32' ? 'junction' : 'dir',
  );
  await writeFile(join(project, '.runtime-ready'), 'a'.repeat(64));
  await writeFile(join(project, 'pyproject.toml'), '[project]\nname = "omnivoice"\n');
  await writeFile(join(project, 'uv.lock'), 'version = 1');
  await writeFile(join(project, 'backend', 'main.py'), 'app = None');
  const targets = await scanUninstallTargets({ ...roots, runtimeEnvironment: entries });
  const plan = await createUninstallPlan(
    targets.filter((target) => entries.includes(target.path)),
    false,
    null,
  );
  expect(plan.refused).toEqual([]);
  expect(plan.paths).toEqual(entries);
  expect(plan.paths).not.toContain(runtime);
  const wholeRoot = await scanUninstallTargets({ ...roots, runtimeEnvironment: runtime });
  expect((await createUninstallPlan(wholeRoot, false, null)).paths).toContain(runtime);
});

it.each(['home', 'unsigned'])(
  'preserves shared caches beneath a rejected %s data root',
  async (kind) => {
    const roots = await fixture();
    const home = join(roots.root, 'home');
    const data = kind === 'home' ? home : join(home, 'personal');
    const models = join(data, '.cache', 'huggingface');
    await mkdir(models, { recursive: true });
    await writeFile(join(models, 'unrelated.txt'), 'keep');
    if (kind === 'home') await writeFile(join(home, 'omnivoice.db'), 'db');
    const targets = await scanUninstallTargets({ ...roots, data, models }, home);
    expect(targets.find((target) => target.key === 'models')).toMatchObject({
      path: models,
      shared: true,
    });
    const plan = await createUninstallPlan(targets, false, home);
    expect(plan.refused).toContain(data);
    expect(plan.paths).not.toContain(models);
    expect(plan.paths).not.toContain(data);
    const explicit = await createUninstallPlan(targets, true, home);
    expect(explicit.paths).toContain(models);
  },
);

it.each(['private-layout', 'inside-data', 'inside-environment'])(
  'requires explicit selection for a %s models link to a recognized shared HF cache',
  async (placement) => {
    const roots = await fixture();
    const external = join(roots.root, 'external', 'huggingface');
    const parent =
      placement === 'inside-data'
        ? roots.data
        : placement === 'inside-environment'
          ? roots.environment
          : join(roots.root, 'VoiceStudio');
    const models = join(parent, 'models');
    await mkdir(parent, { recursive: true });
    await mkdir(external, { recursive: true });
    await writeFile(join(external, 'unrelated.txt'), 'keep');
    await symlink(external, models, process.platform === 'win32' ? 'junction' : 'dir');
    const targets = await scanUninstallTargets({ ...roots, models });
    expect(targets.find((target) => target.key === 'models')).toMatchObject({
      path: models,
      shared: true,
    });
    const automatic = await createUninstallPlan(targets, false, null);
    expect(automatic.refused).toEqual([]);
    const automaticPhysical = await Promise.all(automatic.paths.map((path) => realpath(path)));
    expect(automaticPhysical).not.toContain(await realpath(external));
    const explicit = await createUninstallPlan(targets, true, null);
    expect(explicit.refused).toEqual([]);
    const explicitPhysical = await Promise.all(explicit.paths.map((path) => realpath(path)));
    expect(explicitPhysical).toContain(await realpath(external));
    expect(await readFile(join(external, 'unrelated.txt'), 'utf8')).toBe('keep');
  },
);

it.each(['runtime', 'environment', 'logs', 'userenv', 'data', 'environment-direct'])(
  'preserves shared models before deduplicating a %s role at the same cache',
  async (role) => {
    const roots = await fixture();
    const external = join(roots.root, 'external', 'huggingface');
    const alias = join(roots.root, 'custom-runtime', '.uv-cache');
    await mkdir(external, { recursive: true });
    await mkdir(join(roots.root, 'custom-runtime'));
    await symlink(external, alias, process.platform === 'win32' ? 'junction' : 'dir');
    await writeFile(join(external, 'unrelated.txt'), 'keep');
    const override: Partial<UninstallRoots> =
      role === 'runtime'
        ? { runtimeEnvironment: alias }
        : role === 'environment-direct'
          ? { environment: external }
          : { [role === 'userenv' ? 'userEnvironment' : role]: alias };
    const targets = await scanUninstallTargets({ ...roots, ...override, models: external });
    expect(targets.find((target) => target.key === 'models')).toMatchObject({ shared: true });
    const physical = await realpath(external);
    const automatic = await createUninstallPlan(targets, false, null);
    expect(automatic.refused).toEqual([]);
    for (const path of automatic.paths) {
      const candidate = await realpath(path);
      expect(within(physical, candidate) || within(candidate, physical)).toBe(false);
    }
    const explicit = await createUninstallPlan(targets, true, null);
    expect(explicit.refused).toEqual([]);
    expect(await Promise.all(explicit.paths.map((path) => realpath(path)))).toContain(physical);
    expect(await readFile(join(external, 'unrelated.txt'), 'utf8')).toBe('keep');
  },
);

it.each(['parent-first', 'child-first'])(
  'retains the shared warning and opt-in across %s overlapping runtime roles',
  async (order) => {
    const roots = await fixture();
    const parent = join(roots.root, 'external', 'VoiceStudio');
    const models = join(parent, '.cache', 'huggingface');
    const child = join(models, 'hub');
    await mkdir(child, { recursive: true });
    const aliases = [join(roots.root, 'runtime-parent'), join(roots.root, 'runtime-child')];
    await symlink(parent, aliases[0], process.platform === 'win32' ? 'junction' : 'dir');
    await symlink(child, aliases[1], process.platform === 'win32' ? 'junction' : 'dir');
    const targets = await scanUninstallTargets({
      ...roots,
      models,
      runtimeEnvironment: order === 'parent-first' ? aliases : aliases.toReversed(),
    });
    expect(targets.find((target) => target.key === 'models')).toMatchObject({ shared: true });
    for (const target of targets.filter((target) => aliases.includes(target.path))) {
      expect(target.shared).toBe(true);
    }
    const automatic = await createUninstallPlan(targets, false, null);
    expect(automatic.refused).toEqual([]);
    const protectedPath = await realpath(models);
    for (const path of automatic.paths) {
      const candidate = await realpath(path);
      expect(within(protectedPath, candidate) || within(candidate, protectedPath)).toBe(false);
    }
    const explicit = await createUninstallPlan(targets, true, null);
    expect(explicit.refused).toEqual([]);
    expect(await Promise.all(explicit.paths.map((path) => realpath(path)))).toContain(
      await realpath(parent),
    );
  },
);

it.each(['same', 'parent', 'child'])(
  'enforces shared privacy in direct plans before filtering a %s role overlap',
  async (relation) => {
    const roots = await fixture();
    const parent = join(roots.root, 'external', 'VoiceStudio');
    const models = join(parent, '.cache', 'huggingface');
    const child = join(models, 'hub');
    await mkdir(child, { recursive: true });
    const destination = relation === 'same' ? models : relation === 'parent' ? parent : child;
    const alias = join(roots.root, 'runtime-alias');
    await symlink(destination, alias, process.platform === 'win32' ? 'junction' : 'dir');
    const targets: UninstallTarget[] = [
      { key: 'env', path: alias, size_bytes: 0, exists: true, shared: false },
      { key: 'models', path: models, size_bytes: 0, exists: true, shared: true },
    ];
    for (const rows of [targets, targets.toReversed()]) {
      expect((await createUninstallPlan(rows, false, null)).paths).toEqual([]);
      const explicit = await createUninstallPlan(rows, true, null);
      expect(explicit.refused).toEqual([]);
      expect(explicit.paths).toHaveLength(1);
    }
  },
);

it('keeps a private cache and independent managed runtime in the automatic plan', async () => {
  const roots = await fixture();
  const models = join(roots.root, 'VoiceStudio', 'models');
  const runtime = join(roots.root, 'VoiceStudio', '.uv-cache');
  await mkdir(models, { recursive: true });
  await mkdir(runtime);
  const targets = await scanUninstallTargets({ ...roots, models, runtimeEnvironment: runtime });
  expect(targets.every((target) => !target.shared)).toBe(true);
  const plan = await createUninstallPlan(targets, false, null);
  expect(plan.refused).toEqual([]);
  const physical = await Promise.all(plan.paths.map((path) => realpath(path)));
  expect(physical).toContain(await realpath(models));
  expect(physical).toContain(await realpath(runtime));
});

it.each(
  ['runtime', 'environment', 'logs', 'userenv', 'data'].flatMap((role) =>
    ['root', 'hub'].map((layout) => [role, layout] as const),
  ),
)('refuses a cache-only %s %s outside the configured model cache', async (role, layout) => {
  const roots = await fixture();
  const external = join(roots.root, 'other', 'huggingface');
  const alias = join(roots.root, 'other-cache-link');
  await mkdir(external, { recursive: true });
  const destination = layout === 'root' ? external : join(external, 'hub');
  await mkdir(destination, { recursive: true });
  await symlink(destination, alias, process.platform === 'win32' ? 'junction' : 'dir');
  const override: Partial<UninstallRoots> =
    role === 'runtime'
      ? { runtimeEnvironment: alias }
      : { [role === 'userenv' ? 'userEnvironment' : role]: alias };
  const targets = await scanUninstallTargets({ ...roots, ...override });
  for (const includeModels of [false, true]) {
    const plan = await createUninstallPlan(targets, includeModels, null);
    expect(plan.refused).toContain(alias);
    expect(plan.paths).not.toContain(alias);
  }
});

it('counts an opted-in shared cache once when its parent is the removal target', async () => {
  const roots = await fixture();
  const parent = join(roots.root, 'external', 'VoiceStudio');
  const models = join(parent, '.cache', 'huggingface');
  await mkdir(models, { recursive: true });
  await writeFile(join(parent, 'app.bin'), 'data');
  await writeFile(join(models, 'model.bin'), 'model');
  const targets: UninstallTarget[] = [
    { key: 'env', path: parent, size_bytes: 9, exists: true, shared: false },
    { key: 'models', path: models, size_bytes: 5, exists: true, shared: true },
  ];
  for (const rows of [targets, targets.toReversed()]) {
    const plan = await createUninstallPlan(rows, true, null);
    expect(plan.refused).toEqual([]);
    expect(plan.paths).toEqual([parent]);
    expect(plan.size_bytes).toBe(9);
  }
  expect(await readFile(join(models, 'model.bin'), 'utf8')).toBe('model');
});
