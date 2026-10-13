#pragma once

#include <math.h>
#include <stdint.h>

// 13 encoder lines x 30:1 gearbox x 4 edges per line (seller's nominal value).
constexpr float kTicksPerWheelRevolution = 1560.0f;

struct Odometry {
  float wheelDiameterMm = 0;
  float wheelTrackMm = 0;
  int32_t leftTicks = 0;
  int32_t rightTicks = 0;
  float xMm = 0;
  float yMm = 0;
  float headingRad = 0;

  bool configured() const { return wheelDiameterMm > 0 && wheelTrackMm > 0; }

  void configure(float diameterMm, float trackMm) {
    wheelDiameterMm = diameterMm;
    wheelTrackMm = trackMm;
    leftTicks = rightTicks = 0;
    xMm = yMm = headingRad = 0;
  }

  void addTicks(int32_t left, int32_t right) {
    leftTicks += left;
    rightTicks += right;
    const float mmPerTick = PI * wheelDiameterMm / kTicksPerWheelRevolution;
    const float leftMm = left * mmPerTick;
    const float rightMm = right * mmPerTick;
    const float turn = (rightMm - leftMm) / wheelTrackMm;
    const float travel = (leftMm + rightMm) * 0.5f;
    xMm += travel * cosf(headingRad + turn * 0.5f);
    yMm += travel * sinf(headingRad + turn * 0.5f);
    headingRad = atan2f(sinf(headingRad + turn), cosf(headingRad + turn));
  }
};
