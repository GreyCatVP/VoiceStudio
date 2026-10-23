# VoiceStudio — F5-TTS-THAI Engine

[F5-TTS-THAI](https://huggingface.co/VIZINTZOR/F5-TTS-THAI) (VIZINTZOR) is a
Thai + English fine-tune of [SWivid/F5-TTS](https://github.com/SWivid/F5-TTS),
a flow-matching TTS model that clones a voice from a short reference clip and
the words spoken in it. Output is 24 kHz.

It runs **only on a remote GPU** (a Ray cluster or Modal). There is no local
install: the engine is listed as unavailable until it is routed there.

## When to pick it

- Thai narration or dubbing in a cloned voice.
- Mixed Thai and English text.

The model card warns that long texts and some words are still read wrong.
If a line comes out wrong, try another seed or a slower speed (0.8). A fast
reference speaker reads better at 0.7–0.8.

## Setup

1. Set up a remote GPU: [Ray cluster or Modal](../electron-ray-cluster.md).
2. In **Settings → Remote GPU**, tick **f5-tts-thai** under the engines and
   save. The first job installs the engine on the cluster (the `f5-tts-th`
   package, pinned) and downloads about 1.4 GB of weights from pinned
   Hugging Face revisions: the 1M-step checkpoint and vocabulary of
   `VIZINTZOR/F5-TTS-THAI`, and the `charactr/vocos-mel-24khz` vocoder.
3. **Accept the licence in-app** when asked (see Licence below).
4. Select **F5-TTS-THAI** in **Model Catalogue** (TTS tab → **Use**).

## Reference clip

The model conditions on 2–8 seconds of reference audio and needs its
transcript. VoiceStudio prepares both before the job is sent:

- A clip of 8 s or less is used as it is. Without a transcript it is
  transcribed with your selected speech-to-text model (on the remote GPU when
  that engine is routed there).
- A longer clip is cut to the 8 s window with the most speech, chosen and
  transcribed with your speech-to-text model; a whole-clip transcript is
  ignored. A transcript typed with a `/generate` request for a clip longer than
  8 s is rejected with `[clone_ref_too_long]`.
- With no speech-to-text model installed, use a 2–8 s clip and type its
  transcript.
- With no reference at all, the model card's sample voice is used.

The card recommends Thai reference audio with a Thai transcript; for English
words in the reference, write them as Thai spelling (Good Morning →
กูดมอร์นิ่ง).

## Licence

The model card declares **CC-BY-4.0**, but the model is a fine-tune of
SWivid/F5-TTS, whose weights are **CC-BY-NC-4.0**. Whether the fine-tune can
carry the more permissive licence is unresolved, so VoiceStudio records the
non-commercial base terms and asks for licence acceptance before first use.
Training data per the card: Common Voice Thai, the Porjai Thai voice dataset
and Common Voice English. The inference code (`f5-tts-th`) and F5-TTS code are
MIT; the Vocos vocoder weights are MIT. See
[model-license-data.json](../licensing/model-license-data.json).
