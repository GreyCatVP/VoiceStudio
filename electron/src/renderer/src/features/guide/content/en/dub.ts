import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'dub',
  order: 80,
  title: 'Dub a video',
  summary:
    'Turn a video or audio file into another language with the original speakers’ voices: import, transcribe, translate, cast, generate, check and export.',
  sections: [
    {
      id: 'what',
      title: 'What dubbing does',
      blocks: [
        {
          kind: 'p',
          text: 'The **Dubbing** workspace replaces the speech in a video or audio file with speech in another language. It keeps the music and sound effects, finds who speaks when, and clones each speaker’s voice from the file itself, so the dub sounds like the same people.',
        },
        {
          kind: 'list',
          items: [
            'Use it for one video you want to review line by line: interviews, lessons, short films, product videos.',
            'You can correct the transcript, the translation, the voices and the timing before you export.',
            'For many files with the same settings and no review, use **Batch Dubbing** instead (next chapter).',
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Supported files: MP4, MOV, MKV, WEBM, MP3, WAV, FLAC and M4A, or a YouTube / video link.',
        },
      ],
    },
    {
      id: 'pipeline',
      title: 'How a dub is made',
      blocks: [
        {
          kind: 'diagram',
          id: 'dub-pipeline',
          caption:
            'Blue steps are yours, amber steps run an AI engine, the purple step runs in the backend. The dashed loop is the optional second-pass check.',
          text: {
            import: '1. Import\nfile or link',
            prepare: '2. Prepare\nextract + Demucs',
            transcribe: '3. Transcribe\nASR + speakers',
            review: '4. Review\nlines and speakers',
            translate: '5. Translate\nNLLB, LLM …',
            cast: '6. Cast\na voice per speaker',
            generate: '7. Generate\none line at a time',
            mix: '8. Fit + mix\nwith the music',
            export: '9. Export\nMP4, audio, subtitles',
            qc: 'Verify\n(re-listen)',
            check: 'optional',
            redo: 'regenerate\nflagged lines',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            '**Import** — you choose a file or paste a link. The app uploads it to the backend, which creates a job for it.',
            '**Prepare** — ffmpeg extracts the sound. **Demucs** splits it into the voices (`vocals.wav`) and everything else (`no_vocals.wav`: music, effects, room).',
            '**Transcribe** — speech recognition (Faster-Whisper or your chosen ASR engine) writes the lines with their times. **pyannote** labels who speaks each line (Speaker 1, Speaker 2 …). The backend then cuts a short, clean clip of each speaker from the vocals to clone from.',
            '**Review** — you fix recognition mistakes, split or merge lines, and check the speakers.',
            '**Translate** — the translator you picked (NLLB, Argos, an online service or an OpenAI-compatible LLM) translates every line.',
            '**Cast** — each speaker gets a voice: **Auto** (a clone of that speaker from the video), one of your saved voices, or a design preset.',
            '**Generate** — the TTS engine speaks each translated line in its voice, sized to the time of the original line.',
            '**Fit + mix** — the backend fits each line into its slot, adds an inaudible AI watermark, and lays the lines over the music track.',
            '**Export** — you download a video, an audio file, subtitles or the separate stems.',
          ],
        },
      ],
    },
    {
      id: 'where',
      title: 'What runs where',
      blocks: [
        {
          kind: 'diagram',
          id: 'dub-where',
          caption:
            'With a remote GPU set up (Settings → Remote GPU), the heavy models run there and only audio and text travel; files, editing and the final mix stay on this computer. Without one, every box runs on this computer.',
          text: {
            computer: 'This computer',
            remote: 'Remote GPU (Ray or Modal, optional)',
            ffmpeg: 'ffmpeg: extract sound,\nscene cuts, thumbnail',
            refs: 'Cut speaker clips\nfrom the vocals',
            fit: 'Timing fit, watermark,\nmix with music',
            mux: 'Export: mux video,\nsubtitles, stems',
            edit: 'Your edits\n(app window)',
            demucs: 'Demucs — split vocals / music',
            asr: 'Faster-Whisper (crash-isolated) — ASR',
            diar: 'pyannote — who speaks when',
            mt: 'NLLB-200 — translation',
            tts: 'OmniVoice / VoxCPM2 — the voices',
            send: 'audio in,\nresults back',
            back: 'line text + clip in,\nspeech back',
          },
        },
        {
          kind: 'table',
          head: ['Step', 'Engine', 'Runs'],
          rows: [
            ['Prepare', 'ffmpeg, then Demucs (htdemucs)', 'ffmpeg here; Demucs on the remote GPU when `demucs` is routed there'],
            ['Transcribe', 'The ASR engine in **Settings → Models → ASR**', 'Remote when that engine is routed (for example **Faster-Whisper (crash-isolated subprocess)**), otherwise here'],
            ['Speakers', 'pyannote 3.1 (**Settings → Models → Diarisation**)', 'Remote when `pyannote` is routed; needs the model installed and its licence accepted'],
            ['Translate', 'The engine in **Settings → Models → Translation**', 'NLLB remote when routed; Typhoon Translate (Thai↔English) remote only; Argos here; online services and LLMs at their provider'],
            ['Generate', 'The active TTS engine (must support cloning)', 'Remote when routed, otherwise on this computer’s GPU or CPU'],
            ['Fit, watermark, mix, export, QC scoring', 'Backend + ffmpeg', 'Always here (QC re-uses the ASR engine, so its recognition may run remotely)'],
          ],
        },
      ],
    },
    {
      id: 'storage',
      title: 'Where the files go',
      blocks: [
        {
          kind: 'diagram',
          id: 'dub-storage',
          caption:
            'Every dub has its own job folder. The database keeps the lines, translations and voices so you can close the app and continue later.',
          text: {
            folder: 'Job folder: omnivoice_data/dub_jobs/<job>',
            source: 'Your file\nor link',
            original: 'original.mp4',
            audio: 'audio.wav + audio_hq.wav',
            vocals: 'vocals.wav',
            bed: 'no_vocals.wav',
            refs: 'speaker clips\nrefs/…/voice_*.wav',
            lines: 'seg_<lang>_<line>.wav',
            track: 'dubbed_<lang>.wav',
            db: 'Database\nlines · speakers',
            exports: 'Exports\nMP4 · WAV · SRT …',
            upload: 'upload',
            extract: 'ffmpeg',
            demucs: 'Demucs',
            cut: 'cut clips',
            clone: 'TTS clones',
            assemble: 'fit + mix',
            music: 'music / FX',
            picture: 'picture (MP4)',
            segments: 'transcript',
          },
        },
        {
          kind: 'table',
          head: ['File', 'What it is'],
          rows: [
            ['`original.<ext>`', 'Your upload or the downloaded video, unchanged.'],
            ['`audio.wav`, `audio_hq.wav`', 'The extracted sound: a 16 kHz copy for speech recognition and a full-quality copy for Demucs.'],
            ['`vocals.wav`', 'Only the voices. Transcription and the speaker clips use it.'],
            ['`no_vocals.wav`', 'Music, effects and room sound. It goes under the dub when **Background audio** is on.'],
            ['`refs/<run>/voice_speaker_N.wav`', 'The clip each speaker is cloned from (**Auto** voice). `seg_ref_*.wav` are per-line clips used by **Voice match: Per line**.'],
            ['`seg_<lang>_<line>.wav`', 'One generated line. Only changed lines are regenerated next time.'],
            ['`dubbed_<lang>.wav`', 'The finished voice track of one language, fitted to the timeline.'],
          ],
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Dub a video, step by step',
      blocks: [
        {
          kind: 'p',
          text: 'This walkthrough dubs a 74-second English dialogue between two people, with music, into Thai with **NLLB-200**.',
        },
        {
          kind: 'steps',
          items: [
            {
              title: 'Choose the video',
              text: 'Open **Dubbing** from the workspace menu. Press **Choose file…** (or drop the file on the panel), or paste a link into **…or paste YouTube / video URL** and press **Ingest**. If speech recognition guesses the language wrongly, set it first under **Spoken language**; there you can also set **Speakers** when you know how many people talk.',
              shot: 'dub-import',
              check: 'The file name shows under **Upload & Transcribe** and the preparation starts at once.',
            },
            {
              title: 'Wait for the preparation',
              text: 'The bar at the bottom shows the stage: extracting the sound, **Separating vocals / music (Demucs)…**, then **Transcribing audio…** and the speaker analysis. Long videos take minutes; **Cancel** stops the job.',
              shot: 'dub-prepare',
              check: 'The lines appear on the right, each with its start time and speaker.',
            },
            {
              title: 'Review the lines and speakers',
              text: 'Each line shows its time, its speaker and its text. Click the text to correct it. **More actions** on a line can **Split at cursor**, merge it with its neighbour or add a line. The timeline above shows every line; drag its edges to change the timing. Fix the source text now: wrong words become wrong translations.',
              shot: 'dub-segments',
              check: 'The count above the timeline shows the number of lines, and both speakers appear on the lines.',
            },
            {
              title: 'Choose the language and translate',
              text: 'Under **Dub into**, pick the target language (here **Thai**). **Translator** shows the engine from **Settings → Models → Translation** (here **NLLB-200 (Local, Heavy)**); **Translation quality** **Fast** is literal, **Autofit** and **Cinematic** need an LLM. Press **Translate All**. The first time, NLLB asks you to accept its licence: tick the box, press **Accept licence**, then press **Translate All** again.',
              shot: 'dub-translate',
              check: 'Each line shows the Thai text, with the English original in grey above it. **Tight fit** marks lines that may be too long for their time.',
            },
            {
              title: 'Give each speaker a voice',
              text: 'Open **CAST**. Each detected speaker starts on **Auto · Speaker N**: a clone made from that speaker’s own voice in the video. To use another voice, pick it in the speaker’s list or drag a voice chip onto the speaker. To change one line only, open the line and pick a voice for it.',
              shot: 'dub-cast',
              check: 'Every speaker has a voice. The dub cannot clone a speaker that has no voice and no clip.',
            },
            {
              title: 'Generate the dub',
              text: 'Open **Timing** if you want another fit than the default **Lip sync** (see the table below). Press **Generate Dub**. The bar shows the progress; **Cancel** stops it.',
              shot: 'dub-generate',
              check: 'The banner says **Dub complete** and the bar says **all N segments up to date**.',
            },
            {
              title: 'Check the dub (optional)',
              text: 'Press **Verify** (top right of the line list). Speech recognition listens to the dubbed track and compares it with each line’s text. Lines that sound different get a **Verify** badge: play them, edit the text if needed, and press **Regen N changed** to redo only those lines.',
              shot: 'dub-qc',
              check: 'A message says how many lines may need a re-listen (**N of M lines may need a re-listen**).',
            },
            {
              title: 'Export',
              text: 'Open **Export options** at the bottom of the left panel. Pick a **Format**: **MP4 (H.264)** for the video, **WAV**/**MP3** for audio, **SRT**/**VTT**/**Karaoke** for subtitles, **Stems (.zip)** or **Per-segment clips (.zip)**. For MP4, choose which tracks to include and the **Default audio track**. Keep **Background audio** on to keep the music. Press **Export**.',
              shot: 'dub-export',
              check: 'The file downloads (the desktop app asks where to save it).',
            },
          ],
        },
        {
          kind: 'table',
          head: ['Timing', 'What it does', 'Use it when'],
          rows: [
            ['**Lip sync** (default)', 'Speaks each line to the length of the original line, and speeds it up (pitch kept) if it is still too long.', 'Faces on screen; the timing must match.'],
            ['**Concise**', 'Speaks at a natural pace and lets a line run into the following silence. If a line is still too long, generation stops and tells you to shorten it.', 'Natural speech matters more than exact timing.'],
            ['**Smart Fit**', 'Speeds the voice up a little (up to 1.5×) and slows that part of the video (up to 2×). **Fastest speed** and **Slowest speed** set the limits. Export re-encodes the video.', 'The target language is much longer than the source.'],
            ['**Stretch Video**', 'Keeps the voice natural and stretches the video to fit. Export subtitles separately.', 'Screen recordings and slides, where stretched video is not noticed.'],
          ],
        },
        {
          kind: 'table',
          head: ['Setting', 'Where', 'Effect'],
          rows: [
            ['**Voice match: Per line** / **Consistent**', '**Timing**', 'Per line clones each line from its own source clip (closest delivery). Consistent uses one clip per speaker (steadier voice).'],
            ['**Translate with Agent**', 'Translator', 'Translates with an LLM or a local coding agent, with an optional **Translation style prompt**.'],
            ['**+ Glossary**', 'Line list toolbar', 'Terms that must always be translated the same way (names, products).'],
            ['**Manage languages**', 'Under **Dub into**', 'Adds more target languages; **Generate Dub** then makes one track per language.'],
            ['**Import .srt**', 'Under **Upload & Transcribe**', 'Uses your own subtitles as the lines instead of speech recognition.'],
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
            'Under **Preview**, press **Dubbed (th)** and play: you hear the Thai voices over the original music.',
            'Each speaker keeps a voice close to the original speaker.',
            'The lines start where the original lines start (watch the mouths in **Lip sync** mode).',
            'The exported MP4 has the original and the dubbed audio tracks; your player can switch between them.',
          ],
          shot: 'dub-result',
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
          text: '**All lines are one speaker.** pyannote is missing or not allowed yet. Open **Settings → Models → Diarisation**, open **Hugging Face access is required…**, press **Request model access** and **Accept segmentation terms** on Hugging Face, add your token with **Add Hugging Face token**, press **Check access**, then **Download** and transcribe again. If two people still share a label, set **Speakers** under **Spoken language**.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: '**One line holds two speakers.** Speech recognition sometimes joins a quick reply to the line before it. Place the cursor where the second speaker starts, use **More actions → Split at cursor**, and give the new line the right voice.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Transcription timed out.** On a computer without a strong GPU, local speech recognition can be very slow and use a lot of memory. Select **Faster-Whisper (crash-isolated subprocess)** in **Settings → Models → ASR** (it can run on your remote GPU), then press **Retry**. The prepared audio is kept, so Demucs does not run again.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**Licence acceptance needed.** Some models (NLLB-200, pyannote) have their own licences. The dialog shows what each licence allows; NLLB-200 is for personal and research use only. Accepting is recorded once per model.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: '**Changed a few lines?** Edit them and press **Regen N changed**: only those lines are generated again and the mix is rebuilt.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: '**The same video again** reuses its Demucs result (the stage shows **cached**), so a second dub of the same file starts much faster.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**Your work is saved as you go.** Close the app during a dub and the workspace reopens with your lines; an interrupted step shows **Retry**. Use **Projects** to keep several dubs.',
        },
      ],
    },
  ],
};

export default chapter;
