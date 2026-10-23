import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'audiobook',
  order: 70,
  title: 'Audiobook: from a book to an M4B',
  summary:
    'Import an EPUB, PDF or text file, let VoiceStudio find the chapters, choose a narrator and extra voices, and render a chaptered audiobook you can stop and resume.',
  sections: [
    {
      id: 'what',
      title: 'What Audiobook is for',
      blocks: [
        {
          kind: 'p',
          text: 'Use **Audiobook** for long texts read mostly by one narrator: novels, reports, lessons. You work on one manuscript. Lines that start with `#` are chapter titles, and short tags in the text change voice, pace or pauses. The result is one M4B file with real chapters (or an MP3 with a cue sheet).',
        },
        {
          kind: 'list',
          items: [
            'For dialogue where every line has its own character, **Stories** (previous chapter) is easier.',
            'Both workspaces use the same renderer, so the cache, resume, formats, cover and loudness options work the same way.',
            'Your draft stays in the workspace when you switch to another one or restart the app. Use **Projects** to keep several books.',
          ],
        },
      ],
    },
    {
      id: 'how',
      title: 'How a book is rendered',
      blocks: [
        {
          kind: 'diagram',
          id: 'audiobook-flow',
          caption:
            'Import turns the file into a script with `#` chapter headings. Create audiobook renders the chapters one at a time, keeps each finished chapter in a cache, and joins them into the final file.',
          text: {
            book: 'Book file\nEPUB · PDF\nTXT · MD',
            import: 'Import\nPOST\n/audiobook/import',
            script: 'Script\n# chapter headings',
            plan: 'Plan\nchapters → paragraphs\n→ spans',
            queue: 'Render\none chapter\nat a time',
            manifest: 'Resume\nmanifest',
            engine: 'TTS engine\nlocal, or Ray\nbatch jobs',
            wavs: 'Chapter audio\n+ AI watermark\n(cache)',
            assemble: 'Assemble\nffmpeg: chapters,\ncover, loudness',
            out: 'M4B / MP3\nplayer · download\ncue sheet',
            saved: 'saved first',
            missing: 'chapters\nto render',
            hit: 'cached:\nreuse',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            '**Import** sends the file to the backend on this computer. EPUB chapters are read in reading order, and each chapter’s first heading becomes its title; title pages and similar front matter are skipped when the book marks them. PDF text is extracted and split the same way. In plain text, short lines that start with `Chapter`, `Part`, `Book`, `Prologue`, `Epilogue` or `Section` become chapter headings, and so do Thai headings such as `บทที่ 1`, `ตอนที่ ๒`, `ภาคที่ 3`, `บทนำ`, `คำนำ`, `ปัจฉิมบท` and `บทส่งท้าย`.',
            'When you press **Create audiobook**, the backend splits the script into chapters and spans (runs of text with one voice and pace). It saves this plan as a resume manifest before it starts.',
            'Chapters render one at a time. A chapter that was rendered before with the same text, voices and settings comes from the cache at once.',
            'The engine renders the rest. On your Ray cluster, a chapter’s lines go out as batch jobs, so the model loads once per batch. Each chapter gets the inaudible AI watermark.',
            'ffmpeg joins the chapters, adds chapter marks, tags and cover, and applies loudness normalization if you chose it.',
          ],
        },
        {
          kind: 'table',
          head: ['Markup in the script', 'Effect'],
          rows: [
            ['`# Chapter title`', 'Starts a new chapter with that title.'],
            ['`[voice:Mira]`', 'Everything after it is read by the voice cast as **Mira** in **Cast**, until the next voice tag or the end of the chapter. `[voice:]` switches back to the narrator.'],
            ['`[pause 500ms]`, `[pause 1s]`', 'Silence of that length.'],
            ['`[slow]…[/slow]`, `[fast]…[/fast]`', 'Reads the enclosed words slower or faster.'],
            ['`[emphasis]…[/emphasis]`', 'Stresses the enclosed words.'],
            ['`[spell]…[/spell]`', 'Spells the enclosed text letter by letter.'],
            ['**Reactions**', 'Inserts tags such as laughter or a sigh.'],
          ],
        },
        {
          kind: 'p',
          text: 'You do not need to type the tags: select text and use the toolbar above the script (**Pause**, **Voice**, **Slow**, **Fast**, **Emphasis**, **Spell**, **Reactions**).',
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Turn an EPUB into an audiobook',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Import the book',
              text: 'Open **Audiobook** from the workspace menu, press **Import** (**1**) and choose an `.epub`, `.pdf`, `.txt` or `.md` file. An EPUB fills **Title** in the left panel with the book’s own title when it is empty; otherwise type the book’s name there. The script (**2**) now holds the text with one `#` line per chapter. The line under it (**3**) counts chapters and words (Thai and other languages without spaces are counted word by word) and estimates the running time.',
              shot: 'audiobook-import',
              check: 'Every chapter of the book starts with a `#` line, in the right order.',
            },
            {
              title: 'Mark the lines of a second voice',
              text: 'Put the cursor before a line spoken by another person and press **Voice** (**1**). It inserts `[voice:NAME]` with `NAME` selected, so you can type the name over it. You can also type the tag yourself, for example `[voice:Mira] Grandfather, the ships can see our light!` (**2**).',
              shot: 'audiobook-markup',
              check: '**Before you create** lists `Mira` as an unknown voice until you cast it in the next step. Other warnings there point at empty chapters or unknown tags.',
            },
            {
              title: 'Choose the narrator and the format',
              text: 'In the left panel, pick the narrator in the **voice** list (**1**). Every span without a voice tag uses it. Keep **M4B (chapters)** (**2**) for a file with chapter marks, or choose **MP3**.',
              shot: 'audiobook-voices',
              check: 'The narrator is highlighted in the list.',
            },
            {
              title: 'Cast the other voices and check the plan',
              text: 'Open **Cast**. Each name used in a `[voice:…]` tag is listed; open it and choose a voice profile (**1**). Press **Preview plan** (**2**) to see the chapters the backend will render (**3**). The play button next to a chapter renders only that chapter, so you can check it before the whole book.',
              shot: 'audiobook-plan',
              check: 'The plan lists every chapter with its length in characters, and the cast name shows the voice you chose.',
            },
            {
              title: 'Create the audiobook',
              text: 'Press **Create audiobook**. The tracker (**1**) shows each chapter, the elapsed time and an estimate of the time left. **Stop** (**2**) ends the render after the current chapter.',
              shot: 'audiobook-progress',
              check: 'Chapters get a check mark one by one.',
            },
            {
              title: 'Stop and resume',
              text: 'If you stop, or the app closes during a render, the finished chapters stay in the cache. The panel says the render stopped (**1**) and **Interrupted audiobook** (**2**) shows how many chapters are cached. Press **Resume** (**3**) to render only what is left.',
              shot: 'audiobook-resume',
              check: 'After **Resume**, the cached chapters finish at once and the render continues with the next chapter.',
            },
            {
              title: 'Listen and export',
              text: 'When it finishes, **Audiobook ready** appears under the script. A note (**1**) says how many chapters were reused from the cache. Play the book (**2**) and follow the text as it is read (**3**). Press **Download** (**4**) to save the M4B, or **Download cue sheet (.txt)** (**5**) for a list of chapter start times.',
              shot: 'audiobook-result',
              check: 'The follow-along text highlights the words as they are spoken, chapter by chapter.',
            },
          ],
        },
        {
          kind: 'verify',
          items: [
            'The book plays from the player under **Audiobook ready**, and the narrator and cast voices are where you expect them.',
            'In an M4B player, the chapter list matches the `#` headings of your script.',
            'If a chapter failed, a note under **Audiobook ready** says so. Press **Create audiobook** again to render only the failed chapters.',
          ],
        },
      ],
    },
    {
      id: 'options',
      title: 'Book options',
      blocks: [
        {
          kind: 'table',
          head: ['Section', 'What you can set'],
          rows: [
            ['**Cover & details**', 'Cover image (JPG or PNG, up to 8 MB) and tags: author, narrator, year, genre, description. Players show them.'],
            ['**Loudness**', '**Loudness: off**, **Normalize (ACX)** for audiobook stores, or **Normalize (podcast)**. Normalization measures the whole book first, then encodes it once.'],
            ['**Pronunciation**', 'Words and how to say them (**Word** → **Say it as…**). Applied before synthesis; changing an entry re-renders the chapters that use it.'],
            ['**Production overrides**', '**Gap between lines**, **Gap between paragraphs**, **Trim engine silence**, **Seed**, **Vary repeated lines**, and emotion settings for IndexTTS2.'],
            ['**Language**', '**Auto**, or the book’s language if the narrator drifts into another accent.'],
          ],
        },
      ],
    },
    {
      id: 'tips',
      title: 'Tips and troubleshooting',
      blocks: [
        {
          kind: 'note',
          tone: 'tip',
          text: 'Try **Load sample** on an empty script. It fills in a short demo with chapters, two voices, pauses and expressive tags.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Edits are cheap: after you change a paragraph, **Create audiobook** renders only the chapters that changed. **Preview plan** and the chapter play buttons fill the same cache, so a previewed chapter is not rendered twice.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'No chapters after importing a `.txt` file? Chapter detection knows English keywords such as `Chapter` and `Part` and Thai headings such as `บทที่ 1`, each on a short line of its own. Otherwise add a line starting with `# ` before each chapter yourself, then the import keeps your headings as they are.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Import** fails with **couldn’t parse EPUB** for DRM-protected or broken files, and with **no text found in the file** for scanned PDFs (images only). Files over 64 MB are refused. Export the text another way and import a `.txt` file.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'The running-time estimate counts words by spaces. It reads low for languages written without spaces, such as Thai.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Only one long render runs at a time. While a story or book is rendering, **Create audiobook** is disabled with **Another book is already rendering. Wait for it, or stop it first.**',
        },
      ],
    },
  ],
};

export default chapter;
