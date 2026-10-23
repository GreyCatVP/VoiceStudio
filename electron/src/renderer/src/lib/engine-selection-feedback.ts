export interface EngineSelectionResult {
  active: string;
  routing_status?: string;
  routing_reason?: string | null;
}

export interface EngineSelectionFeedback {
  tone: "success" | "warning";
  key:
    | "settings.engine_switched"
    | "engines.selectCpuFallback"
    | "engines.selectWithCaveat";
  values: { family: string; engine: string; reason?: string };
}

/** i18n keys naming each engine family in a sentence ("Switched Translation to …"). */
export const ENGINE_FAMILY_LABEL_KEYS: Record<string, string> = {
  tts: "sidebarTools.tts",
  asr: "settings.ray_engines_group_asr",
  translation: "settings.translation",
  dictation: "nav.dictation",
  diarisation: "settings.ray_engines_group_diarization",
};

/** Interpret the backend's host-routing verdict exactly once for every engine picker.
 * `labels` carries the translated family name and the engine's display name; the
 * raw ids are only a fallback. */
export function engineSelectionFeedback(
  result: EngineSelectionResult,
  family: string,
  labels: { family?: string; engine?: string } = {},
): EngineSelectionFeedback {
  const reason = result.routing_reason?.trim();
  const familyLabel = labels.family || family.toUpperCase();
  const engine = labels.engine || result.active;
  if (result.routing_status === "cpu_fallback") {
    return {
      tone: "warning",
      key: "engines.selectCpuFallback",
      values: { family: familyLabel, engine, reason: reason || "" },
    };
  }
  if (result.routing_status === "accelerated" && reason) {
    return {
      tone: "warning",
      key: "engines.selectWithCaveat",
      values: { family: familyLabel, engine, reason },
    };
  }
  return {
    tone: "success",
    key: "settings.engine_switched",
    values: { family: familyLabel, engine },
  };
}
