// Chapter "audiobook": import a small EPUB, cast a second voice, preview the
// chapter plan, render, stop half-way, resume, and show the finished book.
// Needs voice profiles named "Narrator" and "Mira". The book text differs per
// language, so the second run renders too instead of hitting the chapter cache.
import { execFileSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BOOKS = {
  en: {
    title: 'The Lighthouse Keeper',
    chapters: [
      ['Chapter One: The Keeper', ['The old lighthouse stood at the edge of the world, white against a grey sea.', 'Every evening the old keeper climbed one hundred steps to light the lamp.']],
      ['Chapter Two: The Storm', ['On the third stormy night the wind tore the clouds apart.', 'His granddaughter Mira watched the beam sweep across the waves.']],
      ['Chapter Three: Morning', ['When the morning sun rose, a small boat rested safely in the harbour.', 'The keeper smiled, and Mira knew the lamp would never go dark.']],
    ],
    line: 'Grandfather, the ships can see our light!',
  },
  th: {
    title: 'ผู้เฝ้าประภาคาร',
    chapters: [
      ['บทที่หนึ่ง ผู้เฝ้าประภาคาร', ['ประภาคารสีขาวตั้งอยู่ที่สุดขอบโลก ตัดกับทะเลสีเทา', 'ทุกเย็น ผู้เฝ้าชราจะปีนบันไดหนึ่งร้อยขั้นขึ้นไปจุดตะเกียง']],
      ['บทที่สอง พายุ', ['ในคืนที่สาม ลมแรงฉีกเมฆจนขาดกระจาย', 'มิราหลานสาวของเขามองลำแสงกวาดผ่านเกลียวคลื่น']],
      ['บทที่สาม รุ่งเช้า', ['เมื่อดวงอาทิตย์ขึ้น เรือลำเล็กก็จอดอยู่อย่างปลอดภัยในท่าเรือ', 'ผู้เฝ้ายิ้ม และมิรารู้ว่าตะเกียงดวงนี้จะไม่มีวันดับ']],
    ],
    line: 'คุณตาคะ เรือมองเห็นแสงของเราแล้วค่ะ',
  },
};

// A minimal EPUB 3 (container, OPF, one XHTML file per chapter), built with
// Python's zipfile so the guide needs no binary fixture.
const EPUB_PY = `
import json, sys, zipfile
book = json.loads(sys.argv[2])
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
    z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    n = len(book["chapters"])
    items = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>' for i in range(n))
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(n))
    z.writestr("OEBPS/content.opf", f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">guide-sample</dc:identifier><dc:title>{book["title"]}</dc:title></metadata><manifest>{items}</manifest><spine>{spine}</spine></package>')
    for i, (title, paras) in enumerate(book["chapters"]):
        body = "".join(f"<p>{p}</p>" for p in paras)
        z.writestr(f"OEBPS/c{i}.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title></head><body><h1>{title}</h1>{body}</body></html>')
`;

export default async function capture({ page, goto, shot, t, language, L }) {
  const book = BOOKS[language] ?? BOOKS.en;
  const epub = join(mkdtempSync(join(tmpdir(), 'guide-epub-')), 'the-lighthouse-keeper.epub');
  execFileSync('python3', ['-I', '-c', EPUB_PY, epub, JSON.stringify(book)]);

  await goto('/audiobook');
  const script = page.getByRole('textbox', { name: L('clone.text_label'), exact: true });
  const importLabel = page.locator('label', { has: page.locator('input[type="file"]') });
  await importLabel.locator('input[type="file"]').setInputFiles(epub);
  await page.waitForFunction((el) => el.value.startsWith('# '), await script.elementHandle(), { timeout: 60000 });
  await page.getByPlaceholder(L('audiobook.untitled')).fill(book.title);
  const stats = page.getByText(L.pattern('audiobook.stats'));
  await shot('audiobook-import', { marks: [importLabel, script, stats] });

  // A second voice: one [voice:Mira] line in chapter two.
  const text = await script.inputValue();
  const second = book.chapters[1][1][1];
  await script.fill(text.replace(second, `${second}\n\n[voice:Mira] ${book.line}`));
  const toolbar = page.getByRole('toolbar');
  await shot('audiobook-markup', {
    marks: [toolbar.getByRole('button', { name: L('twilioIntegration.voice'), exact: true }), script],
  });

  const sidebar = page.locator('[data-slot="secondary-sidebar"]');
  const narrator = sidebar.getByRole('button', { name: 'Narrator', exact: true }).first();
  await narrator.click();
  const cast = sidebar.locator('details', {
    has: page.locator(':scope > summary', { hasText: L('stories.cast') }),
  }).first();
  const mira = cast.locator('details', { has: page.locator('summary', { hasText: 'Mira' }) }).first();
  await mira.locator('summary').click();
  await mira.getByRole('button', { name: 'Mira', exact: true }).click();
  await narrator.scrollIntoViewIfNeeded();
  await shot('audiobook-voices', {
    marks: [narrator, sidebar.getByRole('button', { name: L('audiobook.format_m4b') })],
  });
  await mira.scrollIntoViewIfNeeded();
  const plan = sidebar.getByRole('button', { name: L('audiobook.preview_plan') });
  await plan.click();
  const planRows = plan.locator('xpath=..').locator('div.max-h-56');
  await planRows.waitFor({ timeout: 60000 });
  await planRows.scrollIntoViewIfNeeded();
  await shot('audiobook-plan', { marks: [mira, plan, planRows] });

  // A fresh seed per run, so the render is not served whole from the chapter cache.
  const overrides = sidebar.locator('details', {
    has: page.locator(':scope > summary', { hasText: L('audiobook.expressive') }),
  }).first();
  await overrides.locator(':scope > summary').click();
  await overrides.getByLabel(L('audiobook.seed')).fill(String(Date.now() % 1000000));
  await overrides.locator(':scope > summary').click();

  // Render, stop after the first chapter, then resume.
  const panel = page.locator('[data-slot="generate-panel"]').first();
  const create = panel.getByRole('button', { name: L('audiobook.create') });
  await page.waitForFunction((el) => el && !el.disabled, await create.elementHandle(), { timeout: 120000 });
  await create.click();
  const progress = panel.locator('[aria-live="polite"]');
  await progress.locator('li .lucide-check').first().waitFor({ timeout: 900000 });
  await shot('audiobook-progress', {
    settle: 200,
    marks: [progress, panel.getByRole('button', { name: L('common.stop') })],
  });
  await panel.getByRole('button', { name: L('common.stop') }).click();
  const resume = sidebar.getByRole('button', { name: L('common.resume') }).first();
  await resume.waitFor({ timeout: 120000 });
  const recovery = resume.locator('xpath=..');
  await recovery.scrollIntoViewIfNeeded();
  await shot('audiobook-resume', {
    marks: [panel.getByText(L('audiobook.stopped_note').split(' — ')[0]).first(), recovery, resume],
  });
  await resume.click();
  const ready = page.getByRole('heading', { name: L('audiobook.ready') });
  await ready.waitFor({ timeout: 900000 });
  // Create again: every chapter is cached now, so this is instant and the
  // player gets the script for its follow-along view.
  await page.waitForFunction((el) => el && !el.disabled, await create.elementHandle(), { timeout: 60000 });
  await create.click();
  await page.getByText(L('audiobook.cached_note', { count: 3 })).waitFor({ timeout: 300000 });
  const result = page.locator('section', { has: ready }).last();
  await result.scrollIntoViewIfNeeded();
  await shot('audiobook-result', {
    marks: [
      result.getByText(L.pattern('audiobook.cached_note')),
      result.getByRole('button', { name: L('player.play'), exact: true }),
      result.getByRole('region', { name: L('audiobook.lyrics') }),
      result.getByRole('button', { name: L('modelMaintenance.download'), exact: true }),
      result.getByRole('button', { name: L('audiobook.download_cues') }),
    ],
  });
}
