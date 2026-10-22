import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'voices',
  order: 50,
  title: 'Saved voices and the Gallery',
  summary:
    'Manage the voices you keep (rename, replace the clip, preview, export, delete) and pick ready-made voices from the Gallery.',
  sections: [
    {
      id: 'what',
      title: 'What saved voices are',
      blocks: [
        {
          kind: 'p',
          text: 'A **saved voice** (voice profile) is a voice you can use again in one click. There are two kinds: a **cloned voice** (fingerprint icon) keeps a reference clip and its transcript; a **designed voice** (wand icon) keeps a recipe and a seed. The Gallery adds ready-made voices to the same list.',
        },
        {
          kind: 'diagram',
          id: 'voices-storage',
          caption:
            'Every source creates the same kind of profile on this computer. Dashed: exporting packs a voice into a `.ovsvoice` file you can share.',
          text: {
            data: 'omnivoice_data',
            clone: 'Voice cloning\n(Save)',
            design: 'Design\n(Save as voice profile)',
            gallery: 'Gallery\n(Use voice)',
            import: 'Import\n.ovsvoice / clip',
            api: 'Backend\n/profiles',
            db: 'Voice profiles\n(SQLite database)',
            files: 'voices/\nreference clips',
            workspaces: 'Clone · Design · Batch\nTools · Workflows',
            long: 'Dubbing · Stories\nAudiobook · Projects',
            export: 'Export persona\n(.ovsvoice file)',
            row: 'name, transcript,\nrecipe, seed',
            clip: 'audio',
            pick: 'pick a voice',
            bundle: 'export',
          },
        },
        {
          kind: 'p',
          text: 'Profiles live in your data folder: the details in the SQLite database, the clips in `voices/`. They never leave this computer unless you export them or send a job to your remote GPU.',
        },
      ],
    },
    {
      id: 'saved',
      title: 'Manage your saved voices',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Open Saved voices',
              text: 'In the menu open **Voice → Saved**. Search by name **(1)**, or filter **(2)** to all, cloned or designed voices. Hover a voice **(3)** to show its buttons: **Preview voice**, **Edit voice profile** **(4)** and **Delete voice**. Click the name itself to use the voice in Voice cloning.',
              shot: 'voices-saved',
              check: 'Every voice you saved from Clone, Design or the Gallery is listed, newest first.',
            },
            {
              title: 'Edit a voice',
              text: 'Press **Edit voice profile**. Change the **Profile name** **(2)**, the **Transcript**, **Style** or **Language**, and press **Save** at the bottom. **Replace reference** **(1)** swaps the clip of a cloned voice.',
              shot: 'voices-edit',
              check: 'The pane closes and the list shows the new name.',
            },
            {
              title: 'Preview, export or check where it is used',
              text: 'Further down the pane: **Export persona** **(1)** saves the voice as a `.ovsvoice` file; **Include voice clip** **(2)** decides whether the raw reference goes in. **Try this voice** **(3)** renders a **Test phrase** with **Generate preview** **(4)**; **Lock voice identity** then keeps that take as the voice’s fixed reference. **Where this voice has been used** counts takes, projects and dubbed segments.',
              shot: 'voices-edit-more',
              check: 'After **Generate preview**, a player appears with the test phrase in this voice.',
            },
          ],
        },
        {
          kind: 'table',
          head: ['Action', 'What happens'],
          rows: [
            ['**Replace reference**', 'A new clip replaces the old one. A locked take and own-voice verification are cleared, because the new clip may be another speaker.'],
            ['**Export persona**', 'A `.ovsvoice` file (ZIP) with the voice’s settings and either the raw clip or a watermarked preview.'],
            ['**Voice ownership**', 'Record that this is your own voice, or that you have the speaker’s permission.'],
            ['**Delete**', 'Removes the voice after a confirmation. Takes already generated stay in Recent takes.'],
          ],
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Include voice clip** is on by default. Turn it off before you share a persona with someone else: they then get only a watermarked preview, not the recording itself.',
        },
      ],
    },
    {
      id: 'gallery',
      title: 'Use a ready-made voice from the Gallery',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Browse the archetypes',
              text: 'Open **Voice → Gallery**. The tabs **(1)** are **Archetypes**, **Community** and **My Imports**. Pick a category **(2)** or use the filters. Press play on a card to hear it, the star to keep it in **Favorites**, and **Use voice** **(3)** to save it as a designed voice and open it in Design. The **…** menu offers **Use in Stories** and **Set as Audiobook default**.',
              shot: 'voices-gallery',
              check: 'After **Use voice**, Design opens with the archetype’s details, and the voice is in **Saved voices**.',
            },
            {
              title: 'Browse community voices',
              text: 'The **Community** tab lists presets and recorded voices shared by other users **(1)**. **Open in Designer** **(2)** loads a preset’s recipe into Design; **Use voice** saves it. **Submit a preset** and **Submit a voice** open a prefilled GitHub issue in your browser.',
              shot: 'voices-community',
              check: 'The list loads within a few seconds when you are online.',
            },
            {
              title: 'Import your own clips and personas',
              text: 'In **My Imports**, paste a video or audio link you have the rights to, or type to search **(1)**; or press **Upload file** **(2)**. Trim the part you need and use it as a cloned voice. **Import a .ovsvoice persona bundle** **(3)** adds a voice someone exported for you.',
              shot: 'voices-imports',
              check: 'The imported clip appears under **My Imports** with **Use voice** and **Trim**.',
            },
          ],
        },
      ],
    },
    {
      id: 'network',
      title: 'What the Gallery downloads',
      blocks: [
        {
          kind: 'table',
          head: ['Part', 'Downloads', 'When'],
          rows: [
            ['Archetypes', 'Nothing. Archetypes are built in; a preview is rendered on this computer (or your remote GPU) the first time you play it, then cached.', 'Only when you press play'],
            ['Voice previews (Settings)', 'Pre-rendered previews from the signed `omnivoice-gallery` release on GitHub', 'Only after you turn **Voice previews** on'],
            ['Community', 'The community list from jsDelivr (`cdn.jsdelivr.net`); a recorded voice’s clip from GitHub when you use it (checked against its SHA-256 hash)', 'When you open the **Community** tab or use a community voice'],
            ['My Imports', 'The clip at the link you paste', 'Only when you paste a link or search'],
          ],
        },
        {
          kind: 'shot',
          id: 'voices-previews',
          caption:
            '**Settings → Models → Voice previews** **(1)**: off by default. Off, every preview is rendered locally; on, the featured set is downloaded once.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Everything in this chapter works offline except the Community tab, downloaded previews and link imports. A voice you used from the Gallery is a normal saved voice and keeps working offline.',
        },
      ],
    },
    {
      id: 'verify',
      title: 'Check the result',
      blocks: [
        {
          kind: 'verify',
          shot: 'voices-result',
          items: [
            'The voice you saved, edited or took from the Gallery is in **Voice → Saved**.',
            '**Preview voice** plays it, and other workspaces list it in their voice picker.',
            'An exported `.ovsvoice` file imports again with **Import a .ovsvoice persona bundle**.',
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
          text: 'Give voices names that say what they are for (`Narrator – calm`, `Villain`), and use the filters to tell cloned and designed voices apart.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'A designed or Gallery voice has no clip until its first preview. If the preview button is greyed out, the text-to-speech engine is not ready yet; see the notice at the top of Voice cloning.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'If **Community** says that no community voices are loaded, check your internet connection and reopen the tab. Archetypes and your saved voices still work.',
        },
      ],
    },
  ],
};

export default chapter;
