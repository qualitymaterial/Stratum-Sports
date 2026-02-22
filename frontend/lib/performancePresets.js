export const PRESET_DEFINITIONS = {
  HIGH_CONFIDENCE: {
    minStrength: 75,
    minSamples: 25,
    minBooksAffected: 3,
    maxDispersion: 0.7,
    windowMinutesMax: 20,
  },
  LOW_NOISE: {
    minStrength: 65,
    minSamples: 20,
    minBooksAffected: 3,
    maxDispersion: 0.5,
    windowMinutesMax: 15,
  },
  EARLY_MOVE: {
    signalType: "MOVE",
    minStrength: 60,
    minSamples: 15,
    minBooksAffected: 2,
    maxDispersion: null,
    windowMinutesMax: 10,
  },
  STEAM_ONLY: {
    signalType: "STEAM",
    minStrength: 65,
    minSamples: 10,
    minBooksAffected: 4,
    maxDispersion: null,
    windowMinutesMax: 5,
  },
};

export function applyPresetFilters(current, presetKey) {
  if (presetKey === "CUSTOM") {
    return { ...current, selectedPreset: "CUSTOM" };
  }
  const definition = PRESET_DEFINITIONS[presetKey];
  if (!definition) {
    return { ...current };
  }
  return {
    ...current,
    selectedPreset: presetKey,
    signalType: definition.signalType ?? "ALL",
    market: definition.market ?? "ALL",
    minStrength: definition.minStrength,
    minSamples: definition.minSamples,
    minBooksAffected: definition.minBooksAffected,
    maxDispersion: definition.maxDispersion,
    windowMinutesMax: definition.windowMinutesMax,
  };
}
