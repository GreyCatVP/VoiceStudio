# Hugging Face Token Setup

VoiceStudio uses a single HF token for every model download, license-gate
check, and an explicit **Test now** action. This page covers the places VoiceStudio will
look for a token and the recommended path for v0.3+.

## Sources (cascade)

VoiceStudio resolves the active HF token by walking these sources in priority
order — the first source that has a token *and* survives a live `whoami`
call wins:

0. **OpenBao** — only when you turn it on (see
   [Reading the token from OpenBao](#reading-the-token-from-openbao)). If
   OpenBao is unreachable, sealed or denies access, the next source is used.
1. **App** — encrypted in VoiceStudio's SQLite settings store.
   Set via the in-app **Settings → Credentials** panel.
2. **Env** — `HF_TOKEN` (or the legacy `HUGGING_FACE_HUB_TOKEN`) environment
   variable visible to the VoiceStudio process.
3. **HF CLI** — the local `HF_TOKEN_PATH` file (normally `~/.cache/huggingface/token`) written by
   `huggingface-cli login`. VoiceStudio only reads this file; it never writes it.

Source labels in onboarding and Settings follow the selected UI language;
product names such as HuggingFace CLI remain unchanged.

On opening **Settings → Credentials**, each row shows local set/unset state and
a masked preview (`hf_…3jw`). Tokens remain **Not tested** until you select
**Test now**. That explicit check displays the `whoami` username and a green
check for valid sources, with an **Active** badge on the highest-priority valid source.

## Setting via the app (recommended)

1. Open **Settings → Credentials**.
2. Paste your HF token (get one from
   [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) —
   the "read" scope is enough).
3. Click **Save**. The token is encrypted at rest (Fernet symmetric AEAD,
   key derived per-install from machine-id). It is **not** written to the
   plaintext `huggingface_hub` token file: VoiceStudio hands the resolved
   token to every download and engine itself. (Versions before this change
   did write that file; to remove a copy left there, use **Clear token** with
   **Also clear saved HuggingFace CLI token files**.)
4. Select **Test now** to validate the token with Hugging Face. A successful test turns the indicator green and moves the **Active** badge to "App".

> **Known limitation (honest disclosure):** the encryption key is derived
> per-install from the machine identifier. If you copy `omnivoice_data/`
> across machines, the token row in `settings` will fail to decrypt on the
> new machine — the resolver logs a warning and falls back to the env / CLI
> source. Re-save the token on the new machine to re-encrypt with the
> new install's key.

## Setting via environment variable (power users)

If you launch VoiceStudio from a terminal or CI and prefer env-var management,
export `HF_TOKEN` from your shell's startup file:

```bash
# macOS (zsh — default since 10.15)
echo 'export HF_TOKEN=hf_yourtokenhere' >> ~/.zshrc && source ~/.zshrc

# Linux (bash)
echo 'export HF_TOKEN=hf_yourtokenhere' >> ~/.bashrc && source ~/.bashrc
```

**Windows PowerShell** — write to user-scope environment:

```powershell
[Environment]::SetEnvironmentVariable("HF_TOKEN","hf_yourtokenhere","User")
```

That persists for new shells. Close and reopen PowerShell or your terminal
to see it.

> **Don't use `setx`.** `setx HF_TOKEN "hf_..."` writes the variable but
> *doesn't propagate to the current shell* — a common source of "I set it
> but it's empty" bug reports. Use the in-app Settings → Credentials path or
> the `[Environment]::SetEnvironmentVariable` one-liner above.

## Setting via `huggingface-cli`

If you already use the HuggingFace CLI:

```bash
pip install --upgrade huggingface_hub
huggingface-cli login
# paste token at the prompt
```

That normally writes to `~/.cache/huggingface/token`. VoiceStudio reads the
selected local token file directly — you'll see the
**HF CLI** row in **Settings → Credentials** flip to "set".

## Reading the token from OpenBao

If you keep secrets in [OpenBao](https://openbao.org) (or HashiCorp Vault,
which speaks the same API), VoiceStudio can read the HF token from a KV v2
secret instead of storing it. It is off by default and nothing is sent until
you turn it on.

1. Store the token: `bao kv put secret/voicestudio/hf token=hf_…`.
2. Create a read-only policy for that one path and a **periodic** (or
   renewable) token with it, for example:

   ```hcl
   path "secret/data/voicestudio/hf" { capabilities = ["read"] }
   ```

   ```bash
   bao policy write voicestudio-hf voicestudio-hf.hcl
   bao token create -policy=voicestudio-hf -period=768h -orphan
   ```

   VoiceStudio does not renew the token; a periodic token stays valid while
   it is used within its period, or renew it from your own tooling.
3. Open **Settings → Credentials → OpenBao secret store**, fill in the
   address (default `http://127.0.0.1:8200`), the KV v2 mount (default
   `secret`), the secret path (`voicestudio/hf`), the field (default `token`)
   and the OpenBao token, then select **Test** and turn the source on.

The address must use HTTPS unless OpenBao runs on this computer, and may not
contain credentials, a path or a query. The OpenBao token is stored encrypted
like other secrets and never shown again; **Test** reports only success with a
masked value (`hf_…ABC`), or why it failed: unreachable, sealed, permission
denied, or no such secret/field. The HF token itself is read when needed
(`GET {address}/v1/{mount}/data/{path}` with `X-Vault-Token`), kept in memory
for at most five minutes and never written to disk. Requests go only to the
address you configured.

Unsealing is your server's job — configure OpenBao **auto-unseal** so it is
ready after a reboot. While it is sealed, VoiceStudio reports **sealed** and
falls back to the next token source.

For headless or Docker setups, `OMNIVOICE_OPENBAO_ADDR` and
`OMNIVOICE_OPENBAO_TOKEN` override the saved address and token (the page shows
those fields as set by an environment variable). The source itself is still
turned on in Settings or with `PUT /api/settings/openbao`.

## Accepting model licenses

Some models need both a token *and* a license acceptance click before
downloads work. Visit each page while signed in with the same HF account:

- `pyannote/speaker-diarization-3.1` — required for diarization.
  See [docs/features/diarization.md](../features/diarization.md).
- `pyannote/segmentation-3.0` — required transitively by the above.
- `IndexTeam/IndexTTS-2.5` — required if you use IndexTTS 2.5 for voice cloning.
- `Supertone/supertonic-3` — required if you enable the Supertonic-3 engine.
- `kyutai/pocket-tts` — required if you enable PocketTTS; first accept its
  access conditions on Hugging Face, then use a token from the same account.

After clicking **"Agree and access repository"** on each page, restart any
in-flight VoiceStudio job (the gated check is cached for the lifetime of the
process).

## Troubleshooting

- **HF 401 even though a token is set** — visit the model's HuggingFace page
  and accept the license (see above). The token is fine; the *license* gate
  is separate.
- **Token row stays red after Test now** — the `whoami` call failed. Check the
  token is valid at
  [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
  and has at least the "read" scope.
- **Token didn't survive a reboot** — open **Settings → Credentials** and check
  the App row. If it's empty, the SQLite store may have been wiped — re-save.
  If it's set but the active source is "Env" or "HF CLI", that's the cascade
  working as intended (App is highest priority).

Opening onboarding or Settings only reads local token presence and masked previews; it does not contact Hugging Face. Untested tokens are shown as **Not tested**, and onboarding reports where a token was found without claiming it is valid. **Test now** explicitly contacts Hugging Face. Replacing a saved token does not revoke the previous token on Hugging Face.


Windows automatically shortens the model cache path while keeping the normal CLI token location. If only a previous VoiceStudio short-cache token exists, the app continues using that file. An existing normal CLI token takes priority; explicit token or cache overrides remain authoritative. Credentials are never copied between these locations.

The CLI row reads only the selected local file, without OAuth refresh or environment-token fallback. **Also clear saved HuggingFace CLI token files** removes both active and stored-token files at recognized automatic locations, so an older app token cannot reappear on restart. Explicit overrides limit clearing to their selected location. Clearing only the app token preserves CLI files; neither action revokes tokens on Hugging Face or changes Git credentials. A file permission failure is reported instead of claiming the files were cleared.


If onboarding cannot read token state, it shows an error and **Retry**, keeping token entry hidden until discovery succeeds. **Replace token** writes the encrypted app token through the same endpoint as Settings, so it replaces the highest-priority app credential even when an older one exists. The success message confirms saving only; validation remains a separate explicit action.
