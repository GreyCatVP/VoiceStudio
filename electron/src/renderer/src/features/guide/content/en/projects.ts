import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'projects',
  order: 120,
  title: 'Projects',
  summary:
    'One library for everything you made: dubbing projects, stories, audiobooks, voices, transcripts, generated audio and exports. Save a dub as a project, reopen it later, or clean up in bulk.',
  sections: [
    {
      id: 'what',
      title: 'What the Projects workspace is',
      blocks: [
        {
          kind: 'p',
          text: 'Open **Projects** from the workspace menu (or the **Projects** link in the Dubbing title bar). It lists your work from every workspace, newest first, so you can find, reopen, reuse or delete it in one place.',
        },
        {
          kind: 'table',
          head: ['Filter', 'What it lists', 'What you can do'],
          rows: [
            ['**Dubbing Projects**', 'Dubs you saved as a project', 'Open in Dubbing, rename, delete'],
            ['**Stories** / **Audiobooks**', 'Saved story and audiobook projects, and finished renders', 'Open a project in its workspace, rename; play a render and see **How it was made**'],
            ['**Voice Profiles**', 'Cloned and designed voices', '**Use voice** opens Voice cloning with it'],
            ['**Transcripts**', 'Results from the Transcribe workspace', '**Script** sends the text to Voice cloning'],
            ['**History**', 'Every generated take', 'Play it, **Reuse script**'],
            ['**Exports**', 'Files you exported', '**Show in folder**'],
          ],
        },
      ],
    },
    {
      id: 'storage',
      title: 'What a project contains and where it is stored',
      blocks: [
        {
          kind: 'diagram',
          id: 'projects-storage',
          caption:
            'The library reads from two places. Stories, audiobooks and transcripts are kept by the app itself; dubbing projects, voices, history, exports and renders are kept by the backend in your data folder (`omnivoice_data`).',
          text: {
            app: 'This app',
            backend: 'Backend data',
            page: 'Projects library',
            longform: 'Story + audiobook\nprojects',
            transcripts: 'Transcripts',
            workspaces: 'Stories / Audiobook workspace\n(a project reopens as the draft)',
            dubs: 'Dubbing projects\n(SQLite)',
            voices: 'Voice profiles',
            history: 'Generation\nhistory',
            exports: 'Exports +\nrenders',
            open: 'open',
          },
        },
        {
          kind: 'list',
          items: [
            '**A dubbing project** is a named snapshot of a dub: the source video, its length, every segment with its translations and voices, the target languages and the export options. It points to the dubbing job\'s files (video, extracted audio, separated vocals) that stay in the data folder.',
            '**A story or audiobook project** is the whole draft of that workspace: the script, its lines and the voice of each line.',
            'Voices, takes and renders are not "projects", but they are listed here so you can manage everything in one place.',
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Story, audiobook and transcript entries live in this app\'s own storage, not in `omnivoice_data`. Moving the data folder or using the backend from another computer does not bring them along.',
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Save, find and reopen a project',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Save the current dub as a project',
              text: 'While a dub is open in Dubbing, open **Projects**. Under **Save Dubbing Project**, type a name (**1**) and press **Save** (**2**). Later saves update the same project; **Save as New Dubbing Project** makes a copy.',
              shot: 'projects-save-dub',
              check: '**Project saved** appears under the field.',
            },
            {
              title: 'Save a story or audiobook',
              text: 'In **Stories** or **Audiobook**, open the **Projects** section, enter a **Project name** and press **Save**. **Save a copy** keeps the original.',
              check: 'The project appears under **Stories** or **Audiobooks** in the library.',
            },
            {
              title: 'Find it in the library',
              text: 'Pick a filter on the left (**1**) or type in the search box (**2**). The save form (**3**) stays at the top while a dub is open. Each row (**4**) shows the type, details and when it was last changed.',
              shot: 'projects-library',
              check: 'The counts next to each filter match what you made.',
            },
            {
              title: 'Reopen it',
              text: 'Click the project name (**1**). The row asks whether to replace your current draft; press **Confirm** (**2**). The app switches to Dubbing (or Stories, or Audiobook) with the project loaded.',
              shot: 'projects-open',
              check: 'The workspace shows the project\'s segments or lines as you left them.',
            },
          ],
        },
        {
          kind: 'verify',
          items: [
            'The project is listed under its filter with the name you gave it.',
            'Opening it restores the dub or the story exactly as saved.',
            'A finished story or audiobook render shows **How it was made**: voices, speed, engine, language, format, size and settings.',
          ],
          shot: 'projects-render',
        },
      ],
    },
    {
      id: 'manage',
      title: 'Rename and delete',
      blocks: [
        {
          kind: 'list',
          items: [
            'The pencil button renames a project in place; press **Save name** or Enter.',
            'The bin button deletes one item. To delete several, tick their boxes (or **Select visible**) and press **Delete selected**.',
          ],
        },
        {
          kind: 'shot',
          id: 'projects-delete',
          caption: '**1** Every delete asks first and lists what will be removed.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: 'Deleting cannot be undone. Projects and transcripts are removed; deleting voices or takes also removes their stored audio. Exported files and finished render audio are kept.',
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
          text: '**Save your current work before opening another project.** Opening replaces the current Dubbing, Stories or Audiobook draft.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '**Buttons are disabled.** While a dub, story or audiobook is generating, the library is locked so a project cannot change under a running job. Wait for it to finish or cancel it.',
        },
        {
          kind: 'note',
          tone: 'info',
          text: '**There is no "Save Dubbing Project" box.** It only appears while a dub is open in the Dubbing workspace. Start or open a dub first.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'Use the grid and list buttons next to the search box to switch between cards and a compact list.',
        },
      ],
    },
  ],
};

export default chapter;
