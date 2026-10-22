import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'overview',
  order: 10,
  title: 'How VoiceStudio works',
  summary:
    'The parts of the app, how a request travels through them, and where your data lives. Read this first: every other chapter builds on it.',
  sections: [
    {
      id: 'what',
      title: 'What VoiceStudio is',
      blocks: [
        {
          kind: 'p',
          text: 'VoiceStudio is a desktop app for text to speech, voice cloning, voice design, video dubbing, audiobooks and transcription. It runs **on your computer**: the models, your recordings and your projects stay here unless you choose otherwise.',
        },
        {
          kind: 'list',
          items: [
            '**Desktop app** — the window you use (Electron). It shows the workspaces and talks to the backend.',
            '**Backend** — a local server (Python, FastAPI) on `127.0.0.1`. It queues work, runs the engines and stores your data.',
            '**Engines** — the AI models: voices (TTS), speech recognition (ASR), translation, separation and diarization.',
            '**Remote GPU** (optional) — your own Ray cluster or Modal account, for engines too heavy for this computer.',
          ],
        },
      ],
    },
    {
      id: 'architecture',
      title: 'System architecture',
      blocks: [
        {
          kind: 'diagram',
          id: 'system',
          caption:
            'Solid arrows always happen; dashed arrows only happen when you use that feature (a remote GPU, a model download).',
          text: {
            computer: 'This computer',
            remote: 'Remote GPU (optional)',
            internet: 'Internet (on demand)',
            ui: 'App window\n(Electron renderer)',
            main: 'App process\n(Electron main)',
            api: 'Backend\nFastAPI · 127.0.0.1',
            queue: 'Job queue\n+ GPU pool',
            engines: 'In-process\nengines',
            sidecars: 'Sidecar engines\n(own environments)',
            data: 'Your data\nomnivoice_data',
            models: 'Model cache\n(Hugging Face)',
            ray: 'Ray cluster',
            modal: 'Modal',
            hf: 'Hugging Face Hub',
            http: 'HTTP + WebSocket',
            ipc: 'IPC',
            spawn: 'starts',
            jobs: 'jobs',
            pipe: 'stdin / stdout',
            remotejobs: 'remote jobs\n(opt-in)',
            store: 'SQLite + files',
            load: 'load',
            download: 'downloads\n(on demand)',
          },
        },
        {
          kind: 'table',
          head: ['Part', 'What it does'],
          rows: [
            ['App process', 'Starts the backend (`python -m uvicorn`), opens files and folders for you, checks for updates.'],
            ['App window', 'Every workspace you see. It sends requests to the backend and listens to its live events (`/ws/events`) for progress.'],
            ['Backend', 'Validates each request, queues it, picks the engine, saves the results and the history.'],
            ['Job queue + GPU pool', 'Runs one heavy job at a time per device, so two generations never fight over GPU memory.'],
            ['In-process engines', 'Models loaded inside the backend (for example OmniVoice, Faster-Whisper).'],
            ['Sidecar engines', 'Engines with their own Python environment, run as a separate process the backend can restart (for example IndexTTS2, CosyVoice).'],
            ['Remote GPU', 'When enabled, chosen engines run as jobs on your Ray cluster or in Modal sandboxes instead.'],
          ],
        },
      ],
    },
    {
      id: 'request-flow',
      title: 'What happens when you press Generate',
      blocks: [
        {
          kind: 'diagram',
          id: 'request-flow',
          caption: 'Every workspace follows this path; dubbing and audiobooks repeat it for each line.',
          text: {
            type: '1. You type text\nand pick a voice',
            request: '2. The app sends\nthe request',
            route: '3. Queue + pick\nthe engine',
            render: '4. The engine\nrenders audio',
            finish: '5. Watermark +\nsave',
            play: '6. Play, download\nor reuse',
            history: 'History',
            progress: 'Live progress events',
            saved: 'saved',
            events: 'progress',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            'The workspace collects your text, voice and settings.',
            'The app sends them to the backend on this computer.',
            'The backend queues the job and chooses where it runs: in the backend, in a sidecar, or on your remote GPU.',
            'The engine renders the audio. Progress arrives in the window as it happens.',
            'The backend adds an inaudible AI watermark and saves the result to your history.',
            'You can play it, download it, or use it in a project.',
          ],
        },
      ],
    },
    {
      id: 'data',
      title: 'Where your data lives',
      blocks: [
        {
          kind: 'table',
          head: ['Data', 'Where', 'Leaves this computer?'],
          rows: [
            ['Voices, generation history, dub jobs, settings', '`omnivoice_data` (SQLite database + files)', 'No'],
            ['Story and audiobook projects, transcripts, workflows', 'The app window\'s own storage (IndexedDB / local storage)', 'No'],
            ['Downloaded models', 'Hugging Face cache', 'Downloaded from Hugging Face when you install a model'],
            ['Text and audio of remotely run engines', 'Your Ray cluster or Modal account', 'Only for engines you send there (Settings → Remote GPU)'],
            ['Usage analytics', '—', 'Only if you said yes at first run; content-free'],
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Nothing leaves this computer without your explicit yes, and the app keeps working with every such option declined.',
        },
      ],
    },
    {
      id: 'tour',
      title: 'A tour of the window',
      blocks: [
        {
          kind: 'shot',
          id: 'overview-main',
          caption:
            '**1** Workspace menu — every tool of the app. **2** The current workspace. **3** The workspace title bar with help and settings.',
        },
        {
          kind: 'steps',
          items: [
            {
              title: 'Open a workspace from the menu',
              text: 'The menu on the left groups the workspaces: voices, stories, dubbing and more. This guide is at the bottom of it.',
              check: 'The workspace opens on the right and its name shows in the title bar.',
            },
            {
              title: 'Check that the backend is running',
              text: 'Open **Settings → Compute device** and press **System check**.',
              shot: 'overview-system-check',
              check: 'Each line is green, or yellow with an explanation of what to do.',
            },
          ],
        },
        {
          kind: 'verify',
          items: [
            'The workspace menu opens every workspace.',
            'The system check finishes and lists your GPU (or explains CPU-only mode).',
          ],
        },
      ],
    },
  ],
};

export default chapter;
