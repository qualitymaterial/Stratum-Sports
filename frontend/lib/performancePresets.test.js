import test from "node:test";
import assert from "node:assert/strict";

import { applyPresetFilters, PRESET_DEFINITIONS } from "./performancePresets.js";

test("preset definitions include expected keys", () => {
  assert.equal(PRESET_DEFINITIONS.HIGH_CONFIDENCE.minStrength, 75);
  assert.equal(PRESET_DEFINITIONS.STEAM_ONLY.windowMinutesMax, 5);
});

test("applyPresetFilters applies preset values", () => {
  const initial = {
    selectedPreset: "CUSTOM",
    signalType: "ALL",
    market: "ALL",
    minStrength: 40,
    minSamples: 1,
    minBooksAffected: 1,
    maxDispersion: null,
    windowMinutesMax: null,
  };

  const applied = applyPresetFilters(initial, "LOW_NOISE");
  assert.equal(applied.selectedPreset, "LOW_NOISE");
  assert.equal(applied.minStrength, 65);
  assert.equal(applied.minBooksAffected, 3);
  assert.equal(applied.maxDispersion, 0.5);
});

test("applyPresetFilters keeps values in custom mode", () => {
  const initial = {
    selectedPreset: "HIGH_CONFIDENCE",
    signalType: "MOVE",
    market: "spreads",
    minStrength: 70,
    minSamples: 12,
    minBooksAffected: 2,
    maxDispersion: 0.4,
    windowMinutesMax: 8,
  };

  const applied = applyPresetFilters(initial, "CUSTOM");
  assert.equal(applied.selectedPreset, "CUSTOM");
  assert.equal(applied.minStrength, 70);
  assert.equal(applied.windowMinutesMax, 8);
});
