import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'workflows',
  order: 110,
  title: 'Workflows',
  summary:
    'Chain voice steps — speak, transcribe, translate, change the voice, normalize — on a canvas, and run the chain over many scripts or clips at once. Drafts stay on this computer; phone calls only start after you confirm.',
  sections: [
    {
      id: 'what',
      title: 'What a workflow is',
      blocks: [
        {
          kind: 'p',
          text: 'A workflow is a small graph of steps drawn on a canvas. The first step supplies the input (scripts or audio clips), each following step changes it, and **End** marks the result you export. When you run a workflow, every script or clip goes through the whole chain, one after another.',
        },
        {
          kind: 'list',
          items: [
            'Use it for repeated jobs: narrate 20 lesson scripts with one voice, transcribe a folder of recordings, or translate and re-voice a set of clips.',
            'Open it from the workspace menu: **Workflows**.',
            'Workflows are saved automatically in this app on this computer. They are not uploaded anywhere.',
          ],
        },
      ],
    },
    {
      id: 'blocks',
      title: 'The building blocks',
      blocks: [
        {
          kind: 'table',
          head: ['Step', 'Takes', 'Gives', 'What it does'],
          rows: [
            ['**Start**', '—', 'text', 'Your scripts. Separate clips with a line containing `---`, or **Import scripts** (up to 50, each up to 20,000 characters).'],
            ['**Source clip**', '—', 'audio', 'Audio files you add with **Add audio** (up to 50 clips, 64 MiB each).'],
            ['**Speak**', 'text', 'speech', 'Speaks the text with a saved voice (**Target voice**), **Language** and **Speed**, using the current TTS engine.'],
            ['**Transcribe**', 'audio or speech', 'text', 'Turns audio into text with the selected ASR engine. The language is detected automatically.'],
            ['**Translate**', 'text', 'text', 'Translates from a **Source language** to a target **Language** with an installed local model (Argos or NLLB).'],
            ['**Convert**', 'audio or speech', 'speech', 'Changes the voice of a clip to a saved voice.'],
            ['**Normalize audio**', 'speech', 'speech', 'Sets the peak level of generated speech (**Peak (dBFS)**, -24 to -1).'],
            ['**Condition**', 'text', 'text', 'Sends the text down its **Yes** or **No** handle depending on whether it **Contains**, **Is exactly**, **Starts with** or **Ends with** a phrase (capitals ignored).'],
            ['**End**', 'anything', '—', 'The output of that path. Each clip shows a player or its text, with **Export**.'],
            ['**Agent**, **Call**', '—', '—', 'Local drafts for phone-call tasks. They are not run by **Run workflow**; a Call step opens the **Calls** form instead.'],
          ],
        },
        {
          kind: 'p',
          text: 'Templates give you ready graphs: **Batch narration**, **Batch narration · Normalize audio**, **Audio to transcript**, **Change the voice**, **Translate and narrate**, and three phone-call drafts.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How a run works',
      blocks: [
        {
          kind: 'diagram',
          id: 'workflows-run',
          caption:
            'Nothing runs until the whole graph passes the check. Each step\'s result is saved before the next starts, so a cancelled or interrupted run resumes where it stopped.',
          text: {
            design: '1. Design the\ngraph',
            drafts: 'Drafts\n(this app)',
            run: '2. Press\nRun workflow',
            check: '3. Check the\nwhole graph',
            invalid: 'Message says\nwhat to fix',
            loop: '4. Each script or\nclip, in order',
            step: '5. Each step calls the\nbackend (TTS, ASR, …)',
            checkpoint: 'Result saved\nafter every step',
            output: '6. Play or export\neach result',
            autosave: 'auto-saved',
            fail: 'invalid',
            next: 'next step',
            saved: 'checkpoint',
          },
        },
        {
          kind: 'list',
          items: [
            'The check requires exactly one input step, every step connected from it to an **End**, no loops, and only a **Condition** may branch (both its Yes and No must be connected). Each step must receive the kind of value it accepts (text, audio or speech).',
            'Clips run one at a time so two models never compete for memory. Each step uses the same backend service as its workspace: Speak uses voice generation, Transcribe uses the ASR engine, Translate uses dubbing\'s translation, Convert uses voice conversion — locally or on your remote GPU, as configured.',
            'If a clip fails, the run stops there and shows the error; press **Retry** to continue. Changing a step\'s settings after a run shows "Settings changed" and the next run creates new outputs.',
          ],
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Build and run a narration workflow',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Open Workflows',
              text: 'The rail on the left lists your workflows (**1**), the **Templates** (**2**) and the steps you can add (**3**). The canvas (**4**) shows the selected workflow; **Run workflow** (**5**) opens the run panel.',
              shot: 'workflows-canvas',
              check: 'A workflow with **Start → Speak → End** is shown on the canvas.',
            },
            {
              title: 'Start from a template and add scripts',
              text: 'Press **Batch narration** (**1**). The new workflow opens with its **Start** step selected (**2**). Type your scripts under **Scripts** (**3**); a line with `---` starts a new clip.',
              shot: 'workflows-template',
              check: 'The Start card shows the number of scripts.',
            },
            {
              title: 'Choose the voice',
              text: 'Click the **Speak** card (**1**). In **Step details**, pick a saved voice under **Target voice** (**2**) and, if you like, the **Language** (**3**) and **Speed**.',
              shot: 'workflows-speak',
              check: 'The Speak card shows the voice name instead of "Pick a voice profile…".',
            },
            {
              title: 'Run it',
              text: 'Press **Run workflow**, then **Run workflow** again in the **Run workflow** panel that opens. Progress shows how many clips are ready (**1**). Each finished clip gets a player (**2**) and an **Export** button (**3**) that saves it as a `.wav` file.',
              shot: 'workflows-run',
              check: 'The counter reaches, for example, `2 / 2 clips ready` and every clip says **done**.',
            },
          ],
        },
        {
          kind: 'verify',
          items: [
            'Every clip shows **done** and plays the expected text in the chosen voice.',
            'Leave the workspace and come back: the run and its audio are still there, and **Start a new run** starts over.',
          ],
        },
      ],
    },
    {
      id: 'calls',
      title: 'Calls run only when you confirm',
      blocks: [
        {
          kind: 'p',
          text: 'A **Call** step describes a phone task: **Phone number** and **What should it do?**. Building it on the canvas never dials. **Prepare call** (or the **Calls** button in the title bar) opens the Calls view with the number and task filled in.',
        },
        {
          kind: 'shot',
          id: 'workflows-calls',
          caption: '**1** Back to the canvas. **2** The new-call form: number, task, voice and what it says first. The checklist above it shows the setup that is still missing.',
        },
        {
          kind: 'list',
          items: [
            'Calls need a one-time setup, listed under **Finish setup to place calls**: a Twilio account, a public link for Twilio, a number to call from, a language model, an ASR engine, and a voice that may place calls (one you verified as your own, or a designed voice). Until every item is ready, the call button stays disabled.',
            'Pressing the call button opens a confirmation, **Call … now?**, that names the voice and the time limit. Only **Call now** dials; the dialog focuses **Cancel** first so an accidental Enter never places a call.',
            'During the call you can take over or hang up at any time. Calls are placed through the phone provider account you connect in the setup.',
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
          text: '**"Connect every step from Start to End…"** — a step is not connected, a path does not reach **End**, or a step other than Condition has two outgoing arrows. Drag from a card\'s right handle to the next card\'s left handle; select an arrow and press Delete to remove it.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**"Incompatible steps…"** — a step receives the wrong kind of value, for example **Speak** after a **Source clip**. Put **Transcribe** in between, or use **Convert** for audio.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**"Choose a saved voice…"** or **"Choose source and target languages."** — open the step and fill in the missing field. **"Set up a transcription engine in Settings first."** — install an ASR model in **Settings → Models → ASR**.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Cancelling keeps every finished step. Press **Retry** to continue from where the run stopped, or the circular arrow to start fresh.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Workflow drafts, imported clips and run results live in this app\'s local storage. Deleting a workflow also deletes its clips and results.',
        },
      ],
    },
  ],
};

export default chapter;
