import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'tools',
  order: 130,
  title: 'Tools',
  summary:
    'Five small utilities in one workspace: parse a direction, check whether a translated line fits its time slot, inspect a media file, compare two voices, and convert a recording into another voice.',
  sections: [
    {
      id: 'what',
      title: 'What the Tools workspace is',
      blocks: [
        {
          kind: 'p',
          text: 'Open **Tools** in the workspace menu. The list on the left holds five tools. Each one runs only when you press its button, and switching tools cancels a request that is still running.',
        },
        {
          kind: 'table',
          head: ['Tool', 'You give it', 'You get back', 'Runs on'],
          rows: [
            ['**Directorial AI**', 'A direction in plain words, for example "urgent and surprised"', 'The style tokens, the TTS instruction, a translation hint and a speech-rate bias', 'The backend (a language model when one is set up, otherwise a built-in word list)'],
            ['**Speech-rate fit**', 'A translated line, its slot in seconds and the target language', 'How long the line reads compared to the slot, and a shortened or lengthened line', 'The backend (a language model rewrites the line; without one it only measures)'],
            ['**Probe file**', 'The absolute path of a file on the backend computer', 'Its codecs, streams, sample rate, bit depth and duration (ffprobe)', 'The backend (ffprobe)'],
            ['**A/B Voice Comparison**', 'A test phrase and two voices', 'Two takes side by side, also saved to your history', 'Your text-to-speech engine, here or on your remote GPU'],
            ['**Convert**', 'A recording and a saved voice', 'The same words spoken in that voice, and the transcript', 'Speech recognition, then your text-to-speech engine'],
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Directorial AI and Speech-rate fit are the same steps the dubbing pipeline uses for each line. The Tools workspace lets you try them on one line before a long dub.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How Convert works',
      blocks: [
        {
          kind: 'diagram',
          id: 'tools-convert',
          caption:
            'Convert keeps the words and replaces the voice. The dashed step only runs when **Match source duration** is on.',
          text: {
            source: 'Source clip\n(drop or record)',
            voice: 'Target voice\n(saved profile)',
            api: 'Backend\nPOST /convert',
            asr: 'Speech recognition\n(active ASR model)',
            text: 'Clean the text\n(numbers to words)',
            tts: 'Speak it in the\ntarget voice\n(TTS engine)',
            stretch: 'Time-stretch\n(0.5–2×, same pitch)',
            mark: 'Watermark\n+ save',
            result: 'Converted take\n+ What it heard',
            history: 'History',
            profile: 'reference clip',
            words: 'transcript',
            optional: 'if on',
            saved: 'saved',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            'The app uploads the clip (up to 64 MB) with the chosen voice.',
            'The active speech recognition model writes down what was said. Silence or noise stops here with "No speech was recognized".',
            'The text is cleaned the same way as in text to speech, then the active TTS engine speaks it with the voice\'s reference clip.',
            'With **Match source duration** on, the take is time-stretched toward the clip\'s length, by at most 2× either way.',
            'The take gets the inaudible AI watermark and is saved to your history like any other generation.',
          ],
        },
        {
          kind: 'p',
          text: '**A/B Voice Comparison** is simpler: it sends the same phrase to text to speech twice, once per voice, one after the other. A side can be a saved voice or a built-in preset (marked **(Preset)**), which is a set of style instructions rather than a recording.',
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Use each tool',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Parse a direction',
              text: 'Select **Directorial AI** (1), type a direction in **Direction** (2) and press **Parse** (3).',
              shot: 'tools-direction',
              check: 'The result (4) shows **method:** (`heuristic` without a language model, `llm` with one), **tts instruct:**, **translate hint:** and **rate bias:** (above 1 means a faster delivery). Open **tokens** to see the style words it found.',
            },
            {
              title: 'Check a line against its time slot',
              text: 'Select **Speech-rate fit**. Paste the translated line (1), set **Slot (seconds)** (2) and **Target language** (3), then press **Fit** (4).',
              shot: 'tools-rate-fit',
              check: 'The result (5) shows **ratio:** (how long the line reads compared with its slot; 1.0 fits exactly), **attempts:** and **result:**, the line to use. A red note saying no language model is set up means the line comes back unchanged and was only measured.',
            },
            {
              title: 'Inspect a media file',
              text: 'Select **Probe file**, type the full path of a file on the computer that runs the backend (1) and press **Probe** (2).',
              shot: 'tools-probe',
              check: 'The result (3) lists each stream with its codec, sample rate and channels, and the file\'s duration.',
            },
            {
              title: 'Compare two voices',
              text: 'Select **A/B Voice Comparison**. Type a test phrase (1), pick a voice under **Voice A** (2) and under **Voice B** (3), then press **Compare** (4).',
              shot: 'tools-compare',
              check: 'The button reads **Generating Voice A...**, then **Generating Voice B...**. Each side then has a player with its own take.',
            },
            {
              title: 'Prepare a conversion',
              text: 'Select **Convert**. Drop a recording on **Source clip** or click it to choose a file, or press **Record** (1). Pick the target voice (2). Leave **Match source duration** (3) on to keep the timing close, then press **Convert** (4).',
              shot: 'tools-convert-input',
              check: 'The clip\'s name and waveform appear, and the chosen voice is highlighted.',
            },
            {
              title: 'Get the converted take',
              text: 'Wait while the button reads **Converting…**. Recognition and synthesis each take a few seconds to a minute, depending on your hardware.',
              shot: 'tools-convert-result',
              check: '**Converted take** (1) shows a player and **What it heard**, the transcript the new take was spoken from.',
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
            'Directorial AI turns "urgent and surprised, a little louder" into the instruction `surprised, urgent` and a rate bias of `1.1`.',
            'Probe file reports the duration you expect (a 4.8 s WAV shows `"duration": "4.800000"`).',
            'Both comparison takes play, and they also appear in your generation history.',
            'The converted take says the words under **What it heard** in the target voice, and its length is close to the source clip.',
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
          text: 'Speech-rate fit only rewrites lines when a language model is set up in **Settings → Models → LLM**. A line that reads in 0.92 to 1.08 times its slot already fits and is left alone.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Convert** is disabled with "Choose a ready text-to-speech model that supports voice cloning." when the active engine cannot clone. Use the **Models** link next to it to pick one, such as OmniVoice.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'Convert needs a speech recognition model. When none is installed, the error offers **Models** (and **Fix** in the desktop app) to install one; your clip and voice stay selected for the retry.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Only voices with a reference recording, a locked take or a saved design appear under **Target voice**. Convert keeps the words but not the original pitch, pauses or emotion of the recording.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**Probe file** reads paths on the computer that runs the backend, and only for requests from that computer. "File not found. Provide an absolute path to an existing file." means the path is wrong or relative; "ffprobe binary not available" means the media tools are missing: open **Audio tools** under the button.',
        },
      ],
    },
  ],
};

export default chapter;
