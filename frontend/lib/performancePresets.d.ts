export type PresetFilters = {
  selectedPreset: string;
  signalType: string;
  market: string;
  minStrength: number;
  minSamples: number;
  minBooksAffected: number;
  maxDispersion: number | null;
  windowMinutesMax: number | null;
};

export const PRESET_DEFINITIONS: Record<string, Partial<PresetFilters>>;

export function applyPresetFilters(current: PresetFilters, presetKey: string): PresetFilters;
