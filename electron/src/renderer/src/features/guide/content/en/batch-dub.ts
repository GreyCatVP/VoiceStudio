import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'batch-dub',
  order: 90,
  title: 'Dub many videos at once',
  summary:
    'Queue several videos with the same languages and voice, let the backend dub them one after another, and download the results.',
  sections: [
    {
      id: 'what',
      title: 'What batch dubbing is for',
      blocks: [
        {
          kind: 'p',
          text: '**Batch Dubbing** (`/batch`) dubs a list of videos without asking you anything per file. You choose the target languages, one voice and the background option once; each file then runs through extract → transcribe → translate → speak → mix on its own.',
        },
        {
          kind: 'list',
          items: [
            'Use it for many similar videos: a course, a series of product clips, social media cuts.',
            'There is no review step, no speaker detection and no per-speaker cloning: every line of every file uses the one voice you pick.',
            'When a video needs corrections or several voices, dub it in **Dubbing** instead (previous chapter).',
          ],
        },
      ],
    },
    {
      id: 'queue',
      title: 'How the queue works',
      blocks: [
        {
          kind: 'diagram',
          id: 'batch-dub-queue',
          caption:
            'Each file you add becomes one job. The backend runs one job at a time; inside a job, translate, speak and mix repeat for every target language.',
          text: {
            worker: 'Backend worker — one job at a time',
            files: 'Add Videos\n+ settings',
            queue: 'Queue\n(queued jobs)',
            extract: 'Extract\naudio',
            asr: 'Transcribe\n(ASR)',
            mt: 'Translate',
            tts: 'Speak\n(TTS)',
            mix: 'Mix +\nmux',
            perlang: 'Repeated for each target language',
            outputs: 'output_<lang>.mp4\nper job',
            tabs: 'Active · Completed · Failed\n(refreshes every 3 s)',
            enqueue: 'upload',
            next: 'next job',
            status: 'status',
          },
        },
        {
          kind: 'table',
          head: ['Setting', 'Applies to', 'Comes from'],
          rows: [
            ['**TARGET LANGUAGES**', 'Every file you add with this **Add to Queue**', 'The list in the panel; one output video per language'],
            ['**Engine** (translation)', 'All jobs', '**Settings → Models → Translation** (here NLLB-200)'],
            ['**VOICE**', 'Every line of every file in this **Add to Queue**', '**Default** (the engine’s own voice), one of your **Clone Profiles**, or a **Presets** voice'],
            ['**Preserve background audio (music/FX)**', 'Every file in this **Add to Queue**', 'On: the dub is mixed over the video’s original sound. Off: the dub replaces the sound'],
            ['Speech recognition, TTS engine', 'All jobs', 'The active engines in **Settings → Models**, local or on your remote GPU'],
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Settings are taken when you press **Add to Queue**. To dub some files with other languages or another voice, change the settings and add those files in a second **Add to Queue**.',
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Queue videos, step by step',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Add the videos and choose the settings',
              text: 'Open **Batch Dubbing** from the workspace menu (or the **Dubbing many videos? Open the batch queue** link in Dubbing). Press **Add Videos** and pick one or more MP4, MOV, MKV or WEBM files. Under **TARGET LANGUAGES**, pick each language you want; click a language chip to remove it (Spanish is preselected). Open **VOICE** to choose the voice, and set **Preserve background audio (music/FX)**.',
              shot: 'batch-dub-setup',
              check: 'Your files are listed with their sizes, and only the languages you want are shown as chips.',
            },
            {
              title: 'Add them to the queue',
              text: 'Press **Add to Queue**. Each file is uploaded and becomes a job on the **Active** tab. The first job starts at once; the others wait with **queued**. Each card shows the stage (**🎬 Extracting audio…**, **📝 Transcribing…**, **🌐 Translating…**, **🗣️ Generating speech…** with the line count, **🎛️ Mixing audio…**), the current language and a progress bar. The percentage counts finished languages, so with one target language it stays at 0% until the job is done.',
              shot: 'batch-dub-active',
              check: 'One job shows **running** with its stage and line count (for example **seg 1/3**); the rest show **queued**.',
            },
            {
              title: 'Download the results',
              text: 'When a job finishes it moves to **Completed** and shows how long it took. Press **Export <language>** to download that language’s MP4. Jobs that failed go to **Failed**, with the reason under **More info** and a **Retry** button.',
              shot: 'batch-dub-done',
              check: 'Each completed job has one **Export** button per target language.',
            },
          ],
        },
      ],
    },
    {
      id: 'verify',
      title: 'Check the result',
      blocks: [
        {
          kind: 'verify',
          items: [
            'The **Active** tab is empty and every file is on **Completed**.',
            'Each exported MP4 plays the translated speech in the voice you chose.',
            'With **Preserve background audio (music/FX)** on, the music is still there.',
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
          tone: 'warn',
          text: '**The original voices are still audible.** Batch does not run Demucs. With **Preserve background audio (music/FX)** on, the dub is laid over the whole original sound, speech included. For a clean result with music, dub the video in **Dubbing**, which separates the voices first.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**The queue is kept in memory.** If the app or its backend restarts, the job list starts empty. Finished videos stay on disk under `omnivoice_data/batch/<job>/`, but jobs that had not finished must be added again.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: '**Watch folder** adds every new video that appears in a folder to the queue with the current settings. It needs the desktop app or a Chromium-based browser.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**A job failed with a licence or language-pack message.** Accept the model licence when the dialog opens (for example NLLB-200), then press **Retry** on the job. A missing Argos language pack shows **Install** instead: it installs the pack and retries the job.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: '**Cancel** stops a queued or running job; **Delete** removes a finished one and its files.',
        },
      ],
    },
  ],
};

export default chapter;
