import { z } from 'zod';

const timestamp = z.iso.datetime({ offset: true });
const linked = { record_id: z.string(), url: z.string().nullable() };
const commit = z.object({ ...linked, repository: z.string(), message: z.string(), committed_at: timestamp,
  additions: z.number().int(), deletions: z.number().int(), files_changed: z.number().int() });
const task = z.object({ ...linked, title: z.string(), status: z.string(), status_from: z.string().nullable(),
  status_to: z.string().nullable(), changed_at: timestamp });
const message = z.object({ ...linked, content: z.string(), sent_at: timestamp, chat_name: z.string() });
const source = z.enum(['success', 'failure']);
export const reportSchema = z.object({
  report_date: z.iso.date(), team_name: z.string(), generated_at: timestamp,
  source_status: z.strictObject({ github_commits: source, lark_tasks: source, lark_messages: source }),
  members: z.array(z.object({ member_id: z.string(), display_name: z.string(),
    commits: z.array(commit), tasks: z.array(task), messages: z.array(message) })),
}).superRefine((report, context) => {
  const fail = () => context.addIssue({ code: 'custom', message: 'Invalid saved report' });
  if (Object.values(report.source_status).every(status => status === 'failure')) fail();
  if (new Set(report.members.map(member => member.member_id)).size !== report.members.length) fail();
  for (const member of report.members) {
    if (report.source_status.github_commits === 'failure' && member.commits.length) fail();
    if (report.source_status.lark_tasks === 'failure' && member.tasks.length) fail();
    if (report.source_status.lark_messages === 'failure' && member.messages.length) fail();
  }
});
export type Report = z.infer<typeof reportSchema>;
export type SourceStatus = Report['source_status'];
export type QueryResult = { kind: 'report'; report: Report } | { kind: 'missing' } | { kind: 'error'; message: string };
export const FORMAT_ERROR = '日报响应格式异常';

export function safeUrl(value: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}

export function validDate(value: string): boolean { return z.iso.date().safeParse(value).success && Number(value.slice(0, 4)) >= 1; }

const errorMessages: Record<string, string> = {
  invalid_report_date: '日期无效，请使用 YYYY-MM-DD', origin_not_allowed: '请求来源未允许',
  method_not_allowed: '此接口仅允许查询', storage_read_failed: '日报读取失败，请稍后重新查询',
  invalid_report_data: '日报数据格式异常', internal_error: '日报查询失败',
};
const errorSchema = z.object({ error: z.object({ code: z.string(), message: z.string() }) });

export async function queryReport(date: string, signal: AbortSignal): Promise<QueryResult> {
  const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
  const response = await fetch(`${base}/api/v1/reports/${encodeURIComponent(date)}`, {
    method: 'GET', signal, cache: 'no-store', credentials: 'omit', headers: { Accept: 'application/json' },
  });
  let body: unknown;
  try { body = await response.json(); }
  catch { return { kind: 'error', message: FORMAT_ERROR }; }
  if (response.status === 200) {
    const parsed = reportSchema.safeParse(body);
    return parsed.success && parsed.data.report_date === date
      ? { kind: 'report', report: parsed.data } : { kind: 'error', message: FORMAT_ERROR };
  }
  const parsed = errorSchema.safeParse(body);
  if (!parsed.success) return { kind: 'error', message: FORMAT_ERROR };
  const code = parsed.data.error.code;
  if (response.status === 404 && code === 'report_not_found') return { kind: 'missing' };
  const expected = response.status === 400 ? ['invalid_report_date'] : response.status === 403 ? ['origin_not_allowed']
    : response.status === 405 ? ['method_not_allowed'] : response.status === 500
      ? ['storage_read_failed', 'invalid_report_data', 'internal_error'] : [];
  return { kind: 'error', message: expected.includes(code) ? errorMessages[code] : FORMAT_ERROR };
}
