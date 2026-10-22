import type { GuideChapter } from '../../guide-types';

const chapter: GuideChapter = {
  id: 'integrations',
  order: 140,
  title: 'Integrations',
  summary:
    'Use VoiceStudio from other programs: an OpenAI-compatible speech API, an MCP server for AI assistants, Docker images, workflow tools and phone calls. Includes a first API call you can run in a minute.',
  sections: [
    {
      id: 'what',
      title: 'What the Integrations catalogue is',
      blocks: [
        {
          kind: 'p',
          text: 'Open **Integrations** in the workspace menu. Every card marked **Works with VoiceStudio** has a page with ready-to-copy setup for this computer. Use it when another program should speak or transcribe with your local voices: a script, an AI assistant, an automation or a phone line.',
        },
        {
          kind: 'table',
          head: ['Integration', 'What it gives you', 'How you set it up'],
          rows: [
            ['**VoiceStudio API**', 'OpenAI-compatible `/v1/audio/speech` and `/v1/audio/transcriptions`', 'Copy the base URL, a `curl` command or the Python (OpenAI SDK) snippet'],
            ['**Model Context Protocol**', 'Speech, transcription, voice cloning and voice design as MCP tools', 'Point any MCP client at the Streamable HTTP URL, or use the stdio shim'],
            ['**Claude Code**, **Cursor**, **Codex CLI**', 'The same MCP tools, preconfigured for that assistant', 'Merge the client configuration into the file the page names'],
            ['**OpenAI Agents**', 'Local speech to text and text to speech for an Agents SDK voice pipeline', 'Run the Python script; your own language model server does the thinking'],
            ['**n8n**', 'A ready-made workflow that generates speech', 'Import the workflow JSON (**Save as…**) into n8n'],
            ['**Docker**, **GitHub Container Registry**', 'VoiceStudio as a self-hosted server with its API and MCP endpoint', 'Run the container or Docker Compose snippet'],
            ['**Twilio**', 'Make and answer phone calls in your own voice', 'An interactive setup panel inside the page'],
          ],
        },
        {
          kind: 'note',
          tone: 'info',
          text: 'Integrations only expose what already runs on this computer. Local requests need no key. The backend listens on `127.0.0.1` only, unless you share it in **Settings → Sharing & Remote Access**; remote requests then need the backend\'s API key over `https://`.',
        },
      ],
    },
    {
      id: 'how',
      title: 'How an outside program reaches your voices',
      blocks: [
        {
          kind: 'diagram',
          id: 'integrations-api-flow',
          caption:
            'Both doors lead to the same engines the app uses. Dashed: only when you pass a saved voice, or route the engine to a remote GPU.',
          text: {
            outside: 'Your programs',
            computer: 'This computer (VoiceStudio backend)',
            client: 'Script or app\n(curl, OpenAI SDK, n8n)',
            agent: 'AI assistant\n(MCP client)',
            openai: 'OpenAI-compatible\nAPI /v1/audio/…',
            mcp: 'MCP endpoint /mcp/\n(tool calls)',
            resolve: 'Pick engine + voice\n(tts-1 = active)',
            engine: 'TTS or ASR\nengine',
            remote: 'Remote GPU\n(optional)',
            mark: 'Watermark +\nencode',
            profiles: 'Saved voices',
            voice: 'voice = name or id',
            audio: 'audio or text back',
          },
        },
        {
          kind: 'table',
          head: ['Request field', 'What VoiceStudio does with it'],
          rows: [
            ['`model`', '`tts-1`, `tts-1-hd` and `gpt-4o-mini-tts` mean "the active TTS engine". An engine id such as `omnivoice` picks that engine.'],
            ['`voice`', '`default` or an OpenAI voice name (`alloy`, `nova`…) uses the engine\'s default voice. A saved voice\'s **name** or **id** speaks in that voice.'],
            ['`input`', 'The text, up to 4096 characters. Numbers and abbreviations are spelled out first, as in the app.'],
            ['`response_format`', '`wav`, `pcm`, `mp3`, `opus`, `aac` or `flac`. Compressed formats need the media tools (ffmpeg).'],
            ['`whisper-1` (transcriptions)', 'Means "the active speech recognition model".'],
          ],
        },
        {
          kind: 'p',
          text: 'Like every take from the app, API audio carries the inaudible AI watermark. API requests are not added to your generation history.',
        },
      ],
    },
    {
      id: 'walkthrough',
      title: 'Make your first API call',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Find the VoiceStudio API',
              text: 'In **Integrations**, type `VoiceStudio API` in the search box (1), or narrow the list with the category filters (2). Click the **VoiceStudio API** card (3).',
              shot: 'integrations-catalog',
              check: 'The card shows **Works with VoiceStudio** and **Speech API · Transcription API**.',
            },
            {
              title: 'Read its setup page',
              text: 'The page opens with the integration\'s name (1) and a **Learn more** link (2) to the full API guide. Below it, **Set up VoiceStudio API** (3) lists **Base URL** (4), **Text to speech (curl)**, **Transcription (curl)** and **Python (OpenAI SDK)**, each with a **Copy** button.',
              shot: 'integrations-api',
              check: '**Base URL** shows the address of your backend followed by `/v1`, for example `http://127.0.0.1:3900/v1` in the desktop app. In the browser version it is the address in your address bar, for example `http://localhost:3921/api/v1`; the snippets below already use it.',
            },
            {
              title: 'Run it in a terminal',
              text: 'Copy **Text to speech (curl)** and run it, then run **Transcription (curl)** on the file it saved. Both work from any terminal on this computer.',
              check: 'The first command saves `speech.wav`; the second prints your sentence back as text.',
            },
          ],
        },
        {
          kind: 'p',
          text: 'The real run made for this guide, against a backend on port 3920 (yours uses the port shown in **Base URL**):',
        },
        {
          kind: 'code',
          text: '$ curl http://127.0.0.1:3920/v1/audio/speech \\\n    -H "Content-Type: application/json" \\\n    -d \'{"model":"tts-1","voice":"default","input":"Hello from VoiceStudio.","response_format":"wav"}\' \\\n    --output speech.wav -w "HTTP %{http_code}  %{size_download} bytes\\n"\nHTTP 200  65828 bytes\n\n$ file speech.wav\nspeech.wav: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 24000 Hz\n\n$ curl http://127.0.0.1:3920/v1/audio/transcriptions -F file=@speech.wav -F model=whisper-1\n{"text":"Hello from Voice Studio."}',
        },
      ],
    },
    {
      id: 'more',
      title: 'Use your voices and assistants',
      blocks: [
        {
          kind: 'steps',
          items: [
            {
              title: 'Speak with one of your saved voices',
              text: 'Replace `default` with the name of a saved voice, for example `"voice":"Narrator"`, and `wav` with `mp3` if you prefer. Names match without regard to case; when two voices share a name, use the voice id instead.',
              check: 'The file now plays in that voice.',
            },
            {
              title: 'Give each AI assistant its own voice (MCP)',
              text: 'For MCP clients, open **Settings → Sharing & Remote Access → MCP voice bindings**. Enter the client\'s ID (1), for example `claude-code`, pick a **Voice profile** (2) and press **Add binding** (3). The client sends its ID in the `X-OmniVoice-Client-Id` header.',
              shot: 'integrations-mcp',
              check: 'The binding appears in the list; that assistant\'s speech now uses the chosen voice.',
            },
            {
              title: 'Explore every endpoint',
              text: 'Open **Settings → VoiceStudio API** for the full, live API reference of this backend. **Copy spec URL** (1) copies the OpenAPI document\'s address for code generators; the **OpenAI-Compatible Audio API** group (2) documents the endpoints used above.',
              shot: 'integrations-openapi',
              check: 'The header shows **Engine ready** and the reference lists the endpoints with try-it examples.',
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
            '`curl` prints `HTTP 200` and `speech.wav` plays your sentence.',
            'Transcribing the file returns your sentence as text.',
            'A request with a saved voice name speaks in that voice.',
            '`curl http://127.0.0.1:3900/v1/models` lists `tts-1`, `whisper-1` and your installed engines.',
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
          text: '`403` with `model_licence_required` ("Licence not accepted for k2-fsa/OmniVoice… Review and accept it in Model Catalogue."): the engine\'s model licence has not been accepted yet. Accept it once in **Settings → Models**, then repeat the request.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '`503` with "did not finish loading within its model-load budget": the first request downloads and loads the model. Wait until the model shows as installed, then retry; the response carries `Retry-After`. `429` means the GPU queue is full: back off for the seconds in `Retry-After`.',
        },
        {
          kind: 'note',
          tone: 'warn',
          text: '"Request refused: it came from another website" means a browser page on another address called the API. Add that page\'s origin to `OMNIVOICE_ALLOWED_ORIGINS`, or call the API from a script or server instead of a web page.',
        },
        {
          kind: 'note',
          tone: 'tip',
          text: 'The official OpenAI SDKs work unchanged: set `base_url` to the **Base URL** and any `api_key` value for local use.',
        },
      ],
    },
  ],
};

export default chapter;
