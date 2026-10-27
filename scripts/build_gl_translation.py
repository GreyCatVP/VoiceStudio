#!/usr/bin/env python3
"""Build Galician (gl) translations for VoiceStudio according to Trasno and RAG standards."""
import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import time
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDERER_EN = os.path.join(ROOT, "electron", "src", "renderer", "src", "i18n", "locales", "en.json")
RENDERER_GL = os.path.join(ROOT, "electron", "src", "renderer", "src", "i18n", "locales", "gl.json")
SHARED_EN = os.path.join(ROOT, "electron", "src", "shared", "i18n", "locales", "en.json")
SHARED_GL = os.path.join(ROOT, "electron", "src", "shared", "i18n", "locales", "gl.json")
CACHE_FILE = os.path.join(ROOT, ".gl_translation_cache.json")

VAR_PAT = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
PROTECTED_NAMES = [
    "VoiceStudio", "Hugging Face", "OmniVoice", "Faster-Whisper",
    "NLLB", "Codex", "Claude Code", "OpenCode"
]

# Strict Trasno & RAG lexical rules
REPLACEMENTS = [
    # Trasno software terms
    (r"\barchivos?\b", lambda m: "ficheiros" if m.group(0).endswith("s") else "ficheiro"),
    (r"\bArchivos?\b", lambda m: "Ficheiros" if m.group(0).endswith("s") else "Ficheiro"),
    (r"\bcarpetas?\b", lambda m: "cartafois" if m.group(0).endswith("s") else "cartafol"),
    (r"\bCarpetas?\b", lambda m: "Cartafois" if m.group(0).endswith("s") else "Cartafol"),
    (r"\bsalvar\b", "gardar"),
    (r"\bSalvar\b", "Gardar"),
    (r"\bsalvouse\b", "gardouse"),
    (r"\bSalvouse\b", "Gardouse"),
    (r"\bsalvado\b", "gardado"),
    (r"\bSalvado\b", "Gardado"),
    (r"\bsalvados\b", "gardados"),
    (r"\bSalvados\b", "Gardados"),
    (r"\bpor defecto\b", "predeterminado"),
    (r"\bPor defecto\b", "Predeterminado"),
    (r"\batajos?\b", lambda m: "atallos" if m.group(0).endswith("s") else "atallo"),
    (r"\bAtajos?\b", lambda m: "Atallos" if m.group(0).endswith("s") else "Atallo"),
    (r"\bportapapeles\b", "portapapeis"),
    (r"\bPortapapeles\b", "Portapapeis"),
    (r"\bcopia de seguridad\b", "copia de seguranza"),
    (r"\bCopia de seguridad\b", "Copia de seguranza"),
    (r"\bcopias de seguridad\b", "copias de seguranza"),
    (r"\bCopias de seguridad\b", "Copias de seguranza"),

    # RAG normative forms
    (r"\bgrabación\b", "gravación"),
    (r"\bGrabación\b", "Gravación"),
    (r"\bgrabacións\b", "gravacións"),
    (r"\bGrabacións\b", "Gravacións"),
    (r"\bgrabar\b", "gravar"),
    (r"\bGrabar\b", "Gravar"),
    (r"\bgrabado\b", "gravado"),
    (r"\bGrabado\b", "Gravado"),
    (r"\bgrabados\b", "gravados"),
    (r"\bGrabados\b", "Gravados"),
    (r"\bgrabando\b", "gravando"),
    (r"\bGrabando\b", "Gravando"),
    (r"\bdictado\b", "ditado"),
    (r"\bDictado\b", "Ditado"),
    (r"\bdictar\b", "ditar"),
    (r"\bDictar\b", "Ditar"),
    (r"\bdictados\b", "ditados"),
    (r"\bDictados\b", "Ditados"),
    (r"\blicencia\b", "licenza"),
    (r"\bLicencia\b", "Licenza"),
    (r"\blicencias\b", "licenzas"),
    (r"\bLicencias\b", "Licenzas"),
    (r"\bdisponible\b", "dispoñible"),
    (r"\bDisponible\b", "Dispoñible"),
    (r"\bdisponibles\b", "dispoñibles"),
    (r"\bDisponibles\b", "Dispoñibles"),
    (r"\bdisponibilidad\b", "dispoñibilidade"),
    (r"\bDisponibilidad\b", "Dispoñibilidade"),
    (r"\bpágina\b", "páxina"),
    (r"\bPágina\b", "Páxina"),
    (r"\bpáginas\b", "páxinas"),
    (r"\bPáginas\b", "Páxinas"),
    (r"\bañadir\b", "engadir"),
    (r"\bAñadir\b", "Engadir"),
    (r"\bañadido\b", "engadido"),
    (r"\bAñadido\b", "Engadido"),
    (r"\bañadida\b", "engadida"),
    (r"\bAñadida\b", "Engadida"),
    (r"\bañadidos\b", "engadidos"),
    (r"\bAñadidos\b", "Engadidos"),
    (r"\bañadidas\b", "engadidas"),
    (r"\bAñadidas\b", "Engadidas"),
    (r"\bcalidad\b", "calidade"),
    (r"\bCalidad\b", "Calidade"),
    (r"\bcalidades\b", "calidades"),
    (r"\bvelocidad\b", "velocidade"),
    (r"\bVelocidad\b", "Velocidade"),
    (r"\bdoblaje\b", "dobraxe"),
    (r"\bDoblaje\b", "Dobraxe"),
    (r"\bdoblajes\b", "dobraxes"),
    (r"\bDoblajes\b", "Dobraxes"),
    (r"\bcancelar\b", "cancelar"),
    (r"\bCancelar\b", "Cancelar"),
    (r"\breiniciar\b", "reiniciar"),
    (r"\bReiniciar\b", "Reiniciar"),
    (r"\bactualizar\b", "actualizar"),
    (r"\bActualizar\b", "Actualizar"),
    (r"\beliminar\b", "eliminar"),
    (r"\bEliminar\b", "Eliminar"),
    (r"\bdesactivar\b", "desactivar"),
    (r"\bDesactivar\b", "Desactivar"),
    (r"\bactivar\b", "activar"),
    (r"\bActivar\b", "Activar"),
    (r"\bdispositivo\b", "dispositivo"),
    (r"\bDispositivo\b", "Dispositivo"),
    (r"\bdispositivos\b", "dispositivos"),
    (r"\bDispositivos\b", "Dispositivos"),
]

# Explicit overrides for mandatory test keys and contracts
KEY_OVERRIDES = {
    "common.error": "Erro",
    "bootstrap.retry": "Tentar de novo",
    "firstrun.hf_token_saved": "Gardouse o token de Hugging Face",
    "capture.copied": "Copiado",
    "capture.inserted": "Inserido",
    "capture.pasted": "Pegado",
    "dub.autofit_quality": "Calidade do axuste automático",
    "engines.inMemory": "En memoria",
    "models.role_llm": "LLM",
    "models.role_tts": "TTS",
    "models.role_asr": "ASR",
    "player.pause": "Pausa",
    "player.play": "Reproducir",
    "settings.hf_source_app_label": "VoiceStudio (cifrado, recomendado)",
    "settings.hf_source_cli_label": "hf CLI",
    "settings.hf_source_env_label": "Variable HF_TOKEN",

    # Segment dub plan
    "segment.plan_apply": "Aplicar plan",
    "segment.plan_apply_title": 'Substituír esta liña coa redacción máis curta suxerida: "{{text}}"',
    "segment.plan_impossible": "Non cabe +{{seconds}} s",
    "segment.plan_impossible_title": "Fala prevista ≈{{est}} s fronte a {{avail}} s dispoñibles — arredor de {{seconds}} s máis do que calquera axuste pode absorber, polo que o audio recortarase. Acurta o texto antes de xerar.",
    "segment.plan_tight": "Axuste axustado",
    "segment.plan_tight_title": "Fala prevista ≈{{est}} s fronte a {{avail}} s dispoñibles — Smart Fit pode absorber isto, pero só cunha aceleración audible ou deceleración do vídeo. Acurta o texto para un resultado máis limpo.",

    # Agnostic stage labels (naming NO engine)
    "dub.transcribing": "Transcribindo o audio…",
    "dub_workflow.transcribing_audio": "Transcribindo o audio…",
    "dub_workflow.transcription_failed": "Fallou a transcrición: {{message}}",
    "batch.stage_transcribe": "Transcribindo o audio…",
    "capture.transcribing_label": "Transcribindo o audio…",
    "capture.transcription_failed": "Fallou a transcrición: {{message}}",
    "demo.dictation_transcribing": "Transcribindo a fala…",

    # Dictation model copy (badge alignment)
    "voicePanel.badge_recommended": "Recomendado",
    "voicePanel.model_desc.sherpa-whisper-tiny": "Recomendado. Ditado multilingüe en máis de 90 idiomas con detección automática do idioma.",
    "voicePanel.model_desc.sherpa-parakeet-tdt-v3": "Inglés de alta velocidade (~100 ms de latencia) a través do FastConformer de Nvidia.",

    # OpenAPI UI keys
    "settings.openapi": "Documentación da API",
    "openapi.title": "Referencia da API OpenAPI de VoiceStudio",
    "openapi.loading": "Cargando a documentación da API…",
    "openapi.unreachable_title": "Non se pode conectar co backend",
    "openapi.unreachable_body": "Non se puido acceder á especificación OpenAPI en {{url}}. Asegúrate de que o backend de VoiceStudio estea en execución e téntao de novo.",
    "openapi.retry": "Tentar de novo",
    "openapi.copy_url": "Copiar URL da especificación",
    "openapi.copy_url_aria": "Copiar o URL da especificación OpenAPI",
    "openapi.copied": "Copiado!",
    "openapi.copy_failed": "Non se puido copiar o URL",
    "openapi.open_raw": "Abrir JSON en bruto",
    "openapi.open_raw_aria": "Abrir a especificación OpenAPI en bruto nunha nova xanela",

    # Settings and clone required keys
    "settings.uninstall_confirm_title": "Desinstalar VoiceStudio",
    "settings.uninstall_confirm_body": "Seguro que queres desinstalar VoiceStudio e eliminar os seus compoñentes?",
    "clone.profile_name_required": "O nome do perfil é obrigatorio.",
    "clone.saved_profile": "Perfil gardado correctamente.",
    "clone.save_failed": "Non se puido gardar o perfil de voz: {{message}}",

    "proPage.usd_price": "{{amount, currency(currency: USD; maximumFractionDigits: 0)}}",

    # Shared history plural keys
    "history.dub_meta": "{{segments}} segs · {{duration}} s",
    "history.dub_meta_zero": "{{count}} segmentos · {{duration}} s",
    "history.dub_meta_one": "{{count}} segmento · {{duration}} s",
    "history.dub_meta_two": "{{count}} segmentos · {{duration}} s",
    "history.dub_meta_few": "{{count}} segmentos · {{duration}} s",
    "history.dub_meta_many": "{{count}} segmentos · {{duration}} s",
    "history.dub_meta_other": "{{count}} segmentos · {{duration}} s",
}

RENDERER_KEY_OVERRIDES = {
    "asr_missing.download": "Descargar {{label}}",
    "engines.active": "Motor: {{name}}",
    "models.reco_low_disk": "Non hai espazo suficiente para o paquete completo: descarga ~{{need}} GB e mantén {{headroom}} GB libres despois ({{total}} GB en total), pero só hai {{free}} GB libres. Instala só os modelos requiridos ou libera espazo primeiro.",
    "openapi.unreachable_body": "Non se puido acceder á especificación OpenAPI en {{url}}. Asegúrate de que o backend estea en execución e téntao de novo.",
}

SHARED_KEY_OVERRIDES = {
    "asr_missing.download": "Descargar {{label}} ({{size}} GB)",
    "engines.active": "activo",
    "models.reco_low_disk": "Non hai espazo suficiente para o paquete completo: precisa ~{{need}} GB pero só hai {{free}} GB libres. Instala só os modelos requiridos ou libera espazo primeiro.",
    "openapi.unreachable_body": "Non se puido acceder á especificación OpenAPI do backend local en {{url}}. Asegúrate de que o backend estea en execución e téntao de novo.",
}

def flatten_keys(data, prefix=""):
    flat = {}
    for k, v in data.items():
        curr = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(flatten_keys(v, curr))
        else:
            flat[curr] = v
    return flat

def unflatten_keys(flat):
    root = {}
    for k, v in flat.items():
        parts = k.split(".")
        curr = root
        for part in parts[:-1]:
            if part not in curr or not isinstance(curr[part], dict):
                curr[part] = {}
            curr = curr[part]
        curr[parts[-1]] = v
    return root

def mask_interpolations(text):
    vars_found = VAR_PAT.findall(text)
    masked = text
    for i, v in enumerate(vars_found):
        masked = re.sub(r"\{\{\s*" + re.escape(v) + r"\s*\}\}", f"__VAR_{i}__", masked, count=1)
    return masked, vars_found

def unmask_interpolations(text, vars_found):
    res = text
    for i, v in enumerate(vars_found):
        res = re.sub(rf"__\s*VAR_{i}\s*__", f"{{{{{v}}}}}", res)
    return res

def postprocess_text(text, source_en, key=""):
    if key in KEY_OVERRIDES:
        return KEY_OVERRIDES[key]
    
    res = text
    for pat, repl in REPLACEMENTS:
        res = re.sub(pat, repl, res)
    
    # Question mark alignment
    if "?" not in source_en and "?" in res:
        res = res.replace("?", "")
    
    # Ellipsis alignment
    if source_en.endswith("…") and not res.endswith("…"):
        res = re.sub(r"\.{3}$", "…", res)
        if not res.endswith("…"):
            res = res.rstrip(".") + "…"
    elif not source_en.endswith("…") and not source_en.endswith("...") and res.endswith("…"):
        res = res[:-1]

    # Protected product names
    for p in PROTECTED_NAMES:
        if p.lower() in source_en.lower():
            res = re.sub(re.escape(p), p, res, flags=re.IGNORECASE)
            
    return res

def query_google_translate_batch(texts, target="gl", source="en"):
    delim = "\n===X_DELIM_X===\n"
    combined = delim.join(texts)
    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=" + source + "&tl=" + target + "&dt=t&q=" + urllib.parse.quote(combined)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read().decode("utf-8"))
        full = "".join(seg[0] for seg in data[0] if seg[0])
    parts = full.split("===X_DELIM_X===")
    if len(parts) != len(texts):
        # Fallback to one-by-one if delimiter split drifted
        print(f"Warning: batch size mismatch ({len(parts)} != {len(texts)}), translating individually...")
        results = []
        for t in texts:
            u = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=" + source + "&tl=" + target + "&dt=t&q=" + urllib.parse.quote(t)
            rq = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(rq, timeout=10) as rr:
                d = json.loads(rr.read().decode("utf-8"))
                results.append("".join(s[0] for s in d[0] if s[0]).strip())
            time.sleep(0.05)
        return results
    return [p.strip() for p in parts]

def main():
    print("Loading en.json catalogs...")
    with open(RENDERER_EN, "r", encoding="utf-8") as f:
        ren_en = json.load(f)
    with open(SHARED_EN, "r", encoding="utf-8") as f:
        sh_en = json.load(f)

    flat_ren = flatten_keys(ren_en)
    flat_sh = flatten_keys(sh_en)
    print(f"Renderer keys: {len(flat_ren)}, Shared keys: {len(flat_sh)}")

    # Load cache if exists
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"Loaded {len(cache)} cached translations.")
        except Exception as e:
            print(f"Could not load cache: {e}")

    # Gather all unique (key, en_text) pairs
    all_keys = {}
    for k, v in flat_ren.items():
        if isinstance(v, str):
            all_keys[k] = v
    for k, v in flat_sh.items():
        if isinstance(v, str) and k not in all_keys:
            all_keys[k] = v

    print(f"Total unique keys to resolve: {len(all_keys)}")

    # Identify untranslated keys
    needed = []
    for k, v in all_keys.items():
        if k in KEY_OVERRIDES:
            cache[k] = KEY_OVERRIDES[k]
        elif k not in cache:
            needed.append((k, v))

    print(f"Keys needing translation: {len(needed)}")

    # Process in batches
    BATCH_SIZE = 35
    for i in range(0, len(needed), BATCH_SIZE):
        batch = needed[i:i + BATCH_SIZE]
        batch_keys = [b[0] for b in batch]
        batch_sources = [b[1] for b in batch]

        # Mask placeholders
        masked_texts = []
        vars_list = []
        for src in batch_sources:
            m, vf = mask_interpolations(src)
            masked_texts.append(m)
            vars_list.append(vf)

        try:
            translated_masked = query_google_translate_batch(masked_texts)
        except Exception as exc:
            print(f"Batch {i//BATCH_SIZE + 1} failed: {exc}. Retrying after 2s...")
            time.sleep(2)
            translated_masked = query_google_translate_batch(masked_texts)

        for key, src, raw_trans, vf in zip(batch_keys, batch_sources, translated_masked, vars_list):
            unmasked = unmask_interpolations(raw_trans, vf)
            # Ensure placeholders match
            src_vars = sorted(vf)
            trans_vars = sorted(VAR_PAT.findall(unmasked))
            if src_vars != trans_vars:
                # If translation dropped or broke placeholder, restore from source
                print(f"Placeholder mismatch in {key}: {src_vars} != {trans_vars}. Restoring placeholder structure.")
                unmasked = src  # fallback to English template then re-postprocess or fix
            
            final_text = postprocess_text(unmasked, src, key)
            cache[key] = final_text

        if (i // BATCH_SIZE) % 5 == 0 or i + BATCH_SIZE >= len(needed):
            print(f"Progress: {min(i + BATCH_SIZE, len(needed))}/{len(needed)} strings translated...")
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        
        time.sleep(0.1)

    print("All translations cached. Applying final verification...")
    # Final verification of placeholders and mandatory keys for all cached entries
    for k, src in all_keys.items():
        val = cache.get(k)
        if k in KEY_OVERRIDES:
            cache[k] = KEY_OVERRIDES[k]
            continue
        
        # Check placeholders
        src_vars = sorted(VAR_PAT.findall(src))
        val_vars = sorted(VAR_PAT.findall(val))
        if src_vars != val_vars:
            print(f"Fixing placeholder mismatch for {k}")
            # If plural _zero, count can be omitted
            if k.endswith("_zero") and set(src_vars) - set(val_vars) == {"count"}:
                pass
            else:
                # Force placeholder alignment
                m, vf = mask_interpolations(src)
                raw = query_google_translate_batch([m])[0]
                fixed = unmask_interpolations(raw, vf)
                cache[k] = postprocess_text(fixed, src, k)

        # Ensure protected names
        for p in PROTECTED_NAMES:
            if p in src and p not in cache[k]:
                cache[k] = cache[k].replace(p.lower(), p)

    # Save cache
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Build renderer gl.json
    print("Writing renderer gl.json...")
    ren_gl_flat = {}
    for k, v in flat_ren.items():
        if isinstance(v, str):
            ren_gl_flat[k] = RENDERER_KEY_OVERRIDES.get(k, cache[k])
        else:
            ren_gl_flat[k] = v
    ren_gl_nested = unflatten_keys(ren_gl_flat)
    with open(RENDERER_GL, "w", encoding="utf-8") as f:
        json.dump(ren_gl_nested, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # Build shared gl.json
    print("Writing shared gl.json...")
    sh_gl_flat = {}
    for k, v in flat_sh.items():
        if isinstance(v, str):
            sh_gl_flat[k] = SHARED_KEY_OVERRIDES.get(k, cache.get(k, flat_ren.get(k, v)))
        else:
            sh_gl_flat[k] = v
    sh_gl_nested = unflatten_keys(sh_gl_flat)
    with open(SHARED_GL, "w", encoding="utf-8") as f:
        json.dump(sh_gl_nested, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("Successfully generated renderer and shared gl.json catalogs!")

if __name__ == "__main__":
    main()
