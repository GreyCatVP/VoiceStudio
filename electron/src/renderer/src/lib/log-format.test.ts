import { describe, expect, it } from 'vitest';
import { logSeverity, stripLogAnsi } from './log-format';

describe('log formatting', () => {
  it.each([
    ['2026-09-12 ERROR backend crashed', 'error'],
    ['Traceback (most recent call last):', 'error'],
    ['WARNING model is retrying', 'warning'],
    ['INFO Application startup complete.', 'success'],
    ['DEBUG request headers', 'debug'],
    ['INFO GET /health 200', 'info'],
  ])('classifies %s as %s', (line, severity) => {
    expect(logSeverity(line)).toBe(severity);
  });

  it('removes terminal color escapes before display', () => {
    expect(stripLogAnsi('\u001B[31mERROR\u001B[0m failed')).toBe('ERROR failed');
  });
});

describe('logger levels', () => {
  it('trusts the logged level over words in the message', () => {
    expect(logSeverity("2026-10-21 14:06:46,769 INFO [omnivoice.render] render trace {'failures': 0}")).toBe('info');
    expect(logSeverity('2026-10-21 14:06:46,769 INFO [omnivoice.api] model loaded')).toBe('success');
    expect(logSeverity('2026-10-21 14:06:46,769 WARNING [omnivoice.api] retrying in 2s')).toBe('warning');
    expect(logSeverity('2026-10-21 14:06:46,769 ERROR [omnivoice.api] boom')).toBe('error');
  });

  it('still classifies lines without a level by their words', () => {
    expect(logSeverity('Traceback (most recent call last):')).toBe('error');
  });
});
