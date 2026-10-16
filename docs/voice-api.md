# Voice API: speak with a saved voice

Two small endpoints for scripts and other apps on the same computer. Name a
saved voice, send text, and get audio back with tuned settings. No engine,
language, seed or quality flags to remember.

| Endpoint | What it does |
|---|---|
| `GET /v1/voices` | Saved voices with their category, language and description |
| `POST /v1/speak` | Text in a saved voice, returned as audio |

Both live on the backend (`http://127.0.0.1:3900` by default) next to the
OpenAI-compatible [`/v1/audio/speech`](integration-directory.md). `/v1/speak`
is a thin layer over it, so normalisation, audio tags, `[pause 500ms]`,
watermarking and Sound more human behave the same.

## List voices

```bash
curl "http://127.0.0.1:3900/v1/voices?category=Family&language=hi"
```

```json
{
  "voices": [
    {"id": "2e6d51c1", "name": "HI · Family · Maa (Loving Mother)", "category": "Family",
     "language": "hi", "kind": "clone", "description": "A loving caring Indian mother …"}
  ],
  "categories": ["Family"],
  "count": 1
}
```

- `category` comes from the voice name: the middle part of `Prefix · Group · Name`,
  or the first part of `Group · Name`. The app's Saved voices filter uses the same rule.
- Filters are optional. `category` ignores case; `language` is an ISO code (`hi`, `en`).

## Speak

```bash
curl -X POST http://127.0.0.1:3900/v1/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "नमस्ते दोस्तों, आज की कहानी शुरू करते हैं।", "voice": "HI · Narrator · Kahani (Male Storyteller)"}' \
  -o take.wav
```

Only `text` and `voice` are required. `voice` is a saved voice's id or its exact
name (case-insensitive).

| Field | Default | Notes |
|---|---|---|
| `text` | required | Up to 4096 characters. Hindi in Devanagari reads best. |
| `voice` | required | Id or name from `GET /v1/voices`. |
| `language` | the voice's language | ISO code. Required only if the voice was saved with Auto. |
| `model` | `voxcpm2` | Any TTS engine id. |
| `seed` | the voice's saved seed | Change it to get a different take of the same line. |
| `humanize` | `true` | Breaths, room tone and natural pacing. |
| `humanize_strength` | `0.65` | 0 to 1. |
| `num_step` | `32` | Quality steps, 1 to 64. Higher is cleaner and slower. |
| `speed` | `1.0` | 0.25 to 4. |
| `response_format` | `wav` | `wav`, `mp3`, `opus`, `aac`, `flac` or `pcm`. |

### Python

```python
import requests

VS = "http://127.0.0.1:3900"
voice = requests.get(f"{VS}/v1/voices", params={"category": "Funny"}).json()["voices"][0]
audio = requests.post(f"{VS}/v1/speak", json={"text": "अरे भाई, ये तो कमाल हो गया!", "voice": voice["id"]},
                      timeout=1800)
audio.raise_for_status()
open("funny.wav", "wb").write(audio.content)
```

### JavaScript (Node 18+)

```js
const VS = "http://127.0.0.1:3900";
const res = await fetch(`${VS}/v1/speak`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text: "नमस्ते, आपका स्वागत है।", voice: "HI · Female · Priya (Natural)" }),
});
if (!res.ok) throw new Error((await res.json()).error.message);
await import("node:fs/promises").then((fs) => res.arrayBuffer().then((b) => fs.writeFile("hello.wav", Buffer.from(b))));
```

## Errors

Errors use OpenAI's shape, `{"error": {"message", "type", "param", "code"}}`.

| Status | `code` | Meaning and fix |
|---|---|---|
| 404 | `voice_not_found` | No saved voice has that id or name. Pick one from `GET /v1/voices`. |
| 409 | `ambiguous_voice` | Several voices share the name. Use one of the listed ids, or rename. |
| 400 | `language_required` | The voice was saved with Auto. Pass `language`. |
| 429 | | The GPU is busy. Wait for `Retry-After` seconds and send again. |

Send one request at a time and allow long timeouts (30 minutes): a request
waits for the GPU, and the first one after a restart also loads the model.

## Access from other devices

Like the rest of the API, these routes need no key on the same computer and
are gated for other devices by the share PIN or `OMNIVOICE_API_KEY`. See
[Authenticating the local API](api-auth.md).
