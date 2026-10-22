import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'stories',
  order: 60,
  title: 'Stories: scenes with many voices',
  summary:
    'Write or paste a scene, let Auto-cast split it into lines per character, give each character a voice, and render the whole story to one file with chapters.',
  sections: [
    {
      id: 'what',
      title: 'What Stories is for',
      blocks: [
        {
          kind: 'p',
          text: 'Use **Stories** for dialogue: radio plays, children’s stories, game scenes, podcasts with several speakers. The script is a list of **lines**. Each line belongs to a **character**, and each character speaks with one of your voice profiles.',
        },
        {
          kind: 'list',
          items: [
            'Need one narrator reading a long text? Use **Audiobook** instead (next chapter). It works on one manuscript instead of separate lines.',
            'Need a single short clip? Use the text-to-speech workspace.',
            'You need at least one voice profile. If the voice list says **No voice profiles installed yet**, clone or design a voice first.',
          ],
        },
      ],
    },
    {
      id: 'how',
      title: 'How a story is rendered',
      blocks: [
        {
          kind: 'diagram',
          id: 'stories-flow',
          caption:
            'The app turns your lines into chapters of spans and sends them in one request. The backend renders each chapter, reuses anything already rendered, and stitches the chapters into one file.',
          text: {
            script: 'Script\ntyped, pasted\nor imported',
            lines: 'Auto-cast:\nlines per\ncharacter',
            voices: 'Voice per line:\nline › character\n› default',
            plan: 'Generate → backend\nPOST /longform/render\nchapters → spans',
            cache: 'Chapter\ncache',
            batch: 'TTS engine\nRay: one model\nload per batch',
            chapter: 'Chapter audio\n+ AI watermark',
            mux: 'Stitch chapters\nffmpeg →\nM4B / MP3',
            out: 'Player\n+ Download',
            lookup: 'already\nrendered?',
            missing: 'missing lines',
            hit: 'cache hit: reuse',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            '**Auto-cast** reads your text, finds who speaks each line (`Name:` screenplay lines, `[Name]` tags or quoted prose), adds a character for each speaker and gives each character a voice in turn.',
            'For every line the app picks the voice: the line’s own **voice** if you set one, otherwise its character’s voice, otherwise the default voice from the **voice** list in the left panel.',
            'A line that starts with `#` starts a new chapter. When you press **Generate**, the app sends all chapters in one request to the backend on this computer.',
            'The backend renders one chapter at a time. Chapters and lines it rendered before with the same text, voice and settings come from the cache straight away.',
            'Missing lines go to the TTS engine. When the engine runs on your Ray cluster (Settings → Remote GPU), the backend sends a chapter’s missing lines as batch jobs (up to 16 lines per job), so the model loads once per batch, not once per line.',
            'Each finished chapter gets the inaudible AI watermark. ffmpeg then joins the chapters into one M4B with chapter marks, or one MP3.',
          ],
        },
        {
          kind: 'table',
          head: ['Setting (left panel)', 'What it does'],
          rows: [
            ['**Title**', 'Name of the story. It is written into the file’s tags.'],
            ['**voice**', 'Default voice. Used for every line that has no character voice and no line voice.'],
            ['**Speed**', 'Reading speed for all lines. A line’s own **Tone & speed** setting overrides it.'],
            ['**Language**', '**Auto** detects the language from the text and voice. Pick a language if a voice drifts into the wrong accent.'],
            ['**Format**', '**M4B (chapters)** keeps chapter marks that players show. **MP3** plays everywhere; use **Download cue sheet (.txt)** for its chapter times.'],
            ['**Cast — assign a voice to each character**', 'Rename characters, add or remove them, and choose each character’s voice.'],
            ['**Projects**', 'Save the story under a name and open it again later.'],
            ['**Production overrides**', 'Gaps between lines and paragraphs, trimming engine silence, seed and repeated-line variation.'],
            ['**Cover & details**, **Loudness**', 'Cover image and tags (author, narrator, year…), and loudness normalization (ACX or podcast).'],
          ],
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Make a two-voice story',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Paste the scene into Auto-cast',
              text: 'Open **Stories** from the workspace menu and type a **Title**. Press **Add First Line** and type `# The Storm` to name the first chapter. Open **Auto-cast**, paste your scene with one speaker per line (**1**), for example `Narrator: The storm had kept the lighthouse dark…` and `Mira: Grandfather, is the lamp still burning?`, and press **Auto-cast** (**2**). **Split by** (**3**) controls how long untagged text is cut into lines.',
              shot: 'stories-autocast',
              check: 'A message says how many lines were cast across how many voices, and the lines appear under the chapter line.',
            },
            {
              title: 'Add the next chapter',
              text: 'Press **Add Chapter** under the last line, then paste the next part of the scene into **Auto-cast** and press **Auto-cast** again. New lines are added at the end, after the new chapter line.',
              check: 'The script shows two lines that start with `#`, each followed by its dialogue lines.',
            },
            {
              title: 'Give each character a voice',
              text: 'In the left panel, pick a default voice in the **voice** list. Then open **Cast — assign a voice to each character** and choose a voice for each character (**1**, **2**). Auto-cast assigns voices in turn, so check that each character got the voice you want.',
              shot: 'stories-cast',
              check: 'Each character shows the voice you chose, and **Generate** is enabled.',
            },
            {
              title: 'Listen to one line first',
              text: 'Each line card shows its text (**1**) and its character (**2**). Press the play button at the side of a line (**Preview this line**, **3**) to render only that line, then play it (**4**). This is a quick check of a voice before you render everything.',
              shot: 'stories-lines',
              check: 'A small player appears under the line and plays it in the character’s voice.',
            },
            {
              title: 'Render the story',
              text: 'Press **Generate** at the bottom of the left panel. The tracker (**1**) lists every chapter, its status and the time left. **Stop** (**2**) ends the render after the current chapter.',
              shot: 'stories-progress',
              check: 'Chapters turn from a spinner to a check mark one by one. A lightning icon with **cached** means the chapter was reused.',
            },
            {
              title: 'Play and download',
              text: 'When the render finishes, **Audiobook ready** appears under the script. Play the result (**1**, **2**), press **Download** (**3**) to save the file, or **Download cue sheet (.txt)** (**4**) for the chapter start times.',
              shot: 'stories-result',
              check: 'The file plays the lines in order, each in its character’s voice. Add gaps between lines under **Production overrides** if they run together.',
            },
          ],
        },
        {
          kind: 'verify',
          items: [
            'The player under **Audiobook ready** plays the whole story, and its length is close to the estimate under the script.',
            'Each character speaks with the voice you chose in the cast. If a line uses the wrong voice, check its **voice** row: a line voice wins over the character voice.',
            'In an M4B player (for example Apple Books or VLC), the chapter list shows your `#` chapter titles.',
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
          text: 'Inside a line, `[pause 0.5s]` adds silence and **Set inline voice** switches voice for the selected words. **Tone & speed** adds tone tags (laugh, sigh…) and a speed for that line only.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Change one line and press **Generate** again: only the chapter with that line is rendered again, the rest comes from the cache. After **Stop**, press **Generate** again to continue; finished chapters are reused. If the app closes or the backend restarts during a render, an **Interrupted audiobook** card in the left panel shows how many chapters are cached; press **Resume** there.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Generate** greyed out? The text above the button says why: no spoken line yet, no voice for some lines (**Choose a default voice, or give every line a voice.**), another story or audiobook is still rendering, or the voice engine is not ready (check **Settings → Engines**).',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'If one chapter fails, the others still render and the file is built without it. The tracker shows the reason next to the failed chapter. Fix the cause and press **Generate** again to render only the missing chapters.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**Import** reads `.txt`, `.md`, `.srt` and `.vtt` files in the app, and `.epub` and `.pdf` files through the backend. Imported text goes into **Auto-cast**, ready to split. **Stems** renders one audio file per character, for editing in another program.',
        },
      ],
    },
  ],
};

export default chapter;
