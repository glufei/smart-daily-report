import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import App from './App';
import { operationFixture, previewFixture } from './test/operationFixture';
afterEach(() => vi.unstubAllEnvs());

test('operations_mode_has_explicit_token_and_generation_controls', () => {
  vi.stubEnv('VITE_API_MODE', 'operations'); render(<App />);
  expect(screen.getByLabelText('操作令牌')).toHaveAttribute('type', 'password');
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
});

test('readonly_mode_preserves_history_only_controls', () => {
  vi.stubEnv('VITE_API_MODE', 'readonly'); render(<App />);
  expect(screen.queryByLabelText('操作令牌')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '采集并生成' })).not.toBeInTheDocument();
});

function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
function setup(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubEnv('VITE_API_MODE', 'operations'); vi.stubGlobal('fetch', fetchMock); render(<App />);
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-25' } });
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'private-token' } });
  fireEvent.click(screen.getByRole('button', { name: '验证令牌' }));
}
function generate() { fireEvent.click(screen.getByRole('button', { name: '采集并生成' })); }

test('accepted_generation_is_running_not_success_and_does_not_send', async () => {
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => Promise.resolve(url.endsWith('/current') ? response(null) : response({ ...operationFixture(), request_id: (options.headers as Record<string, string>)['Idempotency-Key'] }, 202)));
  setup(fetchMock); await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled());
  generate(); await screen.findByText('正在生成日报…'); generate();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
  expect(fetchMock.mock.calls.filter(call => String(call[0]).includes('deliveries'))).toHaveLength(0);
  expect(localStorage.length).toBe(0); expect(sessionStorage.length).toBe(0);
});

test('lost_post_response_queries_original_key_without_resubmitting', async () => {
  let originalKey = ''; const lookupKeys: string[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(null));
    if (options.method === 'POST') { originalKey = (options.headers as Record<string, string>)['Idempotency-Key']; return Promise.reject(new TypeError('private-marker')); }
    if (url.includes('/by-key/')) { lookupKeys.push(url.split('/').at(-1)!); return Promise.resolve(response({ ...operationFixture('succeeded'), request_id: originalKey })); }
    return Promise.resolve(response(previewFixture()));
  });
  setup(fetchMock); await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(lookupKeys).toEqual([originalKey]); expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
  expect(screen.queryByText('private-marker')).not.toBeInTheDocument();
});

test('refresh_auth_recovers_current_operation_without_post', async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(response(operationFixture()))); setup(fetchMock);
  await screen.findByText('正在生成日报…');
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('polling_limit_does_not_cancel_or_mark_failed', async () => {
  vi.useFakeTimers(); const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(response(operationFixture()))); setup(fetchMock);
  await act(async () => {}); expect(screen.getByText('正在生成日报…')).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(120000));
  expect(screen.getByText('执行结果尚未确认')).toBeInTheDocument();
  const count = fetchMock.mock.calls.length; await act(() => vi.advanceTimersByTimeAsync(10000)); expect(fetchMock).toHaveBeenCalledTimes(count);
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' })); await act(async () => {});
  expect(fetchMock.mock.calls.length).toBeGreaterThan(count); expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('late_preview_for_A_cannot_replace_selected_B', async () => {
  let resolve!: (value: Response) => void;
  const fetchMock = vi.fn().mockImplementation((url: string) => url.endsWith('/current') ? Promise.resolve(response(operationFixture('succeeded')))
    : new Promise<Response>(done => { resolve = done; })); setup(fetchMock);
  await waitFor(() => expect(resolve).toBeDefined());
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } });
  await act(async () => resolve(response(previewFixture())));
  expect(screen.queryByRole('heading', { name: '示例研发团队' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('报告日期')).toHaveValue('2026-09-26');
  expect(screen.getByRole('button', { name: '验证令牌' })).toBeEnabled();
});

test('disabled_failure_and_zero_records_are_distinct', async () => {
  const preview = previewFixture(); preview.sources.lark_tasks.status = 'failure'; preview.report.source_status.lark_tasks = 'failure'; preview.report.members[0].tasks = [];
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('partial_failure'))).mockResolvedValue(response(preview)); setup(fetchMock);
  await screen.findByRole('heading', { name: '示例研发团队' });
  const member = within(screen.getByRole('article', { name: '示例成员乙' }));
  expect(member.getByText('今日无记录')).toBeInTheDocument();
  expect(member.getByText('未启用')).toBeInTheDocument(); expect(member.getByText('数据获取失败')).toBeInTheDocument();
});

test('legacy_preview_does_not_claim_current_source_enablement', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response({ ...previewFixture(), sources: null })); setup(fetchMock);
  await screen.findByText('来源启用情况未记录');
});


test('unauthorized_validation_clears_token_and_allows_reauthentication', async () => {
  const fetchMock = vi.fn().mockResolvedValue(response({ error: { code: 'operation_unauthorized', message: 'private-marker' } }, 401)); setup(fetchMock);
  await screen.findByText('操作令牌无效或未提供');
  expect(screen.getByLabelText('操作令牌')).toHaveValue('');
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'new-token' } });
  expect(screen.getByRole('button', { name: '验证令牌' })).toBeEnabled();
});

test('invalid_mode_is_visible_and_cannot_enable_operation_controls', () => {
  vi.stubEnv('VITE_API_MODE', 'invalid'); render(<App />);
  expect(screen.getByRole('alert')).toHaveTextContent('前端运行模式配置无效');
  expect(screen.queryByLabelText('操作令牌')).not.toBeInTheDocument();
});


test.each([['failed', '日报生成失败'], ['skipped', '该日期为非工作日，已跳过'], ['interrupted', '操作已中断，未自动重试'], ['unknown', '执行结果尚未确认']])('terminal %s is honest and never posts on refresh', async (status, text) => {
  const value = { ...operationFixture(status), report_revision: null };
  const fetchMock = vi.fn().mockResolvedValue(response(value)); setup(fetchMock);
  await screen.findByText(text); expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1].method).toBe('GET');
});

test('a_running_operation_on_another_day_is_visible_without_wrong_preview', async () => {
  const fetchMock = vi.fn().mockResolvedValue(response({ ...operationFixture(), report_date: '2026-09-24' })); setup(fetchMock);
  await screen.findByText('正在查看 2026-09-24 的操作结果');
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
});

test('polling_completion_reads_preview_and_stops_further_queries', async () => {
  vi.useFakeTimers(); const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture()))
    .mockResolvedValueOnce(response(operationFixture('succeeded'))).mockImplementation(() => Promise.resolve(response(previewFixture()))); setup(fetchMock);
  await act(async () => {}); await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(screen.getByRole('heading', { name: '示例研发团队' })).toBeInTheDocument();
  const calls = fetchMock.mock.calls.length; await act(() => vi.advanceTimersByTimeAsync(130000)); expect(fetchMock).toHaveBeenCalledTimes(calls);
});

test('polling_network_failure_can_be_queried_manually_without_resubmission', async () => {
  vi.useFakeTimers(); const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture())).mockRejectedValueOnce(new Error('private-marker'))
    .mockImplementation(() => Promise.resolve(response({ ...operationFixture('failed'), report_revision: null }))); setup(fetchMock);
  await act(async () => {}); await act(() => vi.advanceTimersByTimeAsync(2000)); expect(screen.getByText('无法连接日报服务')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' })); await act(async () => {});
  expect(screen.getByText('日报生成失败')).toBeInTheDocument(); expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('definite_post_rejection_does_not_query_or_replay', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockResolvedValue(response({ error: { code: 'invalid_request', message: 'private-marker' } }, 400)); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate(); await screen.findByText('操作参数无效');
  expect(fetchMock).toHaveBeenCalledTimes(2); expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled();
});

test('ambiguous_post_keeps_original_key_for_manual_lookup_and_blocks_new_post', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockRejectedValueOnce(new Error('private-marker'))
    .mockImplementation(() => Promise.resolve(response({ error: { code: 'operation_not_found', message: 'private-marker' } }, 404))); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate(); await screen.findByText('执行结果尚未确认');
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' })); await screen.findByText('未找到该操作记录');
  expect(fetchMock.mock.calls[2][0]).toBe(fetchMock.mock.calls[3][0]); expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
});

test('preview_read_error_is_safe_and_manually_recoverable', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded')))
    .mockResolvedValueOnce(response({ error: { code: 'storage_read_failed', message: 'private-marker' } }, 500))
    .mockResolvedValueOnce(response(operationFixture('succeeded'))).mockImplementation(() => Promise.resolve(response(previewFixture()))); setup(fetchMock);
  await screen.findByText('日报读取失败，请稍后重新查询');
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' })); await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.queryByText('private-marker')).not.toBeInTheDocument();
});

test('changing_token_before_auth_response_cannot_authenticate_old_token', async () => {
  let resolve!: (response: Response) => void; const fetchMock = vi.fn().mockImplementation(() => new Promise<Response>(done => { resolve = done; })); setup(fetchMock);
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'new-token' } }); await act(async () => resolve(response(null)));
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled(); expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
});

test('changing_date_before_post_reply_does_not_display_old_operation', async () => {
  let resolve!: (response: Response) => void; let key = '';
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => url.endsWith('/current') ? Promise.resolve(response(null))
    : new Promise<Response>(done => { resolve = done; key = (options.headers as Record<string, string>)['Idempotency-Key']; })); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate();
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } });
  await act(async () => resolve(response({ ...operationFixture(), request_id: key }, 202)));
  expect(screen.queryByText('正在生成日报…')).not.toBeInTheDocument(); expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
});

test('pending_source_evidence_is_not_rendered_as_empty_success', async () => {
  const preview = previewFixture(); preview.sources.github_commits.status = 'pending';
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response(preview)); setup(fetchMock);
  await screen.findByRole('heading', { name: '示例研发团队' }); expect(screen.getAllByText('正在采集…')).toHaveLength(2);
});


test('readonly_history_preserves_UTC_and_missing_optional_metadata', async () => {
  const report = previewFixture().report; report.generated_at = '2026-09-25T10:00:00Z';
  report.members[0].tasks[0].status_from = null; report.members[0].tasks[0].status_to = null; report.members[0].messages[0].chat_name = '';
  vi.stubEnv('VITE_API_MODE', 'readonly'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(report))); render(<App />);
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-25' } }); fireEvent.click(screen.getByRole('button', { name: '查看日报' }));
  await screen.findByRole('heading', { name: '示例研发团队' }); expect(screen.getByText(/UTC\+00:00/)).toBeInTheDocument();
  expect(screen.queryByText(/— →/)).not.toBeInTheDocument();
});

test('manual_current_query_remains_safe_when_operation_storage_fails', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockResolvedValue(response({ error: { code: 'operation_storage_failed', message: 'private-marker' } }, 500)); setup(fetchMock);
  await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '查询执行结果' }));
  await screen.findByText('操作记录不可用，未接受新操作'); expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('late_poll_after_observation_limit_cannot_replace_unknown_result', async () => {
  vi.useFakeTimers(); let resolve!: (value: Response) => void;
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture())).mockImplementation(() => new Promise<Response>(done => { resolve = done; })); setup(fetchMock);
  await act(async () => {}); await act(() => vi.advanceTimersByTimeAsync(120000));
  expect(screen.getByText('执行结果尚未确认')).toBeInTheDocument();
  await act(async () => resolve(response(operationFixture('succeeded'))));
  expect(screen.getByText('执行结果尚未确认')).toBeInTheDocument(); expect(fetchMock).toHaveBeenCalledTimes(2);
});

test('late_poll_error_after_date_switch_cannot_show_old_error', async () => {
  vi.useFakeTimers(); let reject!: (error: Error) => void;
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture())).mockImplementation(() => new Promise<Response>((_, done) => { reject = done; })); setup(fetchMock);
  await act(async () => {}); await act(() => vi.advanceTimersByTimeAsync(2000));
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } });
  await act(async () => reject(new Error('private-marker'))); expect(screen.queryByText('无法连接日报服务')).not.toBeInTheDocument();
});

test('late_authentication_error_is_ignored_after_token_change', async () => {
  let reject!: (error: Error) => void; const fetchMock = vi.fn().mockImplementation(() => new Promise<Response>((_, done) => { reject = done; })); setup(fetchMock);
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'new-token' } });
  await act(async () => reject(new Error('private-marker'))); expect(screen.queryByText('无法连接日报服务')).not.toBeInTheDocument();
});

test('late_preview_error_is_ignored_after_date_change', async () => {
  let reject!: (error: Error) => void; const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded')))
    .mockImplementation(() => new Promise<Response>((_, done) => { reject = done; })); setup(fetchMock);
  await waitFor(() => expect(reject).toBeDefined()); fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } });
  await act(async () => reject(new Error('private-marker'))); expect(screen.queryByText('无法连接日报服务')).not.toBeInTheDocument();
});

test('late_manual_query_is_ignored_after_token_change', async () => {
  let resolve!: (response: Response) => void; const fetchMock = vi.fn().mockResolvedValueOnce(response(null))
    .mockImplementation(() => new Promise<Response>(done => { resolve = done; })); setup(fetchMock);
  await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '查询执行结果' }));
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'new-token' } });
  await act(async () => resolve(response(operationFixture()))); expect(screen.queryByText('正在生成日报…')).not.toBeInTheDocument();
});


test('explicit_retry_after_by_key_404_reuses_original_key_and_date', async () => {
  const posts: { key: string; date: string }[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(null));
    if (url.includes('/by-key/')) return Promise.resolve(response({ error: { code: 'operation_not_found', message: 'private-marker' } }, 404));
    const request = { key: (options.headers as Record<string,string>)['Idempotency-Key'], date: JSON.parse(options.body as string).report_date }; posts.push(request);
    return posts.length === 1 ? Promise.reject(new Error('private-marker')) : Promise.resolve(response({ ...operationFixture(), request_id: request.key }, 202));
  }); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate(); await screen.findByText('执行结果尚未确认');
  fireEvent.click(screen.getByRole('button', { name: '重试原请求' })); await screen.findByText('正在生成日报…');
  expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]);
});


test('failed_lookup_cannot_offer_retry_until_non_acceptance_is_known', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockRejectedValue(new Error('private-marker')); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate(); await screen.findByText('执行结果尚未确认');
  expect(screen.queryByRole('button', { name: '重试原请求' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
});


test('restored_delivery_is_observed_without_starting_generation_or_delivery', async () => {
  const value = { ...operationFixture(), kind: 'delivery', report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null } };
  const fetchMock = vi.fn().mockResolvedValue(response(value)); setup(fetchMock); await screen.findByText('正在推送日报…');
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled(); expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});


test('completed_task_shows_real_completion_without_invented_previous_status', async () => {
  const preview = previewFixture(); preview.sources.lark_tasks.status = 'success';
  const task = preview.report.members[0].tasks[0]; task.status = 'completed'; task.status_from = null; task.status_to = 'completed';
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response(preview)); setup(fetchMock);
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.queryByText(/— →/)).not.toBeInTheDocument(); expect(screen.getByText('完成页面契约评审（已完成）')).toBeInTheDocument();
});


test('cancel_confirmation_never_sends_and_shows_fixed_targets_and_version', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockImplementation(() => Promise.resolve(response(previewFixture()))); setup(fetchMock);
  await screen.findByRole('heading', { name: '示例研发团队' }); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  const dialog = await screen.findByRole('dialog', { name: '确认推送日报' });
  expect(within(dialog).getByText('2026-09-25')).toBeInTheDocument(); expect(within(dialog).getByText('a'.repeat(64))).toBeInTheDocument();
  expect(within(dialog).getByText('邮件（1 位收件人）')).toBeInTheDocument(); expect(within(dialog).getByText('配置的日报群')).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button', { name: '取消' })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(0);
});

test('confirmation_sends_exactly_once_and_only_the_previewed_version', async () => {
  const posts: Record<string, unknown>[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(operationFixture('succeeded')));
    if (options.method === 'POST') {
      posts.push(JSON.parse(options.body as string));
      return Promise.resolve(response({ ...operationFixture(), kind: 'delivery', request_id: (options.headers as Record<string,string>)['Idempotency-Key'],
        report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null } }, 202));
    }
    return Promise.resolve(response(previewFixture()));
  }); setup(fetchMock); await screen.findByRole('heading', { name: '示例研发团队' });
  await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '推送日报' })); fireEvent.click(screen.getByRole('button', { name: '确认推送' }));
  await screen.findByText('正在推送日报…');
  expect(posts).toEqual([{ report_date: '2026-09-25', report_revision: 'a'.repeat(64), channels: ['email','lark'] }]);
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
});

test('date_change_invalidates_open_delivery_confirmation', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockImplementation(() => Promise.resolve(response(previewFixture()))); setup(fetchMock);
  await screen.findByRole('heading', { name: '示例研发团队' }); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '推送日报' })); await screen.findByRole('dialog');
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } }); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(0);
});


function deliveryFixture(status = 'succeeded', email = 'accepted', lark = 'accepted') {
  return { ...operationFixture(status), kind: 'delivery', report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null },
    deliveries: { email: { status: email, attempts: 1, error_code: null }, lark: { status: lark, attempts: 1, error_code: null } } };
}
async function openDelivery() {
  await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '推送日报' })); return screen.findByRole('dialog');
}
test.each(['accepted', 'partial_failure', 'unknown', 'pending'])('previous %s blocks whole-channel resend but rejected channel can be selected', async status => {
  const preview = { ...previewFixture(), targets: { email: { enabled: true, label: '邮件（1 位收件人）', previous: { status, attempts: 1, error_code: null } },
    lark: { enabled: true, label: '配置的日报群', previous: { status: 'rejected', attempts: 1, error_code: null } } } };
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response(preview)); setup(fetchMock);
  const dialog = await openDelivery(); expect(screen.getByRole('checkbox', { name: '邮件' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: '邮件' })).not.toBeChecked(); expect(screen.getByRole('checkbox', { name: '飞书' })).toBeChecked();
  expect(within(dialog).queryByText('邮件（1 位收件人）')).not.toBeInTheDocument(); expect(within(dialog).getByText('配置的日报群')).toBeInTheDocument();
});
test('channel_selection_zero_disables_confirmation_and_cancel_event_is_safe', async () => {
  setup(vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response(previewFixture())));
  await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled());
  fireEvent.click(screen.getByRole('checkbox', { name: '邮件' })); fireEvent.click(screen.getByRole('checkbox', { name: '飞书' }));
  expect(screen.getByRole('button', { name: '推送日报' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '邮件' })); const dialog = await openDelivery();
  expect(within(dialog).getByRole('button', { name: '取消' })).toHaveFocus();
  fireEvent(dialog, new Event('cancel', { bubbles: true, cancelable: true })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
test.each([['succeeded', 'accepted', 'accepted', '所选渠道已受理，请核对实际收件'],
  ['partial_failure', 'accepted', 'rejected', '部分渠道受理失败，请核对渠道结果'],
  ['unknown', 'unknown', 'accepted', '推送结果未知，请先核实，不能重复推送'],
  ['failed', 'rejected', 'rejected', '所选渠道明确拒绝，可核对后仅重试失败渠道']])('delivery %s reports evidence without claiming receipt', async (status, email, lark, text) => {
  const value = deliveryFixture(status, email, lark);
  const preview = { ...previewFixture(), targets: { email: { enabled: true, label: '邮件（1 位收件人）', previous: value.deliveries.email },
    lark: { enabled: true, label: '配置的日报群', previous: value.deliveries.lark } } };
  const fetchMock = vi.fn().mockResolvedValueOnce(response(value)).mockResolvedValue(response(preview)); setup(fetchMock);
  await screen.findByText(text); await screen.findByRole('heading', { name: '示例研发团队' });
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
  expect(screen.queryByText('推送已送达')).not.toBeInTheDocument();
});
test('manual_preview_loads_existing_content_without_generation', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockResolvedValue(response(previewFixture())); setup(fetchMock);
  await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  await screen.findByRole('heading', { name: '示例研发团队' }); expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});
test('manual_preview_failure_and_late_reply_cannot_keep_old_confirmation', async () => {
  let resolve!: (value: Response) => void;
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValueOnce(response(previewFixture()))
    .mockImplementation(() => new Promise<Response>(done => { resolve = done; })); setup(fetchMock); await openDelivery();
  fireEvent.click(screen.getByRole('button', { name: '取消' })); fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } }); await act(async () => resolve(response(previewFixture())));
  expect(screen.queryByRole('button', { name: '推送日报' })).not.toBeInTheDocument();
});
test('manual_preview_failure_has_safe_error_and_never_sends', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockRejectedValue(new Error('private-marker')); setup(fetchMock);
  await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '预览日报' })); await screen.findByText('无法连接日报服务');
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});
test('lost_delivery_response_queries_original_key_without_resending', async () => {
  let key = ''; const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(operationFixture('succeeded')));
    if (options.method === 'POST') { key = (options.headers as Record<string,string>)['Idempotency-Key']; return Promise.reject(new Error('private-marker')); }
    if (url.includes('/by-key/')) return Promise.resolve(response({ ...deliveryFixture(), request_id: key }));
    return Promise.resolve(response(previewFixture()));
  }); setup(fetchMock); await openDelivery(); fireEvent.click(screen.getByRole('button', { name: '确认推送' }));
  await screen.findByText('所选渠道已受理，请核对实际收件'); expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
  expect(fetchMock.mock.calls.some(call => String(call[0]).endsWith(`/by-key/${key}`))).toBe(true);
});
test('delivery_401_clears_token_without_retry', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValueOnce(response(previewFixture()))
    .mockResolvedValue(response({ error: { code: 'operation_unauthorized', message: 'private-marker' } }, 401)); setup(fetchMock);
  await openDelivery(); fireEvent.click(screen.getByRole('button', { name: '确认推送' })); await screen.findByText('操作令牌无效或未提供');
  expect(screen.getByLabelText('操作令牌')).toHaveValue(''); expect(screen.queryByRole('button', { name: '推送日报' })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
});
test.each(['report_revision_changed', 'delivery_not_repeatable'])('%s requires a fresh preview before another confirmation', async code => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValueOnce(response(previewFixture()))
    .mockResolvedValue(response({ error: { code, message: 'private-marker' } }, 409)); setup(fetchMock);
  await openDelivery(); fireEvent.click(screen.getByRole('button', { name: '确认推送' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '推送日报' })).not.toBeInTheDocument());
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(1);
});
test('history_query_invalidates_confirmation_before_different_content_is_displayed', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValueOnce(response(previewFixture()))
    .mockResolvedValue(response(previewFixture().report)); setup(fetchMock); await openDelivery();
  fireEvent.click(screen.getByRole('button', { name: '查看日报' })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(0);
});
test('operations_mode_labels_the_control_mode_honestly', () => {
  vi.stubEnv('VITE_API_MODE', 'operations'); render(<App />);
  expect(screen.getByText('采集与推送')).toBeInTheDocument(); expect(screen.queryByText('只读')).not.toBeInTheDocument();
});


test('manual_lookup_404_after_initial_network_loss_offers_original_key_retry', async () => {
  const posts: { key: string; body: string }[] = []; let lookups=0;
  const fetchMock=vi.fn().mockImplementation((url:string, options:RequestInit)=> {
    if(url.endsWith('/current')) return Promise.resolve(response(null));
    if(url.includes('/by-key/')) {
      lookups++;
      return lookups===1 ? Promise.reject(new Error('private-marker')) : Promise.resolve(response({error:{code:'operation_not_found'}},404));
    }
    posts.push({key:(options.headers as Record<string,string>)['Idempotency-Key'],body:options.body as string});
    return posts.length===1 ? Promise.reject(new Error('private-marker')) : Promise.resolve(response({...operationFixture(),request_id:posts[0].key},202));
  }); setup(fetchMock);
  await waitFor(()=>expect(screen.getByRole('button',{name:'采集并生成'})).toBeEnabled()); generate();
  await screen.findByText('执行结果尚未确认'); expect(screen.queryByRole('button',{name:'重试原请求'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'查询执行结果'})); await screen.findByText('未找到该操作记录');
  fireEvent.click(await screen.findByRole('button',{name:'重试原请求'})); await screen.findByText('正在生成日报…');
  expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]);
});
