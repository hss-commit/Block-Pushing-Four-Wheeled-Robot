#include <Arduino.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "odometry.h"

// USB-only firmware: DRIVE stores a requested wheel speed but never drives pins.
// Real motor output and encoder sampling need the driver board's actual protocol.
constexpr unsigned long kCommandTimeoutMs = 300;
constexpr int kMaxWheelSpeedMmS = 500;
constexpr int32_t kMaxInjectedTicks = 156000;
constexpr size_t kLineCapacity = 96;

Odometry odometry;
char line[kLineCapacity];
size_t lineLength = 0;
bool lineOverflow = false;
int leftCommandMmS = 0;
int rightCommandMmS = 0;
unsigned long lastDriveMs = 0;

bool parseLong(const char *token, long &value) {
  if (!token || !*token) return false;
  char *end = nullptr;
  errno = 0;
  value = strtol(token, &end, 10);
  return errno == 0 && end != token && *end == '\0';
}

bool parseFloat(const char *token, float &value) {
  if (!token || !*token) return false;
  char *end = nullptr;
  errno = 0;
  value = strtof(token, &end);
  return errno == 0 && end != token && *end == '\0' && isfinite(value);
}

void error(long sequence, const char *reason) {
  Serial.printf("ERR %ld %s\n", sequence, reason);
}

void processLine(char *input) {
  char *save = nullptr;
  const char *verb = strtok_r(input, " \t", &save);
  long sequence = 0;
  if (!verb || !parseLong(strtok_r(nullptr, " \t", &save), sequence) || sequence < 0) {
    error(0, "BAD_SEQUENCE");
    return;
  }
  const char *a = strtok_r(nullptr, " \t", &save);
  const char *b = strtok_r(nullptr, " \t", &save);
  const char *extra = strtok_r(nullptr, " \t", &save);
  if (extra) {
    error(sequence, "BAD_ARGUMENTS");
    return;
  }

  if (!strcmp(verb, "PING") && !a && !b) {
    Serial.printf("PONG %ld SIM_ONLY\n", sequence);
  } else if (!strcmp(verb, "STOP") && !a && !b) {
    leftCommandMmS = rightCommandMmS = 0;
    Serial.printf("OK %ld STOPPED\n", sequence);
  } else if (!strcmp(verb, "DRIVE")) {
    long left, right;
    if (!parseLong(a, left) || !parseLong(b, right) ||
        left < -kMaxWheelSpeedMmS || left > kMaxWheelSpeedMmS ||
        right < -kMaxWheelSpeedMmS || right > kMaxWheelSpeedMmS) {
      error(sequence, "BAD_SPEED");
      return;
    }
    leftCommandMmS = static_cast<int>(left);
    rightCommandMmS = static_cast<int>(right);
    lastDriveMs = millis();
    Serial.printf("OK %ld SIM_ONLY\n", sequence);
  } else if (!strcmp(verb, "GEOM")) {
    float diameter, track;
    if (!parseFloat(a, diameter) || !parseFloat(b, track) ||
        diameter <= 0 || diameter > 500 || track <= 0 || track > 1000) {
      error(sequence, "BAD_GEOMETRY");
      return;
    }
    leftCommandMmS = rightCommandMmS = 0;
    odometry.configure(diameter, track);
    Serial.printf("OK %ld GEOMETRY_RESET\n", sequence);
  } else if (!strcmp(verb, "SIMTICKS")) {
    long left, right;
    if (!parseLong(a, left) || !parseLong(b, right) ||
        left < -kMaxInjectedTicks || left > kMaxInjectedTicks ||
        right < -kMaxInjectedTicks || right > kMaxInjectedTicks) {
      error(sequence, "BAD_TICKS");
      return;
    }
    if (!odometry.configured()) {
      error(sequence, "GEOMETRY_REQUIRED");
      return;
    }
    if ((left > 0 && odometry.leftTicks > INT32_MAX - left) ||
        (left < 0 && odometry.leftTicks < INT32_MIN - left) ||
        (right > 0 && odometry.rightTicks > INT32_MAX - right) ||
        (right < 0 && odometry.rightTicks < INT32_MIN - right)) {
      error(sequence, "TICK_OVERFLOW");
      return;
    }
    odometry.addTicks(static_cast<int32_t>(left), static_cast<int32_t>(right));
    Serial.printf("OK %ld SIMULATED\n", sequence);
  } else if (!strcmp(verb, "STATUS") && !a && !b) {
    Serial.printf("STATUS %ld SIM_ONLY %d %d %ld %ld %.3f %.3f %.6f\n",
                  sequence, leftCommandMmS, rightCommandMmS,
                  static_cast<long>(odometry.leftTicks),
                  static_cast<long>(odometry.rightTicks),
                  odometry.xMm, odometry.yMm, odometry.headingRad);
  } else {
    error(sequence, "UNKNOWN_OR_BAD_ARGUMENTS");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("READY SIM_ONLY");
}

void loop() {
  while (Serial.available()) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') {
      if (lineOverflow) error(0, "LINE_TOO_LONG");
      else {
        line[lineLength] = '\0';
        processLine(line);
      }
      lineLength = 0;
      lineOverflow = false;
    } else if (ch != '\r' && !lineOverflow) {
      if (lineLength < kLineCapacity - 1) line[lineLength++] = ch;
      else lineOverflow = true;
    }
  }
  if ((leftCommandMmS || rightCommandMmS) &&
      millis() - lastDriveMs > kCommandTimeoutMs) {
    leftCommandMmS = rightCommandMmS = 0;
  }
}
