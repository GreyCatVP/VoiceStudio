import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'transcribe',
  order: 100,
  title: 'Transcribe and dictate',
  summary:
    'Turn audio files and recordings into text, and dictate into any app with a keyboard shortcut. Everything runs on this computer, or on your own remote GPU if you routed the engine there.',
  sections: [
    {
      id: 'what',
      title: 'What the Transcribe workspace does',
      blocks: [
        {
          kind: 'p',
          text: 'Open **Transcribe** from the workspace menu. It does two jobs: it transcribes an audio file or a recording you make in the app, and it is the home of **Dictation**, which types what you say into the app you are working in.',
        },
        {
          kind: 'list',
          items: [
            '**File transcription** — upload a `.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg` or `.webm` file, or press **Record**. The text appears in the workspace and in its **History**.',
            '**Dictation** — press the dictation shortcut anywhere (desktop app only), speak, press it again. The text is typed where your cursor is.',
            'Every result is kept in the **History** list on the left, where you can search, copy, export or delete it.',
          ],
        },
      ],
    },
    {
      id: 'how',
      title: 'How a transcription works',
      blocks: [
        {
          kind: 'diagram',
          id: 'transcribe-flow',
          caption:
            'Fast mode uses the dictation model; Accurate mode uses the ASR engine selected in Settings, which may run on your Ray cluster. Only Accurate mode asks for word timing.',
          text: {
            pick: '1. Upload or\nrecord audio',
            send: '2. Backend\nchecks the model',
            decode: '3. Decode to\n16 kHz mono',
            fast: 'Fast:\ndictation model',
            accurate: 'Accurate:\nselected ASR engine',
            ray: 'Ray cluster\n(if routed there)',
            align: 'Word timing\n(alignment)',
            polish: 'Clean up\nthe text',
            result: 'Transcript +\nsegments',
            history: 'History\n(in this app)',
            routed: 'remote job',
            saved: 'saved',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            'The app first asks the backend whether a model for the chosen mode is installed. If not, it shows what to install instead of failing.',
            'The file goes to the backend on this computer (`/transcribe`). The engine reads it as 16 kHz mono audio, the format speech models expect.',
            '**Fast** runs the dictation model you chose (for example Whisper Tiny or Parakeet). **Accurate** runs the ASR engine selected in **Settings → Models → ASR** (for example Faster-Whisper large-v3) and asks it for word-level timing; WhisperX also aligns each word to the audio.',
            'If that ASR engine is routed to your Ray cluster (**Settings → Remote GPU**), the audio is sent there as a job and the text comes back. Otherwise it runs here.',
            'The backend removes repeated-phrase glitches and adds a leading capital and final punctuation. If **Dictation cleanup** is on and an LLM is set up, a cleaned-up version is added next to the original.',
            'The result (text, timed segments, length, and the detected language when the engine reports one) is shown and saved in the workspace History.',
          ],
        },
        {
          kind: 'table',
          head: ['Choice', 'Where you set it', 'What it changes'],
          rows: [
            ['**Fast** / **Accurate**', 'The switch at the top of the workspace', 'Fast: the low-latency dictation model. Accurate: the selected ASR model, with detailed timestamps.'],
            ['Dictation model', '**Settings → Models → Dictation**', 'Used by Fast mode and by dictation. Small, runs on the CPU.'],
            ['ASR engine and model', '**Settings → Models → ASR**', 'Used by Accurate mode, dubbing and voice cloning.'],
            ['Language', '—', 'Detected automatically; there is no language picker. When the engine reports the language it detected, it is shown with the result; otherwise no language is shown.'],
            ['Speakers', '—', 'This workspace does not separate speakers. Use **Dubbing** for speaker diarization.'],
            ['Input device', '**Input device** under the switch', 'The microphone used by **Record** and **Dictation**.'],
          ],
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Transcribe a file',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Choose a mode and add audio',
              text: 'Pick **Fast** or **Accurate** (**1**). The model that will be used is shown next to it (**2**). Then press **Upload audio** (**3**) and choose a file, or press **Record** (**4**) to record from your microphone and press it again to stop.',
              shot: 'transcribe-start',
              check: 'The buttons are enabled. If they are greyed out, a model is missing: see the tips below.',
            },
            {
              title: 'Wait for the transcript',
              text: 'While it works the toolbar shows **Transcribing…** with a **Cancel** button. A short clip takes a few seconds in Fast mode; Accurate mode on the CPU can take a minute.',
              shot: 'transcribe-result',
              check: 'The new entry is selected in **History** (**1**) and its text is shown (**2**). Use **Copy** (**3**) or **Export** (**4**) to save it as a `.txt` file, or **Reuse script** (**5**) to send the text to Voice cloning.',
            },
            {
              title: 'Check the timing',
              text: 'Open **Segments** (**1**) to see each part of the transcript with its start and end time. The player at the bottom (**2**) plays the file you transcribed.',
              shot: 'transcribe-segments',
              check: 'Each segment has a time range such as `0.0s – 4.8s`.',
            },
          ],
        },
        {
          kind: 'verify',
          items: [
            'The transcript matches what is said in the audio.',
            'The entry stays in **History** after you leave the workspace and come back.',
            '**Export all** at the bottom of History saves every transcript, with date and language, to one `.txt` file.',
          ],
          shot: 'transcribe-verify',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Exports are plain text (`.txt`). The workspace has no SRT or VTT export; for subtitles use **Dubbing**, which exports subtitle files.',
        },
      ],
    },
    {
      id: 'models',
      title: 'Choose the engines',
      blocks: [
        {
          kind: 'p',
          text: 'Accurate mode uses the ASR model marked active in **Settings → Models → ASR**. Changing it there also changes the engine used by dubbing and voice cloning.',
        },
        { kind: 'shot', id: 'transcribe-asr-settings', caption: '**1** The active ASR model, used by Accurate mode.' },
        {
          kind: 'p',
          text: 'Fast mode and dictation use the model chosen in **Settings → Models → Dictation**. If none is installed, the Transcribe workspace shows a short list of dictation models; pick one and it downloads and becomes active.',
        },
      ],
    },
    {
      id: 'dictation',
      title: 'Dictation with the shortcut',
      blocks: [
        {
          kind: 'p',
          text: 'Dictation types what you say into whatever app has the focus: your editor, mail or chat. It needs the **desktop app** (the browser version cannot press keys in other apps) and a microphone. The default shortcut is `Ctrl+Shift+Space` (`Cmd+Shift+Space` on a Mac).',
        },
        {
          kind: 'diagram',
          id: 'transcribe-dictation',
          caption:
            'The audio streams to the backend while you speak; the text is typed when you stop. If the app cannot type into the focused window, it copies the text to the clipboard instead.',
          text: {
            key: '1. Press the\nshortcut',
            helper: '2. The app starts\na dictation session',
            mic: '3. Microphone\n→ 16 kHz audio',
            ws: '4. Streamed live\nto the backend',
            model: '5. Dictation model\nturns it into text',
            stop: 'Press again\n(Hold: release)',
            history: 'History\n(Transcribe)',
            clip: 'Clipboard\n(paste it yourself)',
            deliver: '6. Text is typed into\nthe focused app',
            text: 'text',
            fallback: 'if typing\nis blocked',
            saved: 'saved',
            eof: 'stop: mic off,\nfinish the text',
          },
        },
        {
          kind: 'table',
          head: ['Setting', 'Where', 'What it does'],
          rows: [
            ['**Dictation Mode**: **Toggle** / **Hold**', '**Settings → Models → Dictation → Dictation shortcut**', 'Toggle: press once to start, again to stop. Hold: dictate while the key is held.'],
            ['**Vocabulary hint**', 'Same section', 'Names and terms the model should prefer. Applied to dictation only, never to file transcription.'],
            ['**Active shortcut**', 'Same section (desktop app)', 'Shows the key combination and lets you change it or **Reset to default**.'],
            ['**Dictation cleanup**', 'Below the shortcut section', 'Optional clean-up of the final text (filler words, self-corrections, punctuation) by an LLM you set up. Echo cancellation, further down, removes the app\'s own playback from the microphone.'],
          ],
        },
        { kind: 'shot', id: 'transcribe-dictation-settings', caption: '**1** Toggle or Hold. **2** The vocabulary hint. Below them: **Dictation cleanup**.' },
        {
          kind: 'p',
          text: 'You can also dictate inside the workspace: press **Dictation** in the toolbar (or **Start dictation** when History is empty). While it listens you can **Pause**, **Stop** or **Cancel**; the text is saved to History but not typed anywhere.',
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
          text: '**The buttons are greyed out, or you see "No speech-to-text model is installed".** Fast mode needs a dictation model; Accurate mode needs an ASR model. Use the list shown in the workspace, or the **ASR** button that opens **Settings → Models → ASR**.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**"Transcription failed".** Open **Technical details** under the message to read the cause, press **Retry**, or open **Logs**. A file without an audio track, a missing `ffmpeg`, or a model whose licence you have not accepted are the common causes.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Accurate mode with a large Whisper model is slow on a CPU and needs several GB of memory. Use Fast mode for quick notes, or route the ASR engine to your remote GPU.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: '**"No speech detected"** after dictation means the microphone sent silence. Check **Input device** and your system\'s microphone permission.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Transcripts are stored in this app on this computer, not in the backend\'s data folder. **Clear all** removes them for good.',
        },
      ],
    },
  ],
};

export default chapter;
