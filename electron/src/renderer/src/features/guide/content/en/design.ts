import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'design',
  order: 40,
  title: 'Design a voice',
  summary:
    'Create a new voice from a description instead of a recording: describe it, fine-tune the details, generate, try another seed, and save the voice you like.',
  sections: [
    {
      id: 'what',
      title: 'What voice design does',
      blocks: [
        {
          kind: 'p',
          text: 'Voice design invents a voice that does not belong to anyone. You describe it (gender, age, pitch, accent, a whisper), and the engine generates a speaker that matches. Use it when you have no recording, need many distinct characters, or want a voice nobody can claim as theirs.',
        },
        {
          kind: 'p',
          text: 'Voice design needs an engine that supports it, such as OmniVoice. Engines that only clone show a notice instead of **Synthesize audio**.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How voice design works',
      blocks: [
        {
          kind: 'diagram',
          id: 'design-flow',
          caption:
            'The description is mapped to details on this computer (a keyword list, no AI model). Only the details, the seed and the script go to the engine. Dashed: saving keeps the recipe, not the audio.',
          text: {
            gpu: 'Remote GPU (Ray)',
            describe: 'Your description\n(free text)',
            presets: 'Starting point\nor demo design',
            mapper: 'Keyword mapper\n(local, instant)',
            details: 'Details\ngender · age · pitch\naccent · seed',
            script: 'Script',
            engine: 'OmniVoice\ndesigns the voice',
            history: 'Watermark +\nRecent takes',
            profile: 'Saved design voice\n(recipe + seed)',
            fills: 'fills',
            instruct: 'tags',
            saved: 'saved',
            save: 'Save as voice profile',
          },
        },
        {
          kind: 'list',
          items: [
            '**Describe your voice** is read for known words (male, elderly, low voice, British…). They set the **Details** below. Words it does not know are listed as **Couldn’t map: …** and ignored. A description in Thai (or another non-Latin script) is first translated to English, shown as **Understood as: …**.',
            '**Details** is the real recipe: one choice per category. Every category on **Auto** lets the model decide.',
            'The **Seed** picks one speaker among all that match the recipe. Same details + same seed = the same voice every time. **New seed** gives a different speaker with the same description.',
            '**Save as voice profile** stores the recipe, the seed and the language. Its sample is rendered the first time you play the voice.',
          ],
        },
        {
          kind: 'table',
          head: ['Category', 'Choices'],
          rows: [
            ['Gender', 'Auto, male, female'],
            ['Age', 'Auto, child, teenager, young adult, middle-aged, elderly'],
            ['Pitch', 'Auto, very low pitch … very high pitch'],
            ['Style', 'Auto, whisper'],
            ['English Accent', 'Auto, american, british, australian, canadian, indian, chinese, korean, japanese, portuguese, russian accent'],
            ['Chinese Dialect', 'Auto and regional Chinese dialects (for Chinese scripts)'],
          ],
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Design a voice step by step',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Open Design and pick a starting point (optional)',
              text: 'In the menu open **Voice → Design**. To start from something ready, click a chip in **Starting points** **(1)**, or open **Hear demo** **(2)**, play a demo and press **Use this design →** **(3)**.',
              shot: 'design-start',
              check: 'The **Details** summary changes from **Auto — the model decides** to the chosen traits.',
            },
            {
              title: 'Describe the voice',
              text: 'Type a description in **Describe your voice** **(1)**, in English, for example `an elderly British man with a low voice`. The line below **(2)** shows what could not be mapped. Open **Details** **(3)** to see what was understood.',
              shot: 'design-describe',
              check: 'The **Details** summary lists the traits, here `male · elderly · low pitch · british accent`.',
            },
            {
              title: 'Fine-tune the details and the seed',
              text: 'Click a choice to change a category, for example **Pitch** **(1)** or **English Accent** **(2)**. The **Seed** **(3)** fixes the speaker; press **New seed** **(4)** to hear a different speaker with the same details.',
              shot: 'design-details',
              check: 'The choice you clicked is highlighted. **Reset to description** brings back what the description says.',
            },
            {
              title: 'Type a script and generate',
              text: 'Type the text in **Script** **(1)** and press **Synthesize audio** **(2)**.',
              shot: 'design-script',
              check: 'The button shows progress; a short line takes about 20 seconds on a remote GPU.',
            },
            {
              title: 'Listen and iterate',
              text: '**Latest take** **(1)** opens with a player. If the voice is not right, change a detail or press **New seed** and generate again. Press **Save as…** **(2)** to download the WAV.',
              shot: 'design-take',
              check: 'Each take is also kept in **Recent takes**, so you can go back to an earlier one.',
            },
            {
              title: 'Save the voice',
              text: 'Type a **Profile name** at the bottom of the left panel and press **Save as voice profile**. The voice appears in **Saved voices** **(1)**, and the header shows its name **(2)**.',
              shot: 'design-saved',
              check: 'The saved voice has a pencil (edit) and a play button. Click its name later to load its recipe and seed again.',
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
          shot: 'design-result',
          items: [
            'The take sounds like your description, and generating again with the same seed gives the same speaker.',
            'The voice is listed under **Saved voices** here and in **Voice → Saved**, with a wand icon (designed voice).',
            'You can pick the saved voice in other workspaces, for example Voice cloning, Stories or Dubbing.',
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
          text: 'The mapper only knows English trait words. A Thai description is translated to English first, with Typhoon Translate when it runs on your remote GPU, otherwise with the translator chosen in **Settings → Models → Translation**. With no translator available, describe the voice in English.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Change one thing at a time. Keep the seed while you adjust details, then try a few seeds once the details are right.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Editing the details of a saved voice turns the draft into a new design: save it under a new name to keep both.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'If the panel shows that the engine **can’t design voices**, the active engine only clones. Open **Settings → Models → TTS** and choose an engine that supports voice design, such as OmniVoice.',
        },
      ],
    },
  ],
};

export default chapter;
