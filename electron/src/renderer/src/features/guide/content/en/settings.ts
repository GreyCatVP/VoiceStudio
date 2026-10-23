import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'settings',
  order: 150,
  title: 'Settings',
  summary:
    'A map of every Settings section: what each one is for, the options that matter, where your choices are saved and when they take effect.',
  sections: [
    {
      id: 'what',
      title: 'What Settings is for',
      blocks: [
        {
          kind: 'p',
          text: 'Settings holds everything that is not part of a single project: the language and look of the app, the models and engines, where data is stored, privacy, networking and diagnostics. Open it with **Settings** at the bottom of the workspace menu. **Back** returns to the studio.',
        },
        {
          kind: 'shot',
          id: 'settings-general',
          caption:
            '**1** The section list. **2** **Search…** finds a section by the names of its options. **3** **Language** of the interface. **4** **Review mode**: **Pause for review** or **Run straight through**.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How settings are saved and applied',
      blocks: [
        {
          kind: 'diagram',
          id: 'settings-storage',
          caption:
            'Looks and layout stay in the app window. Everything else goes through the backend into one of three stores. The dashed arrow: a few settings only take effect after a restart.',
          text: {
            app: 'App window',
            backend: 'Backend',
            apply: 'When it applies',
            ui: 'Settings pages',
            local: 'Browser storage\ntheme · language\nlayout',
            api: 'Settings API',
            env: 'Environment\nvariables\nOMNIVOICE_*',
            prefs: 'prefs.json\nengine picks · env.*',
            table: 'settings table\nin omnivoice.db',
            secrets: 'Encrypted secrets\ntokens · API keys',
            now: 'Right away',
            restart: 'After a restart\ndevice · mirror · ports',
            instant: 'saved\ninstantly',
            http: 'HTTP',
            overrides: 'override\nprefs',
            some: 'some\nsettings',
          },
        },
        {
          kind: 'table',
          head: ['Where', 'What is stored there', 'Notes'],
          rows: [
            ['Browser storage of the app window', 'Theme, palettes, font, UI scale, glass mode, language, sidebar layout', 'Per device. Applies instantly.'],
            ['`prefs.json` in your data folder', 'Engine choices, translator, and `env.*` values such as the mirror', 'An environment variable with the same name always wins over the saved value.'],
            ['`settings` table in `omnivoice.db`', 'Plain options such as performance flags', 'Backed up with the database (**Settings → Storage → Database backup**).'],
            ['Encrypted rows in the same table', 'Hugging Face token, translation and LLM API keys, remote GPU tokens', 'Encrypted with a key made for this installation. A copied database cannot decrypt them on another computer.'],
          ],
        },
        {
          kind: 'list',
          items: [
            '**Right away**: almost everything, including the proxy, tokens, engine choices and privacy options.',
            '**After a restart**: **Compute device**, the **Hugging Face mirror**, the backend and UI ports, and a new model cache folder. The page says **Takes effect after the app restarts** when this applies.',
            '**Reloads the app**: saving a **Remote backend** URL.',
            'Your Hugging Face token: OpenBao is used first when you turn it on in **Credentials**, then the one saved in VoiceStudio, then the `HF_TOKEN` environment variable, then the Hugging Face CLI login. VoiceStudio never writes the CLI login file.',
          ],
        },
      ],
    },
    {
      id: 'map',
      title: 'Every section at a glance',
      blocks: [
        {
          kind: 'table',
          head: ['Section', 'What it is for', 'Important options'],
          rows: [
            ['**General**', 'Language and how pipelines run', '**Language**, **Review mode** (pause between dubbing stages to check ASR and translation)'],
            ['**Appearance**', 'How the app looks', '**Theme** (Light, Dark, System), **Glass mode**, **Keep sidebar expanded**, palettes, **Font**, **UI scale**, **Reset to default**'],
            ['**Models**', 'Every model and engine, by tool', '**Model packs**, **Voice previews**, a page per tool (**TTS**, **ASR**, **Dictation**, **Diarisation**, **Translation**, **LLM**) with engine choice and the catalogue, **Hugging Face mirror**. See the chapter **Getting started**.'],
            ['**Pronunciation dictionary**', 'Teach every engine how to say tricky words', '**Add entry** (word and respelling, for one language or Global), **Test a sentence**, **Backup & restore**. In text, `[[word|respelling]]` overrides it once.'],
            ['**Updates**', 'App updates and release notes', '**Check now**, **What\'s new**, **Releases**, **Database backup**'],
            ['**Network**', 'How downloads reach the internet', '**Proxy** (HTTP or SOCKS5, for Hugging Face and video downloads), **FFmpeg**'],
            ['**Sharing & Remote Access**', 'Use this VoiceStudio from other devices', '**Local network** (one-time PIN and QR code), **Ports**, **Tailscale (private remote access)**, **Remote backend** (run on another computer: **Backend URL**, **API key**)'],
            ['**Credentials**', 'Tokens and keys for online services', '**HuggingFace token** (with its sources, **Test now**, **Clear token**), **Translation providers** (**DeepL API Key**, **Microsoft Translator Key**)'],
            ['**VoiceStudio account**', 'Optional cloud account, only in builds that offer it', 'Off by default. **Account features**, **Cloud sync** of settings'],
            ['**Compute device**', 'Speed, memory and the device models run on', '**System check**, **Speed / quality** for all tools or each one, **Compute-time budget**, **Memory management** (**Flush caches**, **Unload all + flush**), **Compute device** (**Auto (recommended)**), **Disable torch.compile**, **GPU acceleration** report'],
            ['**Usage**', 'What you have made, counted on this computer', '**Takes generated**, **Audio produced**, **By mode**, **By language**'],
            ['**Privacy**', 'What leaves the computer and what is kept', '**Translator** (whether it is offline), **Invisible watermark** (on by default), **Help improve VoiceStudio** (off by default), **Generation history** (**Takes to keep**)'],
            ['**Permissions**', 'System permissions of the desktop app', '**Microphone** (recording, dictation), **Accessibility** (dictation types into other apps)'],
            ['**Storage**', 'Where data and models live, and clean-up', '**Voice data & projects** (move to another drive), **Model cache**, **Disk usage**, **Database backup**, **Generation history**, **Reset & remove**, **Remove all data**'],
            ['**Remote GPU**', 'Run heavy engines on your Ray cluster or Modal', 'See the chapter **Remote GPU**.'],
            ['**Diagnostics**', 'Information for bug reports', '**About** (version, platform, RAM, Python, folders), **Run self-check**, **Save diagnostic bundle**, model credits'],
            ['**VoiceStudio API**', 'The local REST API, documented and testable', 'Interactive reference, **Copy spec URL**, **Open raw spec**'],
            ['**Audio tools**', 'ffmpeg and yt-dlp used for media', 'Bundled or **Use system copy**, **Update**, **Restore tested version**'],
            ['**Logs**', 'The backend log', 'Search, refresh, **Ask VoiceStudio Agent** about an error'],
            ['**Support**', 'Help the project and contact the team', 'Donations, sponsors, **Ways to get in touch**'],
          ],
        },
      ],
    },
    {
      id: 'tour',
      title: 'Find and change a setting',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Search for the option',
              text: 'Type part of an option\'s name in **Search…**, for example `token`. The list keeps only the sections that contain it. Press **Esc** to clear the search.',
              shot: 'settings-search',
              check: 'Only matching sections are listed; here **Credentials**, where the Hugging Face token lives.',
            },
            {
              title: 'Models',
              text: '**Models** opens the model packs, **Voice previews** (downloads pre-rendered samples so voices play before a model is installed; off until you turn it on) and one page per tool.',
              shot: 'settings-models',
              check: 'The tool pages (**TTS**, **ASR**, …) appear under **Models** in the list.',
            },
            {
              title: 'Compute device',
              text: 'Run the **System check** here any time. **Speed / quality** sets one preset for every tool; the rows below override it per tool and show the model and setting it uses.',
              shot: 'settings-compute',
              check: 'A toast says the preset was applied, and the rows show the new values (for example **16 Steps**).',
            },
            {
              title: 'Privacy',
              text: '**Invisible watermark** marks generated audio as AI-made. **Help improve VoiceStudio** is your analytics choice from the first run. **Takes to keep** limits the history; starred takes are never removed, and 0 keeps everything.',
              shot: 'settings-privacy',
              check: 'Switches save immediately. After changing **Takes to keep**, press **Save**.',
            },
            {
              title: 'Storage',
              text: '**Voice data & projects** and **Model cache** show the folders in use; you can move each to another drive. **Disk usage** shows what takes space; press **Refresh** after a clean-up.',
              shot: 'settings-storage',
              check: '**Disk usage** lists each drive VoiceStudio uses with its free space, then the model cache and the other folders with their sizes. A red line warns when a drive has less than 10 GB free.',
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
            'The option keeps its new value after you leave the page and come back.',
            'Options marked **Takes effect after the app restarts** show the new value after a restart.',
            'If a saved value seems ignored, check for an environment variable of the same name (for example in a Docker `-e` flag or a `.env` file): it wins over the app.',
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
          text: 'Before a bug report, open **Diagnostics** and press **Save diagnostic bundle**. It saves one zip file with the self-check report, recent errors and log excerpts, with sensitive details scrubbed, ready to attach to a GitHub issue.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'Moving your data folder to another computer keeps voices and projects, but saved tokens and API keys cannot be decrypted there. Enter them again in **Credentials** and **Remote GPU**.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Reset & remove** and **Remove all data** in **Storage** delete files for good. Make a **Database backup** first if you may want your voices and projects back.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'With a **VoiceStudio account** and **Cloud sync** turned on, changed settings are also sent to your account. Turning either off stops it at once; nothing is synced by default.',
        },
      ],
    },
  ],
};

export default chapter;
