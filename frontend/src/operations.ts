import { z } from 'zod';
import { reportSchema } from './api';

const id = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
const revision = z.string().regex(/^[0-9a-f]{64}$/);
const errorCode = z.enum(['non_workday', 'all_sources_failed', 'source_auth_failed', 'source_access_policy_denied', 'source_unavailable',
  'source_payload_invalid', 'report_write_failed', 'delivery_rejected', 'delivery_partial', 'delivery_unknown', 'operation_interrupted', 'internal_error']).nullable();
const source = z.strictObject({ status: z.enum(['pending', 'success', 'failure', 'disabled']), error_code: errorCode });
const sources = z.strictObject({ github_commits: source.nullable(), lark_tasks: source.nullable(), lark_messages: source.nullable() });
const delivery = z.strictObject({ status: z.enum(['not_requested', 'pending', 'accepted', 'rejected', 'partial_failure', 'unknown']),
  attempts: z.number().int().nonnegative(), error_code: errorCode }).refine(value => value.status !== 'not_requested' || value.attempts === 0);
export const operationSchema = z.strictObject({ operation_id: id, request_id: id, kind: z.enum(['generation', 'delivery']),
  report_date: z.iso.date(), status: z.enum(['running', 'succeeded', 'partial_failure', 'failed', 'skipped', 'unknown', 'interrupted']),
  created_at: z.iso.datetime({ offset: true }), updated_at: z.iso.datetime({ offset: true }), report_revision: revision.nullable(),
  sources, deliveries: z.strictObject({ email: delivery, lark: delivery }), error_code: errorCode,
  email_recipients: z.array(z.string()).nullable().default(null),
}).refine(value => Object.values(value.sources).every(source => value.kind === 'generation' ? source !== null : source === null));
const target = z.strictObject({ enabled: z.boolean(), label: z.string(), previous: delivery.nullable() });
export const previewSchema = z.strictObject({ report: reportSchema, report_revision: revision, sources: sources.nullable(),
  targets: z.strictObject({ email: target.extend({ recipients: z.array(z.string()) }), lark: target }) });
export type OperationView = z.infer<typeof operationSchema>;
export type PreviewView = z.infer<typeof previewSchema>;

const messages: Record<string, string> = {
  recipient_not_configured: '所选邮箱不在服务器配置中',
  invalid_request: '操作参数无效', invalid_report_date: '日期无效，请使用 YYYY-MM-DD',
  operation_unauthorized: '操作令牌无效或未提供', origin_not_allowed: '请求来源未允许',
  report_not_found: '该日期尚无日报', operation_not_found: '未找到该操作记录',
  idempotency_conflict: '同一请求标识不能用于不同操作', operation_busy: '已有操作正在执行，请先查看其结果',
  report_revision_changed: '日报已更新，请重新预览后推送', report_requires_regeneration: '当前日报使用旧版内容，请先重新采集并生成汇总版', delivery_not_repeatable: '该渠道已接受或结果待核实，不能重复推送',
  channel_not_configured: '所选推送渠道未配置', non_workday: '该日期为非工作日，不能推送',
  storage_read_failed: '日报读取失败，请稍后重新查询', invalid_report_data: '日报数据格式异常',
  operation_storage_failed: '操作记录不可用，未接受新操作', internal_error: '操作请求处理失败',
};
export class OperationError extends Error {
  constructor(public code: string, message: string) { super(message); }
}
async function request<T>(path: string, token: string, signal: AbortSignal, schema: z.ZodType<T>, body?: unknown, requestId?: string): Promise<T> {
  const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
  let response: Response;
  try {
    response = await fetch(`${base}/api/v1/${path}`, { method: body === undefined ? 'GET' : 'POST', signal,
      cache: 'no-store', credentials: 'omit', headers: { Accept: 'application/json', Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { 'Content-Type': 'application/json', 'Idempotency-Key': requestId! }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  } catch { throw new OperationError('network_error', '无法连接日报服务'); }
  let data: unknown;
  try { data = await response.json(); } catch { throw new OperationError('invalid_response', '操作响应格式异常'); }
  if (response.status !== 200 && response.status !== 202) {
    const error = z.object({ error: z.object({ code: z.string() }) }).safeParse(data);
    const code = error.success ? error.data.error.code : 'invalid_response';
    const allowed = response.status === 400 ? ['invalid_request', 'invalid_report_date', 'channel_not_configured', 'recipient_not_configured', 'non_workday']
      : response.status === 401 ? ['operation_unauthorized'] : response.status === 403 ? ['origin_not_allowed']
      : response.status === 404 ? ['report_not_found', 'operation_not_found']
      : response.status === 409 ? ['idempotency_conflict', 'operation_busy', 'report_revision_changed', 'report_requires_regeneration', 'delivery_not_repeatable']
      : response.status === 500 ? ['storage_read_failed', 'invalid_report_data', 'operation_storage_failed', 'internal_error'] : [];
    throw new OperationError(allowed.includes(code) ? code : 'invalid_response', allowed.includes(code) ? messages[code] : '操作响应格式异常');
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) throw new OperationError('invalid_response', '操作响应格式异常');
  return parsed.data;
}
export function generateReport(date: string, token: string, requestId: string, signal: AbortSignal) {
  return request('generations', token, signal, operationSchema.refine(value => value.kind === 'generation' && value.report_date === date && value.request_id === requestId), { report_date: date }, requestId);
}
export function getOperation(id: string, token: string, signal: AbortSignal) {
  return request(`operations/${encodeURIComponent(id)}`, token, signal, operationSchema.refine(value => value.operation_id === id));
}
export function getOperationByKey(key: string, token: string, signal: AbortSignal) {
  return request(`operations/by-key/${encodeURIComponent(key)}`, token, signal, operationSchema.refine(value => value.request_id === key));
}
export function getCurrentOperation(token: string, signal: AbortSignal) {
  return request('operations/current', token, signal, operationSchema.nullable());
}
export function getPreview(date: string, token: string, signal: AbortSignal) {
  return request(`reports/${encodeURIComponent(date)}/preview`, token, signal, previewSchema.refine(value => value.report.report_date === date));
}

export function deliverReport(date: string, revision: string, channels: ('email' | 'lark')[], emailRecipients: string[], token: string, requestId: string, signal: AbortSignal) {
  return request('deliveries', token, signal, operationSchema.refine(value => value.kind === 'delivery' && value.report_date === date
    && value.request_id === requestId && value.report_revision === revision
    && JSON.stringify(value.email_recipients) === JSON.stringify([...emailRecipients].sort())),
    { report_date: date, report_revision: revision, channels, email_recipients: [...emailRecipients].sort() }, requestId);
}
