import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'troubleshooting',
  order: 170,
  title: 'Troubleshooting',
  summary:
    'Where to look when something fails: the error card, the self-check, the logs, the remote GPU test and the bug report. Ends with a table of common error messages and what to do about each.',
  sections: [
    {
      id: 'what',
      title: 'Where problems show up',
      blocks: [
        {
          kind: 'p',
          text: 'Most problems explain themselves where they happen: a red error card in the workspace says what went wrong and usually what to do. When it does not, four screens help you find the cause, and one button turns it into a bug report.',
        },
        {
          kind: 'table',
          head: ['Screen', 'Where', 'Use it for'],
          rows: [
            ['Error card', 'In the workspace, under the button you pressed', 'The message, **Open docs** for that kind of error, **Copy diagnostic** for the full text'],
            ['System check', '**Settings → Compute device**', 'RAM, disk, GPU and network before you download models'],
            ['Self-check', '**Settings → Diagnostics**', 'Checks of this install (engines, ffmpeg, token, disk, GPU routing, network), a diagnostic bundle'],
            ['Logs', '**Settings → Logs**', 'What the backend and the window did, line by line'],
            ['Remote GPU test', '**Settings → Remote GPU**', 'Whether your Ray cluster is reachable and can run a job'],
            ['Report a bug', '**Settings → Support**, and on crash screens', 'A prefilled GitHub issue in your browser'],
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Nothing is sent anywhere by these tools. **Report a bug** only opens a GitHub page in your browser; it is submitted when you click **Submit** there. The diagnostic bundle is a file you choose to attach.',
        },
      ],
    },
    {
      id: 'where',
      title: 'Something failed: where to look',
      blocks: [
        {
          kind: 'diagram',
          id: 'troubleshooting-where',
          caption:
            'Start at the top. Each branch ends in a screen of this chapter; the logs are the common fallback.',
          text: {
            fail: 'Something failed',
            q1: 'Did an error card\nappear?',
            a1: 'Read it: Open docs,\nCopy diagnostic, Fix',
            q2: 'Engine, model or\nsetup problem?',
            a2: 'Diagnostics:\nRun self-check',
            q3: 'Engine on your\nremote GPU?',
            a3: 'Remote GPU:\nTest connection',
            logs: 'Settings → Logs\n(filter WARNING, ERROR)',
            agent: 'Ask VoiceStudio Agent\n(desktop app)',
            report: 'Report a bug\n(+ diagnostic bundle)',
            yes1: 'yes',
            no1: 'no',
            yes2: 'yes',
            no2: 'no',
            yes3: 'yes',
            no3: 'no',
            unclear: 'still unclear',
            desktop: 'let an agent fix it',
            stuck: 'still stuck',
          },
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Diagnose step by step',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Read the error card',
              text: 'An error card (1) gives the cause in one sentence. Longer errors add **Copy diagnostic** with the full text, and known kinds add **Open docs**. Here, **Probe file** was given a path that does not exist.',
              shot: 'troubleshooting-error-card',
              check: 'You know whether the problem is your input (a path, a file, a missing voice) or the setup (an engine, a model, the GPU).',
            },
            {
              title: 'Check what this install runs',
              text: 'Open **Settings → Diagnostics**. **About** shows the app version (1), the compute device (2), the active TTS model (3) and where your data lives (4). Include these in any report.',
              shot: 'troubleshooting-about',
              check: '**Compute device** names your GPU, or `cpu` when none is used.',
            },
            {
              title: 'Run the self-check',
              text: 'Scroll to **Diagnostics** and press **Run self-check** (1). **Save diagnostic bundle** (2) writes a zip with the report and scrubbed logs; **Copy diagnostics** (3) copies the report as text. Each warning or failure (4) has a hint and, where there is one, an **Open** link to the page that fixes it.',
              shot: 'troubleshooting-self-check',
              check: '"All checks passed — this install looks healthy." or a count of failed checks with hints. This computer has no GPU, so **Compute device** is a warning.',
            },
            {
              title: 'Read the logs',
              text: 'Open **Settings → Logs**. Choose **Backend** (1) for the server or **Frontend** for the window, and type a word in the search box (2), such as `WARNING`, `ERROR` or an engine name. In the desktop app, **Ask VoiceStudio Agent** (3) sends the visible warnings and errors to a local coding agent.',
              shot: 'troubleshooting-logs',
              check: 'Warnings have a yellow edge and errors a red one. The newest lines are at the bottom.',
            },
            {
              title: 'Test the remote GPU',
              text: 'If the failing engine runs on your Ray cluster, open **Settings → Remote GPU** and press **Test connection** (1). It runs a small probe job and can take up to 3 minutes.',
              shot: 'troubleshooting-remote-test',
              check: '"Connected to the Ray cluster." (2). Any other message names the problem: the address, the credentials, or a job that failed or timed out.',
            },
            {
              title: 'Report a bug',
              text: 'Open **Settings → Support**. Under **Ways to get in touch**, press **Report a bug** (1). The same button appears on the backend failure screen and the crash screen.',
              shot: 'troubleshooting-report',
              check: 'Your browser opens a GitHub issue prefilled with the app version, platform, GPU, active engines and, for a crash, a scrubbed log tail. Review it, add what you did, and click **Submit** yourself. Drag the diagnostic bundle onto the issue if you saved one.',
            },
          ],
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'If an update is already available, **Report a bug** first asks whether to look at it: the bug may already be fixed. Choose **File anyway** to continue.',
        },
      ],
    },
    {
      id: 'errors',
      title: 'Common error messages',
      blocks: [
        {
          kind: 'table',
          head: ['Message (starts with)', 'What it means', 'What to do'],
          rows: [
            ['Licence not accepted for …', 'The model\'s licence has not been accepted on this computer.', 'Open **Settings → Models**, review and accept the licence, then retry.'],
            ['No speech-to-text model is installed. Download …', 'Transcription, dubbing or Convert needs a speech recognition model.', 'Download the named model from its Weights list in **Settings → Models**, or press **Fix** in the desktop app.'],
            ['TTS engine \'…\' could not load its model.', 'Usually the first download of the model failed.', 'Open the engine in **Settings → Models**, check its weights, then retry.'],
            ['Model weight download failed: …', 'An engine install could not download its weights.', 'Run the install again: it resumes. If it keeps failing, check **Settings → Network**.'],
            ['Set a valid HF_TOKEN … If the model is gated …', 'Hugging Face refused the download: no token, a wrong token, or terms not accepted.', 'Add your token in **Settings → Credentials**; for a gated model, accept its terms on huggingface.co first.'],
            ['… ran out of GPU memory', 'The GPU is full.', 'Close other GPU apps, unload models you are not using, then retry; or pick a smaller engine or another device in **Settings → Compute device**.'],
            ['The machine ran out of memory during generation.', 'System RAM is full (common on CPU-only computers).', 'Close memory-heavy apps, render a shorter passage, or choose a lighter engine.'],
            ['TTS engine stopped mid-generation. This usually means it ran out of memory.', 'The engine crashed during a take.', 'Press **Flush caches** in **Settings → Compute device** to free memory and reload the model, then generate again.'],
            ['Generation exceeded the compute-time limit.', 'The take took longer than its time budget.', 'Try a shorter passage or a CPU-tuned engine (OmniVoice GGUF, Supertonic-3), or raise the budget in **Settings → Compute device**.'],
            ['Generation capacity is busy. Try again shortly.', 'Another heavy job is using the GPU.', 'Wait for it to finish, then retry.'],
            ['Transcription needs ffmpeg …', 'The media tools are missing or broken.', 'Open **Settings → Audio tools** and use Download or Repair, then retry.'],
            ['No speech was recognized in the source clip …', 'The recording is silent, too quiet or only noise.', 'Record or choose a clip with clear speech.'],
            ['Choose a ready text-to-speech model that supports voice cloning.', 'The active engine cannot clone voices.', 'Pick a cloning engine (for example OmniVoice) with the **Models** link.'],
            ['Could not reach the dashboard. Check the URL and your network.', 'The Ray dashboard address does not answer.', 'Check **Dashboard URL** in **Settings → Remote GPU** and your network.'],
            ['The cluster rejected the credentials. …', 'The Ray token or Cloudflare Access keys are wrong.', 'Re-enter them in **Settings → Remote GPU**, **Save**, then **Test connection**.'],
            ['No Ray node has … GPU(s) for …', 'No cluster machine has the GPU share a job asks for.', 'Add a GPU node, or lower **GPU share per job** (0 runs on the cluster CPU).'],
            ['Ray job … made no progress for …', 'A remote job stalled.', 'Retry; if it repeats, check the cluster and the logs.'],
            ['Request refused: it came from another website.', 'A web page on another address called the backend.', 'Use the app itself, or add that address to `OMNIVOICE_ALLOWED_ORIGINS`.'],
          ],
        },
      ],
    },
    {
      id: 'verify',
      title: 'Check that it is fixed',
      blocks: [
        {
          kind: 'verify',
          items: [
            '**Run self-check** reports no failures (warnings you understand, such as CPU-only, are fine).',
            'The task that failed runs again without the error card.',
            '**Settings → Logs** shows no new red lines while you repeat it.',
          ],
        },
      ],
    },
    {
      id: 'tips',
      title: 'Tips',
      blocks: [
        {
          kind: 'note',
          tone: 'tip',
          text: '**Ask VoiceStudio Agent** and the **Fix** buttons exist only in the desktop app and need a local coding agent (Codex, Claude Code, OpenCode or Pi). The agent receives your report, the current screen, recent logs and diagnostics; it never decides licences, credentials or privacy choices for you.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Logs and the diagnostic bundle stay on this computer. The bundle\'s log text is scrubbed of personal paths and tokens because it is meant to be attached to a public issue; read it before you attach it.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'Before a first model download, run **System check** in **Settings → Compute device**: it flags too little disk space or RAM before you wait for a multi-gigabyte download.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Some log lines that only report timings, such as `render trace`, can appear in red even when nothing failed. Look for `WARNING` and `ERROR` at the start of the message.',
        },
      ],
    },
  ],
};

export default chapter;
