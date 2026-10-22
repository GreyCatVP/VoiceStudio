import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'getting-started',
  order: 20,
  title: 'Getting started',
  summary:
    'First launch, installing models from the Model Catalogue, accepting a model licence, and choosing engines and the speed / quality preset.',
  sections: [
    {
      id: 'what',
      title: 'What you set up on first launch',
      blocks: [
        {
          kind: 'p',
          text: 'The first time you open VoiceStudio, a short setup replaces the workspaces until it is done. It checks this computer, downloads the models you choose, and asks your privacy choices. It runs once; afterwards you change everything in **Settings**.',
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            '**System check** — RAM, disk space, GPU, the model cache and the network to Hugging Face.',
            '**Model packs** — a set of models tuned for this machine, installed in one step.',
            '**Privacy** — whether to share anonymous usage stats, plus the privacy defaults.',
            '**Enter studio** — optional dictation setup (microphone and shortcut), then the studio opens.',
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Before this setup, the desktop app may show **Install local runtime**: it downloads Python and the app\'s dependencies (several GB) once, with a progress bar. Voice models are installed separately, when you choose them.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How first run and model installs work',
      blocks: [
        {
          kind: 'diagram',
          id: 'getting-started-flow',
          caption:
            'Top: the four setup steps. Bottom: what happens when you install a model, from setup or from Settings → Models. Dashed arrows only happen sometimes.',
          text: {
            firstrun: 'First-run setup',
            install: 'Installing a model',
            check: '1. System check',
            packs: '2. Model packs',
            privacy: '3. Privacy',
            studio: '4. Enter studio',
            pick: 'Download or\nInstall pack',
            backend: 'Backend checks:\nknown model, disk,\naccess',
            hub: 'Hugging Face\n(or a mirror)',
            cache: 'Model cache\non this computer',
            progress: 'Live progress\n% · speed · ETA',
            licence: 'Accept licence',
            ready: 'Installed:\nselect the engine',
            starts: 'install',
            request: 'request',
            download: 'download',
            files: 'files',
            ifneeded: 'if the model\nasks for it',
            events: 'progress',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            'You press **Download** on a model (or install a whole pack).',
            'The backend checks the model is one it knows, that the download plus **10 GB** of headroom fits on the model disk, and whether Hugging Face needs a token or access request for it.',
            'It downloads the files from Hugging Face, or from the mirror you chose in **Settings → Models**. Your Hugging Face token is only ever sent to Hugging Face, never to a mirror.',
            'The files go to the model cache on this computer. A broken download resumes from where it stopped.',
            'If the model asks for it, you accept its licence. Then you select it as the engine to use.',
          ],
        },
        {
          kind: 'table',
          head: ['Check', 'What you see when it fails', 'What to do'],
          rows: [
            ['Disk space', '**Not enough space for this pack** with the download size, the 10 GB headroom and the free space', 'Free up space, or move the model cache to a bigger drive in **Settings → Storage**'],
            ['Hugging Face access', '**Hugging Face access is required before this model can be installed.**', 'Use **Request model access** and **Add Hugging Face token**, then **Check access**'],
            ['Network', 'The download stops with an error and a **Retry** button', 'Check the proxy or mirror in **Settings → Network** and **Settings → Models**, then retry'],
            ['Repeated failure', 'The model refuses to install again for a short time', 'Wait for the countdown, then retry'],
          ],
        },
      ],
    },
    {
      id: 'first-run',
      title: 'Walk through the first-run setup',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Read the system check',
              text: 'The four steps are listed on the left. The check runs by itself; press **Re-check** after you fix something. When nothing blocks you, press **All good — continue**.',
              shot: 'getting-started-setup-check',
              check: 'Every line has a green tick. Yellow lines explain what to do but do not block you.',
            },
            {
              title: 'Choose a model pack',
              text: 'Pick a tier (**Fast**, **Balanced**, **Quality** or **Max**). The pack lists each model, its size and the total download. Press **Install … pack** to download and activate the whole set. **Advanced** shows every model one by one.',
              shot: 'getting-started-setup-packs',
              check: 'A progress bar shows while the pack downloads. **Still needed:** names any required model that is not installed yet; the step finishes when it is gone.',
            },
            {
              title: 'Make your privacy choice',
              text: 'VoiceStudio asks once whether to share anonymous, content-free usage stats. The two buttons have equal weight: **Yes, share anonymous stats** or **No thanks**. Nothing is sent unless you say yes. **What exactly is sent?** opens the details.',
              shot: 'getting-started-setup-privacy',
              check: 'After you choose, the buttons disappear and you can continue. You can change your mind any time in **Settings → Privacy**.',
            },
            {
              title: 'Enter the studio',
              text: 'On the last step you can set up dictation now (microphone permission and a shortcut) or skip it. Press **Enter studio**.',
              check: 'The main window opens on the Clone workspace.',
            },
          ],
        },
      ],
    },
    {
      id: 'catalogue',
      title: 'Install a model from the Model Catalogue',
      blocks: [
        {
          kind: 'p',
          text: 'Every model VoiceStudio can use is in **Settings → Models**, grouped by tool: **TTS**, **ASR**, **Dictation**, **Diarisation**, **Translation** and **LLM**. Each card shows the size, a **Licence** badge and the actions for that model.',
        },
        {
          kind: 'steps',
          items: [
            {
              title: 'Open the catalogue and find the model',
              text: 'Open **Settings → Models** and pick a tool, here **Dictation**. Use the search box to filter by name. Check the size on the card before you download.',
              shot: 'getting-started-catalogue',
              check: 'The card shows the model name, its Hugging Face id, the **Licence** badge, the size and **Download**.',
            },
            {
              title: 'Download it',
              text: 'Press **Download**. The download runs in the background, so you can keep working. Press **Cancel** to stop it.',
              shot: 'getting-started-downloading',
              check: 'The card shows **downloading** with a progress bar and the time left.',
            },
            {
              title: 'Accept the licence, if the model asks',
              text: 'Some models stay unusable until you accept their licence; their card says **Accept licence to use**. Press the **Licence** badge, read the terms, tick the box that you have the rights the licence needs, and press **Accept licence**.',
              shot: 'getting-started-licence',
              check: 'The dialog now offers **Withdraw acceptance**, and the card no longer asks for a licence.',
            },
          ],
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'VoiceStudio is not the owner of these models and cannot give you rights to them. The licence of each model decides how you may use it and the audio it makes, for example non-commercial use only.',
        },
      ],
    },
    {
      id: 'engines',
      title: 'Choose engines and the speed / quality preset',
      blocks: [
        {
          kind: 'p',
          text: 'The panel at the bottom left of the window shows the device and, for each tool, the engine in use and its state. Click a row for details, or **Change engine** to open its page in **Settings → Models**.',
        },
        {
          kind: 'shot',
          id: 'getting-started-engine-panel',
          caption:
            '**1** The device the backend runs on; click it for live CPU, RAM and GPU use. **2** **Speed / quality** preset. **3** An engine row. **4** View: **Simple**, **Models** or **Details**.',
        },
        {
          kind: 'table',
          head: ['Preset', 'Voice (OmniVoice)', 'Speech to text (Faster-Whisper)', 'Translation'],
          rows: [
            ['**Fast**', '8 steps, no post-processing', 'beam 1', 'Argos, beam 1'],
            ['**Balanced**', '16 steps', 'beam 3', 'Argos, beam 3'],
            ['**Quality**', '32 steps', 'beam 5', 'NLLB, beam 5'],
            ['**Max**', '64 steps, strongest installed models', 'beam 8', 'NLLB, beam 8'],
            ['**Auto**', 'Picks a tier per tool that fits this machine\'s RAM and GPU', '', ''],
          ],
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Start with **Balanced**. Presets never download anything: a tier that needs a model you do not have keeps the current one. The preset is locked while a job runs.',
        },
        {
          kind: 'steps',
          items: [
            {
              title: 'Select the engine for a tool',
              text: 'In **Settings → Models**, open a tool (here **TTS**). The engines list shows where each runs (for example **CPU**, or **network** for a remote GPU). Press **Select** on the one you want; **Test engine** checks that it loads.',
              shot: 'getting-started-engine-select',
              check: 'The engine shows **Selected**, and the engine panel shows the new name.',
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
          shot: 'getting-started-installed',
          items: [
            'The model card shows **installed** and no longer asks for a licence.',
            'The engine panel shows a model for **Text to speech** with a green or blue dot, not **Inactive**.',
            '**Settings → Compute device → System check** finishes without red lines.',
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
          text: 'If **Text-to-speech is not ready** appears above a workspace, press **Fix**: VoiceStudio installs and selects the best compatible voice engine for this device.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'A model marked **Incomplete** was interrupted. Press **Repair** to finish the download; the parts already on disk are kept.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Downloads are slow or blocked on your network? Choose another endpoint under **Hugging Face mirror** at the bottom of **Settings → Models**, or set a proxy in **Settings → Network**. Gated models still need the official Hugging Face endpoint.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Models listed under **Unavailable** do not run on this computer (for example Apple-only MLX models on Linux or Windows). With a remote GPU, heavy engines run there and show **network** instead of a local device.',
        },
      ],
    },
  ],
};

export default chapter;
