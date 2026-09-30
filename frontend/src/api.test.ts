import { test, expect, vi } from 'vitest';
import { queryReport, reportSchema, safeUrl, validDate } from './api';
import { reportFixture } from './test/fixture';

test('browser rejects impossible source states instead of guessing success', () => {
  for (const kind of ['missing', 'all-failed', 'failure-with-records', 'duplicate', 'naive']) {
    const report: any = reportFixture();
    if (kind === 'missing') delete report.source_status.lark_tasks;
    if (kind === 'all-failed') Object.keys(report.source_status).forEach(key => { report.source_status[key] = 'failure'; });
    if (kind === 'failure-with-records') report.source_status.lark_tasks = 'failure';
    if (kind === 'duplicate') report.members.push(report.members[0]);
    if (kind === 'naive') report.generated_at = '2026-09-25T18:00:00';
    expect(reportSchema.safeParse(report).success).toBe(false);
  }
});
test('a mismatched report date cannot look like the requested day', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(reportFixture('2026-09-26')))));
  expect(await queryReport('2026-09-25', new AbortController().signal)).toEqual({ kind: 'error', message: '日报响应格式异常' });
});
test('only web links may be opened and valid calendar dates queried', () => {
  for (const value of ['javascript:alert(1)', 'data:text/html,x', 'file:///private', '//example.com', null]) expect(safeUrl(value)).toBeUndefined();
  expect(safeUrl('https://example.com/a')).toBe('https://example.com/a');
  for (const value of ['20260925', '2026-02-30', '2026-9-25', '0000-01-01']) expect(validDate(value)).toBe(false);
  expect(validDate('2026-09-25')).toBe(true);
});
