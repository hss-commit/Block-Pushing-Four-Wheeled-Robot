#pragma once

// Bluetooth transport for the shared vision-test firmware and timed motor task.
void bluetoothReply(const char *id, const char *result) {
  String message = String("{\"protocol\":\"vision-bt-v1\",\"id\":\"") + id +
      "\",\"result\":\"" + result + "\",\"busy\":" +
      (isBusy() ? "true" : "false") + ",\"pulse_ms\":250,\"step_ms\":120,\"uptime_ms\":" +
      String(millis()) + "}";
  bluetooth.println(message);
}

void bluetoothCommand(const char *line) {
  char id[33] = {}, path[16] = {}, direction[12] = {}, expires[12] = {}, extra[2] = {};
  int fields = sscanf(line, "%32s %15s %11s %11s %1s", id, path, direction, expires, extra);
  bool valid = strlen(id) == 32;
  for (const char *p = id; *p; ++p) {
    if (!(*p >= '0' && *p <= '9') && !(*p >= 'a' && *p <= 'f')) valid = false;
  }
  if (!valid) { requestStop(); return; }
  if (fields == 2 && strcmp(path, "/stop") == 0) {
    requestStop();
    bluetoothReply(id, "stop_queued");
    return;
  }
  if (fields == 2 && strcmp(path, "/status") == 0) {
    bluetoothReply(id, "ready");
    return;
  }
  uint8_t command = 0;
  if (fields == 4 && strcmp(path, "/pulse") == 0 && strcmp(direction, "-") == 0) command = 1;
  if (fields == 4 && strcmp(path, "/step") == 0) {
    command = strcmp(direction, "forward") == 0 ? 2 :
              strcmp(direction, "left") == 0 ? 3 : strcmp(direction, "right") == 0 ? 4 : 0;
  }
  bool digits = expires[0] != '\0';
  for (const char *p = expires; *p; ++p) if (*p < '0' || *p > '9') digits = false;
  unsigned long long expiry = strtoull(expires, nullptr, 10);
  int32_t remaining = static_cast<int32_t>(static_cast<uint32_t>(expiry) - millis());
  // PC derives this deadline from a fresh status. Delayed serial movement is rejected.
  if (!command || !digits || expiry > UINT32_MAX || remaining <= 0 || remaining > 200) {
    requestStop();
    bluetoothReply(id, "invalid_or_expired");
    return;
  }
  if (lastToken == id) { bluetoothReply(id, "duplicate_ignored"); return; }
  if (isBusy()) { bluetoothReply(id, "busy"); return; }
  lastToken = id;
  setBusy(true);
  xQueueOverwrite(commands, &command);
  bluetoothReply(id, command == 1 ? "pulse_queued" : "step_queued");
}

void handleBluetooth() {
  static char line[128];
  static size_t used = 0;
  static bool discard = false, hadClient = false;
  static uint32_t firstByteAt = 0;
  bool connected = bluetooth.hasClient();
  if (!connected) {
    if (hadClient) requestStop();
    hadClient = false;
    used = 0;
    discard = false;
    while (bluetooth.available()) bluetooth.read();
    delay(2);
    return;
  }
  hadClient = true;
  if (used && millis() - firstByteAt > 300) {
    requestStop(); used = 0; discard = true;
  }
  for (int n = 0; n < 256 && bluetooth.available(); ++n) {
    char c = bluetooth.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (!discard && used) { line[used] = '\0'; bluetoothCommand(line); }
      used = 0; discard = false;
    } else if (!discard) {
      if (!used) firstByteAt = millis();
      if (c < 32 || c > 126 || used == sizeof(line) - 1) {
        requestStop(); used = 0; discard = true;
      } else line[used++] = c;
    }
  }
  delay(2);
}
