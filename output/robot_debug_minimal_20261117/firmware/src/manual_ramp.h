#pragma once
#include <stdint.h>

// Motor-board command values, not calibrated physical speeds. Tune after testing.
constexpr float kManualStraightStart = 0.03f;
constexpr float kManualStraightMax = 0.08f;
constexpr float kManualTurnStart = 0.02f;
constexpr float kManualTurnMax = 0.04f;
constexpr uint32_t kManualStraightRampMs = 2500;
constexpr uint32_t kManualTurnRampMs = 3000;

constexpr float rampValue(float start, float maximum, uint32_t elapsed, uint32_t duration) {
  return start + (maximum-start) * (elapsed >= duration ? 1.0f : float(elapsed)/duration);
}

constexpr float manualSpeed(uint8_t command, uint32_t elapsed) {
  return command >= 8
      ? rampValue(kManualTurnStart, kManualTurnMax, elapsed, kManualTurnRampMs)
      : rampValue(kManualStraightStart, kManualStraightMax, elapsed, kManualStraightRampMs);
}

// Compile-time checks exercise the same speed calculation used by motorTask.
static_assert(manualSpeed(6, 0) == kManualStraightStart, "Straight start");
static_assert(manualSpeed(8, 0) == kManualTurnStart, "Turn start");
static_assert(manualSpeed(6, 1000) > manualSpeed(6, 500), "Straight accelerates");
static_assert(manualSpeed(8, 2000) > manualSpeed(8, 1000), "Turn accelerates");
static_assert(manualSpeed(6, 2500) == kManualStraightMax, "Straight maximum");
static_assert(manualSpeed(8, 3000) == kManualTurnMax, "Turn maximum");
static_assert(manualSpeed(7, 100000) == kManualStraightMax, "Reverse capped");
static_assert(manualSpeed(9, 100000) == kManualTurnMax, "Right capped");
static_assert(kManualTurnMax < kManualStraightMax, "Turning must remain slower");
