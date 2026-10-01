import { expect, test, vi } from 'vitest';
import { operationFixture, previewFixture } from './test/operationFixture';
const modules = import.meta.glob('./operations.ts');
async function api(): Promise<any> {
  expect(modules['./operations.ts'], 'Real operation API client is missing').toBeDefined();
  return modules['./operations.ts']();
}
function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }

test('token_is_memory_only_and_never_in_url_and_post_is_not_retried', async () => {
  const client = await api(); const fetchMock = vi.fn().mockResolvedValue(response(operationFixture(), 202)); vi.stubGlobal('fetch', fetchMock);
  const controller = new AbortController();
  const result = await client.generateReport('2026-09-25', 'private-token', operationFixture().request_id, controller.signal);
  expect(result.status).toBe('running'); expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, options] = fetchMock.mock.calls[0];
  expect(url).not.toContain('private-token');
  expect(options).toMatchObject({ method: 'POST', cache: 'no-store', credentials: 'omit', signal: controller.signal,
    headers: { Authorization: 'Bearer private-token', 'Idempotency-Key': operationFixture().request_id } });
  expect(JSON.parse(options.body)).toEqual({ report_date: '2026-09-25' });
  expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
});

test('status_and_preview_queries_use_validated_contracts_and_original_identity', async () => {
  const client = await api(); const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture()))
    .mockResolvedValueOnce(response(operationFixture())).mockResolvedValueOnce(response(null)).mockResolvedValueOnce(response(previewFixture())); vi.stubGlobal('fetch', fetchMock);
  const signal = new AbortController().signal; const id = operationFixture().operation_id;
  expect((await client.getOperation(id, 'token', signal)).operation_id).toBe(id);
  expect((await client.getOperationByKey(operationFixture().request_id, 'token', signal)).request_id).toBe(operationFixture().request_id);
  expect(await client.getCurrentOperation('token', signal)).toBeNull();
  expect((await client.getPreview('2026-09-25', 'token', signal)).report.report_date).toBe('2026-09-25');
  expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
    `http://127.0.0.1:8000/api/v1/operations/${id}`, `http://127.0.0.1:8000/api/v1/operations/by-key/${operationFixture().request_id}`,
    'http://127.0.0.1:8000/api/v1/operations/current', 'http://127.0.0.1:8000/api/v1/reports/2026-09-25/preview']);
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test.each([{}, { ...operationFixture(), status: 'delivered' }, { ...operationFixture(), error_code: 'private-marker' }])('bad operation payload is rejected safely', async body => {
  const client = await api(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(body)));
  await expect(client.getCurrentOperation('token', new AbortController().signal)).rejects.toThrow('操作响应格式异常');
});

test('private_http_error_and_invalid_json_are_not_displayed_or_retried', async () => {
  const client = await api(); const fetchMock = vi.fn().mockResolvedValueOnce(response({ error: { code: 'operation_unauthorized', message: 'private-marker' } }, 401))
    .mockResolvedValueOnce(new Response('{')).mockRejectedValueOnce(new TypeError('private-marker')); vi.stubGlobal('fetch', fetchMock);
  const signal = new AbortController().signal;
  await expect(client.getCurrentOperation('token', signal)).rejects.toMatchObject({ code: 'operation_unauthorized', message: '操作令牌无效或未提供' });
  await expect(client.getCurrentOperation('token', signal)).rejects.toThrow('操作响应格式异常');
  await expect(client.generateReport('2026-09-25', 'token', operationFixture().request_id, signal)).rejects.toThrow('无法连接日报服务');
  expect(fetchMock).toHaveBeenCalledTimes(3);
});


test('mismatched_operation_or_preview_cannot_be_accepted_as_requested_identity', async () => {
  const client = await api(); const signal = new AbortController().signal;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(operationFixture())));
  await expect(client.getOperation('c13e0218-2e9f-424e-bef6-8e5d6de79814', 'token', signal)).rejects.toThrow('操作响应格式异常');
  await expect(client.getOperationByKey('c6ff843b-f0c4-4c11-a23e-bd2d6e15c938', 'token', signal)).rejects.toThrow('操作响应格式异常');
  await expect(client.generateReport('2026-09-26', 'token', operationFixture().request_id, signal)).rejects.toThrow('操作响应格式异常');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(previewFixture())));
  await expect(client.getPreview('2026-09-26', 'token', signal)).rejects.toThrow('操作响应格式异常');
});

test('an_error_code_in_the_wrong_http_status_is_not_trusted', async () => {
  const client = await api(); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ error: { code: 'operation_unauthorized', message: 'private-marker' } }, 500)));
  await expect(client.getCurrentOperation('token', new AbortController().signal)).rejects.toMatchObject({ code: 'invalid_response', message: '操作响应格式异常' });
});


test.each([[400,'invalid_request'],[403,'origin_not_allowed'],[404,'operation_not_found'],[409,'operation_busy'],[500,'operation_storage_failed'],[418,'invalid_request'],[500,'constructor']])('HTTP %i/%s remains a safe single-request error', async (status, code) => {
  const client = await api(); const fetchMock = vi.fn().mockResolvedValue(response({ error: { code, message: 'private-marker' } }, status)); vi.stubGlobal('fetch', fetchMock);
  try { await client.getCurrentOperation('token', new AbortController().signal); throw new Error('Unexpected success'); }
  catch (error: any) { expect(error.message).not.toContain('private-marker'); expect(error.code).toBe(status === 418 || code === 'constructor' ? 'invalid_response' : code); }
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test('malformed_error_body_and_mixed_delivery_source_evidence_are_invalid', async () => {
  const client = await api(); const fetchMock = vi.fn().mockResolvedValue(response({ private: 'private-marker' }, 500)); vi.stubGlobal('fetch', fetchMock);
  await expect(client.getCurrentOperation('token', new AbortController().signal)).rejects.toThrow('操作响应格式异常');
  expect(client.operationSchema.safeParse({ ...operationFixture(), kind: 'delivery' }).success).toBe(false);
  expect(client.operationSchema.safeParse({ ...operationFixture(), kind: 'delivery', sources: { github_commits: null, lark_tasks: null, lark_messages: null } }).success).toBe(true);
});


test('delivery_post_contains_only_confirmed_date_revision_channels_and_original_key', async () => {
  const client = await api(); expect(client.deliverReport, 'Confirmed delivery client is missing').toBeTypeOf('function');
  const value = { ...operationFixture(), kind: 'delivery', report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null } };
  const fetchMock = vi.fn().mockResolvedValue(response(value, 202)); vi.stubGlobal('fetch', fetchMock);
  const result = await client.deliverReport('2026-09-25', 'a'.repeat(64), ['email','lark'], 'private-token', value.request_id, new AbortController().signal);
  expect(result.kind).toBe('delivery'); expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:8000/api/v1/deliveries');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ report_date: '2026-09-25', report_revision: 'a'.repeat(64), channels: ['email','lark'] });
  expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer private-token');
});
