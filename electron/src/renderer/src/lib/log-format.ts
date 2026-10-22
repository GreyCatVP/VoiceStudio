export type LogSeverity = 'error' | 'warning' | 'success' | 'debug' | 'info';

export function stripLogAnsi(line: string): string {
  let clean = '';
  for (let index = 0; index < line.length; index++) {
    if (line.charCodeAt(index) !== 27 || line[index + 1] !== '[') {
      clean += line[index];
      continue;
    }
    index += 2;
    while (index < line.length) {
      const code = line.charCodeAt(index);
      if (code >= 0x40 && code <= 0x7e) break;
      index++;
    }
  }
  return clean;
}

// "2026-10-21 14:06:46,769 INFO [omnivoice.api] …" — the logger's own level
// wins over words in the message ("'failures': 0" is not an error).
const LEVEL = /^\S+\s+\S+\s+(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b/;

export function logSeverity(line: string): LogSeverity {
  const value = stripLogAnsi(line);
  const level = LEVEL.exec(value)?.[1];
  if (level === 'ERROR' || level === 'CRITICAL' || level === 'FATAL') return 'error';
  if (level === 'WARNING' || level === 'WARN') return 'warning';
  if (level === 'DEBUG') return 'debug';
  if (level === 'INFO') {
    return /(?:ready|complete|completed|succeeded|healthy|loaded)\b/i.test(value) ? 'success' : 'info';
  }
  if (
    /(?:^|[\s[.:_-])(?:critical|fatal|error|exception|traceback|panic)(?:$|[\s\].:_-])/i.test(
      value,
    ) ||
    /(?:failed|failure|crashed|unexpectedly stopped|unhandled rejection)/i.test(value)
  ) {
    return 'error';
  }
  if (/(?:^|[\s[.:_-])(?:warn|warning)(?:$|[\s\].:_-])|deprecated|retrying/i.test(value)) {
    return 'warning';
  }
  if (/(?:ready|complete|completed|succeeded|healthy|loaded)\b/i.test(value)) return 'success';
  if (/(?:^|[\s[.:_-])(?:debug|trace)(?:$|[\s\].:_-])/i.test(value)) return 'debug';
  return 'info';
}
