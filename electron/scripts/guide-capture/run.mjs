// Capture the user guide's screenshots from a running web UI.
//
//   node scripts/guide-capture/run.mjs [--base http://localhost:3921] [--lang en,th] [--chapter dub,clone]
//
// Each chapter's capture steps live in chapters/<chapter-id>.mjs and export
// `default async function capture(ctx)`. Screenshots are written as WebP to
// src/renderer/src/features/guide/assets/<lang>/<shot-id>.webp. Needs ffmpeg
// (WebP encode) and Playwright's Chromium. Sample media come from the environment:
// GUIDE_DUB_SAMPLE (a short two-speaker video) and GUIDE_SPEECH_CLIP (a short speech WAV).
import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { labels } from './chapters/dub.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const assets = join(here, '../../src/renderer/src/features/guide/assets');
const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, value, index, all) => {
    if (value.startsWith('--')) pairs.push([value.slice(2), all[index + 1]]);
    return pairs;
  }, []),
);
const base = (args.base || process.env.GUIDE_BASE_URL || 'http://localhost:3921').replace(/\/$/, '');
const languages = (args.lang || 'en,th').split(',');
const wanted = args.chapter ? new Set(args.chapter.split(',')) : null;
const chapterFiles = readdirSync(join(here, 'chapters'))
  .filter((name) => name.endsWith('.mjs') && (!wanted || wanted.has(name.slice(0, -4))))
  .sort();

/** Outline the given elements with numbered badges (removed after the shot). */
async function annotate(page, marks) {
  const boxes = [];
  for (const [index, mark] of marks.entries()) {
    const locator = typeof mark === 'string' ? page.locator(mark).first() : mark;
    const box = await locator.boundingBox();
    if (box) boxes.push({ ...box, n: index + 1 });
    else console.warn(`  ! highlight ${index + 1} not visible`);
  }
  await page.evaluate((items) => {
    for (const item of items) {
      const frame = document.createElement('div');
      frame.dataset.guideMark = '';
      Object.assign(frame.style, {
        position: 'fixed', left: `${item.x - 4}px`, top: `${item.y - 4}px`,
        width: `${item.width + 8}px`, height: `${item.height + 8}px`, border: '3px solid #f43f5e',
        borderRadius: '10px', boxShadow: '0 0 0 4px rgb(244 63 94 / 0.25)', zIndex: 2147483646,
        pointerEvents: 'none',
      });
      const badge = document.createElement('div');
      badge.dataset.guideMark = '';
      badge.textContent = String(item.n);
      Object.assign(badge.style, {
        position: 'fixed', left: `${Math.max(2, item.x - 16)}px`, top: `${Math.max(2, item.y - 16)}px`,
        width: '26px', height: '26px', borderRadius: '13px', background: '#f43f5e', color: '#fff',
        font: '700 14px/26px system-ui, sans-serif', textAlign: 'center', zIndex: 2147483647,
        pointerEvents: 'none', boxShadow: '0 1px 4px rgb(0 0 0 / 0.4)',
      });
      document.body.append(frame, badge);
    }
  }, boxes);
}

// The capture backend's real remote-GPU host never appears in a shipped
// screenshot (an unauthenticated cluster URL is an open door): it is shown
// as ray.example.com. Read from the backend, so the host is never in the repo.
const redactions = await fetch(`${base}/api/settings/ray`)
  .then((response) => response.json())
  .then((config) => (config.dashboard_url ? [new URL(config.dashboard_url).host] : []))
  .catch(() => []);

async function redact(page) {
  if (!redactions.length) return;
  await page.evaluate((hosts) => {
    const swap = (text) => hosts.reduce((out, host) => out.split(host).join('ray.example.com'), text);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (hosts.some((host) => node.nodeValue.includes(host))) node.nodeValue = swap(node.nodeValue);
    }
    for (const field of document.querySelectorAll('input, textarea')) {
      if (hosts.some((host) => field.value.includes(host))) field.value = swap(field.value);
    }
  }, redactions);
}

async function shot(page, language, id, { marks = [], target, fullPage = false, settle = 400 } = {}) {
  await page.waitForTimeout(settle);
  await redact(page);
  if (marks.length) await annotate(page, marks);
  const png = join(tmpdir(), `guide-${language}-${id}.png`);
  const options = { path: png, animations: 'disabled', fullPage };
  if (target) {
    const locator = typeof target === 'string' ? page.locator(target).first() : target;
    await locator.screenshot(options);
  } else {
    await page.screenshot(options);
  }
  await page.evaluate(() => document.querySelectorAll('[data-guide-mark]').forEach((node) => node.remove()));
  mkdirSync(join(assets, language), { recursive: true });
  const out = join(assets, language, `${id}.webp`);
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', png, '-c:v', 'libwebp', '-quality', '80', out]);
  rmSync(png, { force: true });
  console.log(`  ✓ ${language}/${id}`);
}

const browser = await chromium.launch(
  process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {},
);
let failures = 0;
try {
  for (const language of languages) {
    for (const file of chapterFiles) {
      const chapter = file.slice(0, -4);
      console.log(`${language} · ${chapter}`);
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: language });
      await context.addInitScript((lang) => {
        localStorage.setItem('voicestudio.setup.complete.v1', '1');
        localStorage.setItem('voicestudio.locale', lang);
      }, language);
      const page = await context.newPage();
      const ctx = {
        page,
        language,
        base,
        /** Open an app route and wait for the UI to settle. */
        goto: async (path) => {
          await page.goto(`${base}/#${path}`, { waitUntil: 'networkidle' }); // hash routing
          await page.waitForTimeout(800);
        },
        shot: (id, options) => shot(page, language, id, options),
        /** Pick per-language text: ctx.t({ en: 'Save', th: 'บันทึก' }). */
        t: (byLanguage) => byLanguage[language] ?? byLanguage.en,
        /** UI label from the locale catalog: L('nav.dub'); L.pattern(key) matches any {{values}}. */
        L: labels(language),
      };
      try {
        const module = await import(pathToFileURL(join(here, 'chapters', file)).href);
        await module.default(ctx);
      } catch (error) {
        failures += 1;
        console.error(`  ✗ ${chapter}: ${error?.message ?? error}`);
        await page.screenshot({ path: join(tmpdir(), `guide-failed-${language}-${chapter}.png`) }).catch(() => {});
      } finally {
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
}
process.exit(failures ? 1 : 0);
