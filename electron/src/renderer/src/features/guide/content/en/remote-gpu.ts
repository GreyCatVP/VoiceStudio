import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'remote-gpu',
  order: 160,
  title: 'Remote GPU: Ray cluster or Modal',
  summary:
    'Run the heavy engines on a GPU somewhere else: your own Ray cluster, or serverless GPUs in your own Modal account. Each run frees the GPU when it ends.',
  sections: [
    {
      id: 'what',
      title: 'What it is and when to use it',
      blocks: [
        {
          kind: 'p',
          text: 'With **Remote GPU** on, the engines you tick run as jobs on a GPU outside this computer. Everything else (your voices, projects, history, the watermark, live dictation) stays here. It is **off by default**; engines you do not tick keep running locally.',
        },
        {
          kind: 'list',
          items: [
            '**No GPU, or a weak one** — voice cloning, dubbing and transcription run about ten times faster on a GPU than on a CPU.',
            '**Nothing stays loaded** — every run is one job. When the job ends, its process exits and the GPU memory goes back to the cluster or Modal stops billing.',
            '**Ray cluster** — your own GPU servers running Ray. You pay nothing per run; you run the cluster.',
            '**Modal** — serverless GPUs in your own Modal account. Nothing to run yourself; Modal bills each second a container runs.',
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Remote GPU is opt-in. The text, reference audio and other inputs of the engines you tick are sent to your cluster or your Modal account; nothing is sent until you turn it on.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How it works',
      blocks: [
        {
          kind: 'diagram',
          id: 'remote-gpu-lifecycle',
          caption:
            'One job per step (one sentence batch, one transcription piece, one translation). The dashed arrow only happens when you cancel or a deadline passes.',
          text: {
            package: '1. Build the\njob package',
            upload: '2. Upload\nand submit',
            install: '3. Install or\nreuse the engine',
            run: '4. Run the engine,\nstream progress',
            result: '5. Results back\n(checksummed)',
            free: '6. Job ends,\nGPU freed',
            cache: 'Engine cache\n(node disk or\nModal image)',
            progress: 'Progress in\nthe app',
            cancel: 'Cancel or\ndeadline',
            reuse: 'reuse',
            frames: 'progress frames',
            stop: 'stops the job',
          },
        },
        {
          kind: 'list',
          ordered: true,
          items: [
            'The backend packs the worker, the engine code, the inputs (text, reference audio) and the task into one zip. It is content-addressed, so an identical package is uploaded only once.',
            '**Ray:** the package is uploaded through the dashboard Jobs API and becomes the job\'s `working_dir`; the job asks for your **GPU share per job** and **CPUs per job**. **Modal:** a Sandbox starts on the GPU type you chose, from an image built once per engine install recipe, with a Volume that keeps model weights.',
            'The worker installs the engine environment on first use (a `uv` virtual environment pinned like the local installer) or reuses the cached one. The first run can take many minutes.',
            'The worker starts the engine and streams progress frames through the job log; the app shows them as live progress.',
            'The result (audio, text) comes back in checksummed frames, at most 50 MB per job. The backend then deletes the finished job.',
            'The job exits, which returns the GPU memory. On Modal the sandbox is terminated, so billing stops.',
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Cancelling a generation, or a deadline passing, stops the job — even one still waiting in the cluster queue. A job that waited past its deadline refuses to start the engine, so it does no GPU work.',
        },
        {
          kind: 'diagram',
          id: 'remote-gpu-data',
          caption: 'What a remote job carries off this computer. Your secrets never leave it.',
          text: {
            computer: 'This computer',
            remote: 'Your Ray cluster or Modal account',
            internet: 'Internet',
            inputs: 'Text, reference audio,\nsource recording',
            models: 'Installed pyannote\nmodel files',
            secrets: 'Hugging Face token\nand other secrets',
            backend: 'Backend\n(builds each job)',
            job: 'Remote job\n(Ray job or Modal sandbox)',
            hub: 'Hugging Face Hub',
            gated: 'diarization\nonly',
            local: 'stay here',
            exchange: 'inputs out,\nresults back',
            weights: 'public weights',
          },
        },
        {
          kind: 'table',
          head: ['Data', 'Leaves this computer?'],
          rows: [
            ['Text, reference audio and generated audio of ticked engines', 'Yes, to your cluster or Modal account'],
            ['Dubbing source recording, its transcript and translations', 'Yes, for the dubbing steps you route remotely'],
            ['Installed pyannote model files (about 32 MB)', 'Yes, with each diarization job — the cluster never downloads the gated model'],
            ['Hugging Face token, Ray token, Modal token, other secrets', 'Never sent to the job or to engine code. The Modal token goes only to the local driver process that talks to Modal'],
            ['Voices, projects, history, settings', 'No'],
          ],
        },
        {
          kind: 'table',
          head: ['', 'Ray cluster', 'Modal'],
          rows: [
            ['What it is', 'Your own servers running Ray (tested with 2.59)', 'Serverless GPUs in your Modal account'],
            ['Cost', 'Your hardware; nothing per run', 'Billed per second of container time'],
            ['One run is', 'One Ray job, submitted through the dashboard Jobs API', 'One Modal Sandbox, terminated when the run ends'],
            ['GPU choice', '**GPU share per job** (a fraction; 0 = CPU)', '**GPU type** (T4 … B200, or CPU only)'],
            ['Engine install', 'On the node, in a cache folder; first run per node', 'In an image built per engine; first run per engine'],
            ['Model weights', 'Hugging Face cache on the node', 'Modal Volume (default `voicestudio-cache`)'],
            ['Credentials', 'Ray token or Cloudflare Access service token', 'Modal token ID and secret'],
            ['Job list in the app', 'Yes, **Recent VoiceStudio jobs**', 'No — use the Modal dashboard'],
          ],
        },
      ],
    },
    {
      id: 'ray',
      title: 'Set up a Ray cluster',
      blocks: [
        {
          kind: 'p',
          text: 'You need a Ray head whose dashboard is reachable over HTTPS (plain HTTP only for `localhost`), with authentication on, and nodes that can reach PyPI, `download.pytorch.org`, GitHub and Hugging Face. This computer does not need Ray installed.',
        },
        {
          kind: 'steps',
          items: [
            {
              title: 'Open Remote GPU and enter the connection',
              text: 'Open **Settings → Remote GPU**. Under **Provider** pick **Ray cluster** (1) and turn on **Use Ray cluster** (2). Enter the **Dashboard URL** (3), for example `https://ray.example.com`. If the cluster uses Ray token authentication, turn on **Ray token authentication** (4): the **Ray auth token** field (5) appears; paste the token there. If the dashboard is behind Cloudflare Access, turn on **Cloudflare Access** (6) instead, and fill in the **Cloudflare Access client ID** and **Cloudflare Access client secret** it reveals. Press **Save**.',
              shot: 'remote-gpu-connection',
              check: '**Ray settings saved.** appears next to **Save**. A stored secret shows as dots; leave the field blank to keep it. When credentials are stored, their switch is already on. Turning a switch off removes its stored credentials when you save; the row warns **Will be removed when you save.** first.',
            },
            {
              title: 'Test the connection',
              text: 'Press **Test connection** (1). It runs a small probe job on the cluster, so it can take up to 3 minutes. Save first: the button is off while you have unsaved changes.',
              shot: 'remote-gpu-test',
              check: '**Connected to the Ray cluster.** (2) and the details (4): Ray version, cluster Python, and each GPU with its free memory (for example `NVIDIA H200 NVL: 66.9 GB free of 140.4 GB`). If the cluster has no authentication, a red warning (3) appears — see Troubleshooting. A failed test shows its reason in the same place, under the button.',
            },
            {
              title: 'Tick the engines to run on Ray',
              text: 'Under **Engines that run on Ray**, tick the voice engines (1) and the dubbing engines (2): speech recognition, translation, speaker diarization and source separation. Only ticked engines run on Ray. Each engine shows **GPU** or **CPU**.',
              shot: 'remote-gpu-engines',
              check: 'Your ticks stay after **Save**. The first run of each engine installs it on the cluster, which can take many minutes.',
            },
            {
              title: 'Set the resources and watch the jobs',
              text: '**GPU share per job** (1) is the fraction of a GPU each job reserves (default 0.1; 0 runs GPU engines on CPU). Ray treats it as bookkeeping, not a memory limit. **CPUs per job** (2) is the CPU cores each job reserves. Save, then generate something with a ticked engine: the job shows in **Recent VoiceStudio jobs** (3).',
              shot: 'remote-gpu-jobs',
              check: 'The job shows **PENDING** while it waits for the cluster, then **RUNNING**, with its engine and operation; it disappears once it finishes. **Stop** ends a waiting or running job.',
            },
          ],
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'For speech recognition on Ray, open the speech recognition settings, select **Faster-Whisper (crash-isolated subprocess)** and a Hugging Face model, not a local folder. The cluster downloads the model; you do not need a local copy.',
        },
      ],
    },
    {
      id: 'modal',
      title: 'Set up Modal',
      blocks: [
        {
          kind: 'p',
          text: 'Create a token in your Modal account, with the Modal command line tool or at modal.com → Settings → API tokens:',
        },
        { kind: 'code', text: 'pip install modal\nmodal token new' },
        {
          kind: 'steps',
          items: [
            {
              title: 'Switch the provider and paste the token',
              text: 'In **Settings → Remote GPU**, pick **Modal** under **Provider** (1). Paste the **Modal token ID** (2), which starts with `ak-`, and the **Modal token secret** (3), which starts with `as-`.',
              shot: 'remote-gpu-modal',
              check: 'The Ray fields are replaced by the Modal token fields, and the jobs list is gone (Modal has none in the app).',
            },
            {
              title: 'Choose the GPU type and names',
              text: 'Pick the **GPU type** (1) each job runs on (default L4; **CPU only** runs GPU engines on Modal\'s CPUs). **Modal app name** (2) groups the sandboxes in your account; **Cache volume (advanced)** (3) keeps model weights between jobs — change it only if you share the account, since a new name starts with an empty cache. Tick the engines, turn on **Use Modal** and press **Save**.',
              shot: 'remote-gpu-modal-resources',
              check: '**Modal settings saved.** appears next to **Save**.',
            },
            {
              title: 'Test the connection',
              text: 'Press **Test connection** (4 in the first picture). It checks the token and starts one short sandbox on your GPU type. The first run builds the container image and can take a few minutes.',
              check: '**Connected to Modal.** and the GPU with its memory.',
            },
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'This computer does not need the Modal SDK. On first use, `uv` installs a pinned `modal` package into its own cache, and a small driver process talks to Modal. Each engine gets its own image (Python 3.12, build tools, ffmpeg and the engine), rebuilt only when its install recipe changes.',
        },
      ],
    },
    {
      id: 'no-gpu',
      title: 'From the system check: no GPU found',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Run the system check',
              text: 'Open **Settings → Compute device** and press **System check**. When this computer has no usable GPU and no remote GPU is set up, the **GPU acceleration** line offers three choices: **Keep using CPU** (1), **Use a Ray cluster** (2) and **Use Modal (cloud GPU)** (3).',
              shot: 'remote-gpu-choice',
              check: 'The three buttons show under the GPU acceleration line. **Keep using CPU** hides them and shows **Using CPU · Change**.',
            },
            {
              title: 'Set up the remote GPU in place',
              text: '**Use a Ray cluster** or **Use Modal (cloud GPU)** opens the **Remote GPU** settings in a dialog (1), with that provider already picked under **Provider** (2) but not saved yet. Fill it in as above, save, then close the dialog.',
              shot: 'remote-gpu-choice-dialog',
              check: 'After you close the dialog the check runs again, and the GPU acceleration line says where GPU work now goes, for example **No local GPU — 6 engines run on the Ray cluster**.',
            },
          ],
        },
      ],
    },
    {
      id: 'verify',
      title: 'Check that it works',
      blocks: [
        {
          kind: 'verify',
          items: [
            '**Test connection** shows **Connected to the Ray cluster.** (or **Connected to Modal.**) and your GPU.',
            'In **Settings → Models → TTS**, a ticked engine shows **network** as its device: it runs on the remote GPU, not on this computer.',
            'While you generate with a ticked engine, its job appears in **Recent VoiceStudio jobs**, and disappears when it finishes.',
            'The **System check** GPU acceleration line says how many engines run remotely.',
          ],
          shot: 'remote-gpu-network',
        },
      ],
    },
    {
      id: 'troubleshooting',
      title: 'Tips and troubleshooting',
      blocks: [
        {
          kind: 'note',
          tone: 'warn',
          text: '**Cluster authentication is disabled** — the cluster accepts jobs from anyone who can reach its dashboard, so anyone could run code on your GPUs and read the audio you send. Turn on Ray token authentication (`RAY_AUTH_MODE=token` on the head) and paste the token in **Ray auth token** after turning on **Ray token authentication**, or put the dashboard behind Cloudflare Access and enter its service token under **Cloudflare Access**.',
        },
        {
          kind: 'table',
          head: ['Message', 'Meaning and fix'],
          rows: [
            ['**The cluster rejected the credentials.** (auth)', 'Wrong or expired Ray token or Cloudflare Access keys. Paste them again and save.'],
            ['**Could not reach the dashboard.** (network)', 'The URL is wrong or the dashboard is not reachable from this computer (firewall, VPN, DNS).'],
            ['**The probe job failed on the cluster.** (job_failed)', 'The job ran but failed; the engine\'s error is shown under the result. Failed jobs stay in the Ray dashboard while **Keep failed jobs** is on.'],
            ['**The probe job did not finish in time.** (timeout)', 'Usually no free CPU on the cluster for the probe. Free some, or lower **CPUs per job**.'],
            ['**No Ray node has … GPU(s)**', 'The placement check: no single node can hold the job\'s GPU share and CPUs. Add a GPU node, lower **GPU share per job** or **CPUs per job**, or set the share to 0 to run on CPU. On an autoscaling cluster that starts GPU nodes on demand, set `OMNIVOICE_RAY_SKIP_PLACEMENT_CHECK=1`.'],
            ['**Modal rejected the token.** (Modal auth)', 'The token ID or secret is wrong or was revoked. Create a new one with `modal token new`.'],
            ['**The probe sandbox failed on Modal.** (Modal job_failed)', 'Often a GPU type your Modal workspace cannot use, or an engine install error. An image build failure is detailed in the Modal dashboard\'s logs for the app.'],
            ['**uv was not found** (Modal)', 'The Modal SDK is installed with `uv`. The desktop app ships it; a source install needs `uv` on `PATH`.'],
          ],
        },
        {
          kind: 'list',
          items: [
            'The first run of an engine installs it on the node (or builds its Modal image). A CUDA PyTorch environment is several GB; later runs reuse it. A node with an ephemeral disk installs again after a restart.',
            'Each job returns at most 50 MB of results. Long texts, chapters and dub segments render many lines per job (one model load); dubbing transcription is sent in pieces of up to 30 minutes.',
            'Engines whose weights need a Hugging Face login are not offered remotely, because your token never leaves this computer.',
            'Live dictation, voice activity detection and the watermark always stay on this computer.',
          ],
        },
      ],
    },
  ],
};

export default chapter;
