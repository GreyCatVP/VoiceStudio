import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'clone',
  order: 30,
  title: 'Clone a voice',
  summary:
    'Turn a short recording of a voice into a voice you can type for: add a reference clip, check its transcript, generate, then download the take or keep the voice for later.',
  sections: [
    {
      id: 'what',
      title: 'What voice cloning does',
      blocks: [
        {
          kind: 'p',
          text: 'Voice cloning makes new speech in the voice of a **reference clip**: 5–15 seconds of one person speaking. You type a script, and the engine reads it in that voice. Use it for narration in your own voice, a consistent character voice across many lines, or a voice you will reuse in dubbing and stories.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'Only clone voices you have the right to use: your own, or a speaker who gave you permission. Every generated take carries an inaudible AI watermark.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How cloning works',
      blocks: [
        {
          kind: 'diagram',
          id: 'clone-flow',
          caption:
            'Dashed: automatic transcription only runs when the Transcript field is empty. Here the engine runs on a remote GPU; without one it runs on this computer the same way.',
          text: {
            gpu: 'Remote GPU (Ray)',
            ref: 'Reference clip\n5–15 s',
            asr: 'Automatic\ntranscription (ASR)',
            transcript: 'Transcript\n(you can edit it)',
            script: 'Script, language\nand voice controls',
            request: 'Backend\nPOST /generate',
            prepare: 'Reference prep\n(best window)',
            engine: 'OmniVoice\nclones the voice',
            watermark: 'AI watermark\n+ save WAV',
            history: 'Recent takes\n(history)',
            play: 'Play, download\nor reuse',
            auto: 'if empty',
            fills: 'fills',
            job: 'job',
            audio: 'audio',
            saved: 'saved',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            'You add a reference clip by uploading a file or recording with your microphone.',
            'The app transcribes the clip with the active speech-recognition (ASR) engine and fills the **Transcript** field. You can correct it. A correct transcript gives a closer clone.',
            'When you press **Synthesize audio**, the app sends the clip (or the saved voice), the transcript and your script to the backend.',
            'The backend prepares the reference. A clip longer than the engine accepts (20 s for OmniVoice) is not cut blindly: the engine picks its best window, and then it ignores a transcript of the whole clip.',
            'The engine renders the speech. With a remote GPU configured, OmniVoice runs there as a Ray job; the audio comes back to this computer.',
            'The backend adds the AI watermark, saves the WAV in `omnivoice_data/outputs` and adds the take to **Recent takes**.',
          ],
        },
        {
          kind: 'table',
          head: ['Setting', 'Where', 'What it does'],
          rows: [
            ['**Transcript**', 'Voice sample → Optional details', 'What the reference clip says. Leave it empty to let the engine listen.'],
            ['**Style**', 'Voice sample → Optional details', 'Optional delivery tags, for example `whisper`.'],
            ['Language', 'Bottom bar (**Auto**)', 'The language of the script. **Auto** lets the engine detect it.'],
            ['Speed and quality', 'Bottom bar (**Standard**) and the controls icon', 'Speed, duration and advanced model tuning for this take.'],
          ],
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Clone a voice step by step',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Open Voice cloning and add a reference clip',
              text: 'In the menu open **Voice → Clone**. Under **Add a new voice**, drop an audio file on the box **(1)** or click it to choose one (WAV, MP3, M4A…). To use your microphone, press **Record** **(2)** and read a sentence or two.',
              shot: 'clone-choose',
              check: 'The screen changes to **Save as voice profile**, with your clip and its length below.',
            },
            {
              title: 'Check the clip and its transcript, then save the voice',
              text: 'Play the clip **(1)** and make sure it is one speaker with no music. The app transcribes it into **Transcript** **(2)**; correct any wrong words. Type a **Profile name** **(3)** and press **Save** **(4)**. To try the clip without keeping it, press **Use without saving** instead.',
              shot: 'clone-reference',
              check: 'While the clip is transcribed the button shows **Transcribing…**. After saving, the voice appears in **Saved voices** in the sidebar.',
            },
            {
              title: 'Type a script and generate',
              text: 'The header shows the chosen voice **(1)**; click it to switch voices. Type what the voice should say in **Script** **(2)**. Leave the language on **Auto** **(3)** or pick the script’s language, then press **Synthesize audio** **(4)** (or Ctrl/Cmd + Enter).',
              shot: 'clone-script',
              check: 'The button shows progress. On a remote GPU a short line takes about 20 seconds; the first take after a pause takes longer while the model loads.',
            },
            {
              title: 'Listen to the take and download it',
              text: '**Latest take** **(1)** opens under the script. Press play **(2)** to listen. Press **Save as…** **(3)** to save the WAV file where you want it.',
              shot: 'clone-take',
              check: 'The take shows its length and render time, for example `7.0s · rendered in 21.3s`.',
            },
            {
              title: 'Find earlier takes in Recent takes',
              text: 'Press **Recent takes** in the title bar. The list **(1)** holds every take. Click one to open its details **(2)**: the script, language and seed, a player, **Save as voice profile**, **Lock voice identity**, **Save as…** and **Reuse script**.',
              shot: 'clone-history',
              check: 'The take you just made is at the top of the list.',
            },
            {
              title: 'Review or change the saved voice',
              text: 'Press **Voice sample** at the top right. It shows the saved reference and its stored transcript **(2)**. Press **Edit voice** **(1)** to rename it, replace the clip, or export it (see the Saved voices chapter).',
              shot: 'clone-voice-sample',
              check: 'The pane shows the voice’s name, its reference clip and the transcript you saved.',
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
          shot: 'clone-result',
          items: [
            'The take plays and sounds like the reference speaker, reading your script.',
            '**Save as…** writes a WAV file you can open in any player.',
            'The take appears in **Recent takes**, and the voice appears under **Saved voices**.',
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
          text: 'The reference decides the result. Use 5–15 seconds of clean speech: one speaker, no music, little room echo, at a steady volume. Record again rather than fixing a noisy clip.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'A wrong transcript makes the clone mispronounce words or drift. If **Transcript** says **Transcription failed**, type what the clip says yourself and press **Retry transcription** later.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'Clips longer than 75 seconds are refused. Between 20 and 75 seconds OmniVoice uses only its best window of up to 20 seconds; in that case leave **Transcript** empty, because a transcript of the whole clip will not match.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**Text-to-speech is not ready** means the selected engine cannot run yet: press **Fix**, or open **Settings → Models → TTS**. If generation stops with a licence message, open the model catalogue and accept the model licence (OmniVoice is non-commercial).',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'With a remote GPU, the script and the reference clip are sent to your own Ray cluster for the render. Automatic transcription runs wherever your ASR engine is set to run (Settings → Models → ASR).',
        },
      ],
    },
  ],
};

export default chapter;
