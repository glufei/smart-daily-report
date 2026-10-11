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
  const value = { ...operationFixture(), kind: 'delivery', email_recipients: ['fixture@example.invalid'], report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null } };
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
  await screen.findByRole('heading', { name: '示例研发团队' }); await selectFixtureRecipient(); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  const dialog = await screen.findByRole('dialog', { name: '确认推送日报' });
  expect(within(dialog).getByText('2026-09-25')).toBeInTheDocument(); expect(within(dialog).getByText('a'.repeat(64))).toBeInTheDocument();
  expect(within(dialog).getByText('fixture@example.invalid')).toBeInTheDocument(); expect(within(dialog).getByText('配置的日报群')).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button', { name: '取消' })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(0);
});

test('confirmation_sends_exactly_once_and_only_the_previewed_version', async () => {
  const posts: Record<string, unknown>[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(operationFixture('succeeded')));
    if (options.method === 'POST') {
      posts.push(JSON.parse(options.body as string));
      return Promise.resolve(response({ ...operationFixture(), kind: 'delivery', email_recipients: ['fixture@example.invalid'], request_id: (options.headers as Record<string,string>)['Idempotency-Key'],
        report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null } }, 202));
    }
    return Promise.resolve(response(previewFixture()));
  }); setup(fetchMock); await screen.findByRole('heading', { name: '示例研发团队' });
  await selectFixtureRecipient(); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '推送日报' })); fireEvent.click(screen.getByRole('button', { name: '确认推送' }));
  await screen.findByText('正在推送日报…');
  expect(posts).toEqual([{ report_date: '2026-09-25', report_revision: 'a'.repeat(64), channels: ['email','lark'], email_recipients: ['fixture@example.invalid'] }]);
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
});

test('date_change_invalidates_open_delivery_confirmation', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockImplementation(() => Promise.resolve(response(previewFixture()))); setup(fetchMock);
  await screen.findByRole('heading', { name: '示例研发团队' }); await selectFixtureRecipient(); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: '推送日报' })); await screen.findByRole('dialog');
  fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: '2026-09-26' } }); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(0);
});


function deliveryFixture(status = 'succeeded', email = 'accepted', lark = 'accepted') {
  return { ...operationFixture(status), kind: 'delivery', email_recipients: ['fixture@example.invalid'], report_revision: 'a'.repeat(64), sources: { github_commits: null, lark_tasks: null, lark_messages: null },
    deliveries: { email: { status: email, attempts: 1, error_code: null }, lark: { status: lark, attempts: 1, error_code: null } } };
}
async function selectFixtureRecipient() {
  const checkbox = await screen.findByRole('checkbox', { name: 'fixture@example.invalid' });
  if (!(checkbox as HTMLInputElement).checked) fireEvent.click(checkbox);
}
async function openDelivery() {
  await selectFixtureRecipient(); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '推送日报' })); return screen.findByRole('dialog');
}
test.each(['accepted', 'partial_failure', 'unknown', 'pending'])('previous %s keeps email manually selectable while lark rejection is retryable', async status => {
  const preview = { ...previewFixture(), targets: { email: { enabled: true, label: '邮件（1 位收件人）', recipients: ['fixture@example.invalid'], previous: { status, attempts: 1, error_code: null } },
    lark: { enabled: true, label: '配置的日报群', previous: { status: 'rejected', attempts: 1, error_code: null } } } };
  const fetchMock = vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response(preview)); setup(fetchMock);
  const dialog = await openDelivery(); expect(screen.getByRole('checkbox', { name: '邮件' })).toBeEnabled();
  expect(screen.getByRole('checkbox', { name: '邮件' })).toBeChecked(); expect(screen.getByRole('checkbox', { name: '飞书' })).toBeChecked();
  expect(within(dialog).getByText('fixture@example.invalid')).toBeInTheDocument(); expect(within(dialog).getByText('配置的日报群')).toBeInTheDocument();
});
test('channel_selection_zero_disables_confirmation_and_cancel_event_is_safe', async () => {
  setup(vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockResolvedValue(response(previewFixture())));
  await selectFixtureRecipient(); await waitFor(() => expect(screen.getByRole('button', { name: '推送日报' })).toBeEnabled());
  fireEvent.click(screen.getByRole('checkbox', { name: '邮件' })); fireEvent.click(screen.getByRole('checkbox', { name: '飞书' }));
  expect(screen.getByRole('button', { name: '推送日报' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '邮件' })); const dialog = await openDelivery();
  expect(within(dialog).getByRole('button', { name: '取消' })).toHaveFocus();
  fireEvent(dialog, new Event('cancel', { bubbles: true, cancelable: true })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
test.each([['succeeded', 'accepted', 'accepted', '所选渠道已受理，请核对实际收件'],
  ['partial_failure', 'accepted', 'rejected', '部分渠道受理失败，请核对渠道结果'],
  ['unknown', 'unknown', 'accepted', '推送结果未知，请先核实；未自动重发'],
  ['failed', 'rejected', 'rejected', '所选渠道明确拒绝，可核对后仅重试失败渠道']])('delivery %s reports evidence without claiming receipt', async (status, email, lark, text) => {
  const value = deliveryFixture(status, email, lark);
  const preview = { ...previewFixture(), targets: { email: { enabled: true, label: '邮件（1 位收件人）', recipients: ['fixture@example.invalid'], previous: value.deliveries.email },
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


test('reauthentication_does_not_release_unknown_request_based_on_unrelated_current', async () => {
  const posts: { key: string; body: string }[] = []; let currentReads = 0;
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(++currentReads === 1 ? null : operationFixture('succeeded')));
    if (url.includes('/by-key/')) return Promise.reject(new Error('private-marker'));
    if (options.method === 'POST') {
      posts.push({ key: (options.headers as Record<string, string>)['Idempotency-Key'], body: options.body as string });
      return Promise.reject(new Error('private-marker'));
    }
    return Promise.resolve(response(previewFixture()));
  }); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate();
  await screen.findByText('执行结果尚未确认');
  fireEvent.click(screen.getByRole('button', { name: '验证令牌' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '验证令牌' })).toBeEnabled());
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled(); generate();
  expect(posts).toHaveLength(1); expect(currentReads).toBe(1);
  expect(fetchMock.mock.calls.filter(call => String(call[0]).endsWith(`/by-key/${posts[0].key}`))).toHaveLength(2);
});

test('reauthentication_404_allows_explicit_retry_of_only_original_request', async () => {
  const posts: { key: string; body: string }[] = []; let lookups = 0; let currentReads = 0;
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(++currentReads === 1 ? null : operationFixture('succeeded')));
    if (url.includes('/by-key/')) return ++lookups === 1 ? Promise.reject(new Error('private-marker'))
      : Promise.resolve(response({ error: { code: 'operation_not_found' } }, 404));
    if (options.method === 'POST') {
      posts.push({ key: (options.headers as Record<string, string>)['Idempotency-Key'], body: options.body as string });
      return posts.length === 1 ? Promise.reject(new Error('private-marker'))
        : Promise.resolve(response({ ...operationFixture(), request_id: posts[0].key }, 202));
    }
    return Promise.resolve(response(previewFixture()));
  }); setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '采集并生成' })).toBeEnabled()); generate();
  await screen.findByText('执行结果尚未确认');
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'replacement-private-token' } });
  fireEvent.click(screen.getByRole('button', { name: '验证令牌' }));
  fireEvent.click(await screen.findByRole('button', { name: '重试原请求' }));
  await screen.findByText('正在生成日报…');
  expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]); expect(currentReads).toBe(1);
});


test('restored_delivery_results_stay_bound_to_original_version_after_same_date_update', async () => {
  const delivered = deliveryFixture('partial_failure', 'accepted', 'rejected');
  const newer = previewFixture(); newer.report_revision = 'b'.repeat(64); newer.report.team_name = '后续生成的新日报';
  const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(response(url.endsWith('/current') ? delivered : newer)));
  setup(fetchMock);
  await waitFor(() => expect(screen.getByRole('button', { name: '验证令牌' })).toBeEnabled());
  const results = screen.getByRole('region', { name: '推送执行结果' });
  expect(within(results).getByText('a'.repeat(64))).toBeInTheDocument();
  expect(within(results).getByText(/2026-09-25/)).toBeInTheDocument();
  expect(within(results).getByText('本次邮件结果：服务商已受理')).toBeInTheDocument();
  expect(within(results).getByText('本次飞书结果：明确拒绝，可单独重提')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: '后续生成的新日报' })).not.toBeInTheDocument();
  expect(screen.getByText(/日报已更新，请重新预览/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  await screen.findByRole('heading', { name: '后续生成的新日报' });
  expect(within(screen.getByRole('region', { name: '推送执行结果' })).getByText('a'.repeat(64))).toBeInTheDocument();
  expect(screen.getByText('b'.repeat(64))).toBeInTheDocument();
  expect(within(results).getByText('本次邮件结果：服务商已受理')).toBeInTheDocument();
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});


test.each(['', '   '])('blank_token_validation_guides_user_without_network_request (%j)', async value => {
  const fetchMock = vi.fn().mockResolvedValue(response(null));
  vi.stubEnv('VITE_API_MODE', 'operations'); vi.stubGlobal('fetch', fetchMock); render(<App />);
  const input = screen.getByLabelText('操作令牌');
  fireEvent.change(input, { target: { value } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '验证令牌' })); });
  expect(fetchMock).not.toHaveBeenCalled();
  const panel = within(screen.getByRole('region', { name: '日报操作' }));
  expect(panel.getByRole('status')).toHaveTextContent(/请输入操作令牌/);
  expect(input).toHaveFocus();
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
  fireEvent.change(input, { target: { value: 'not-yet-verified-token' } });
  expect(panel.queryByText('请输入操作令牌')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '采集并生成' })).toBeDisabled();
});

test('unauthenticated_generation_explains_disabled_action_without_request', () => {
  const fetchMock = vi.fn();
  vi.stubEnv('VITE_API_MODE', 'operations'); vi.stubGlobal('fetch', fetchMock); render(<App />);
  const button = screen.getByRole('button', { name: '采集并生成' });
  expect(button).toBeDisabled();
  expect(button).toHaveAccessibleDescription(/请先输入并验证操作令牌/);
  fireEvent.click(button);
  fireEvent.change(screen.getByLabelText('操作令牌'), { target: { value: 'not-yet-verified-token' } });
  expect(button).toBeDisabled();
  expect(button).toHaveAccessibleDescription(/请先输入并验证操作令牌/);
  expect(fetchMock).not.toHaveBeenCalled();
});


test('query_feedback_loading_then_completed_even_when_result_is_unchanged', async () => {
  let resolve!: (value: Response) => void;
  const fetchMock = vi.fn().mockImplementation((url: string) => url.endsWith('/current') ? Promise.resolve(response(operationFixture('succeeded')))
    : url.includes('/preview') ? Promise.resolve(response(previewFixture())) : new Promise<Response>(done => { resolve = done; }));
  setup(fetchMock); await screen.findByRole('heading', { name: '示例研发团队' });
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-11T02:00:00Z'));
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' }));
  expect(screen.getByRole('button', { name: '正在查询执行结果…' })).toBeDisabled();
  await act(async () => resolve(response(operationFixture('succeeded'))));
  expect(screen.getByText(/执行结果查询完成/)).toBeVisible();
  const firstTime = screen.getByLabelText('本次查询时间').getAttribute('datetime');
  vi.setSystemTime(new Date('2026-10-11T02:01:00Z'));
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' }));
  await act(async () => resolve(response(operationFixture('succeeded'))));
  expect(screen.getByLabelText('本次查询时间').getAttribute('datetime')).not.toBe(firstTime);
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('query_feedback_null_reports_empty_without_authentication_message', async () => {
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(response(null))); setup(fetchMock);
  await screen.findByText('令牌已验证');
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' }));
  await screen.findByText('暂无执行记录');
  expect(screen.queryByText('令牌已验证')).not.toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '推送执行结果' })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('preview_feedback_success_focuses_current_report_heading', async () => {
  let resolve!: (value: Response) => void;
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockImplementation(() => new Promise<Response>(done => { resolve = done; }));
  setup(fetchMock); await screen.findByText('令牌已验证');
  fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  await act(async () => resolve(response(previewFixture())));
  expect(screen.getByRole('heading', { name: '示例研发团队' })).toHaveFocus();
  expect(screen.getByText(/已加载 2026-09-25 日报预览/)).toBeVisible();
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test.each(['查询执行结果', '预览日报'])('manual_query_and_preview_timeout_after_ten_seconds: %s', async action => {
  let resolve!: (value: Response) => void;
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null)).mockImplementation(() => new Promise<Response>(done => { resolve = done; }));
  setup(fetchMock); await screen.findByText('令牌已验证'); vi.useFakeTimers();
  fireEvent.click(screen.getByRole('button', { name: action }));
  await act(async () => vi.advanceTimersByTimeAsync(9999));
  expect(screen.queryByText(/请求超时/)).not.toBeInTheDocument();
  await act(async () => vi.advanceTimersByTimeAsync(1));
  expect(screen.getByText(/请求超时/)).toBeVisible();
  expect(screen.getByRole('button', { name: action })).toBeEnabled();
  await act(async () => resolve(response(action === '预览日报' ? previewFixture() : null)));
  expect(screen.getByText(/请求超时/)).toBeVisible();
  expect(screen.queryByRole('heading', { name: '示例研发团队' })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test.each(['报告日期', '操作令牌'])('late_preview_after_date_or_token_change_does_not_focus: %s', async field => {
  let resolve!: (value: Response) => void;
  setup(vi.fn().mockResolvedValueOnce(response(null)).mockImplementation(() => new Promise<Response>(done => { resolve = done; })));
  await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  const input = screen.getByLabelText(field); input.focus();
  fireEvent.change(input, { target: { value: field === '报告日期' ? '2026-09-24' : 'new-private-token' } });
  await act(async () => resolve(response(previewFixture())));
  expect(input).toHaveFocus();
  expect(screen.queryByRole('heading', { name: '示例研发团队' })).not.toBeInTheDocument();
  expect(screen.queryByText(/已加载 2026-09-25 日报预览/)).not.toBeInTheDocument();
});

test('automatic_preview_does_not_move_focus', async () => {
  let resolve!: (value: Response) => void;
  setup(vi.fn().mockResolvedValueOnce(response(operationFixture('succeeded'))).mockImplementation(() => new Promise<Response>(done => { resolve = done; })));
  await waitFor(() => expect(resolve).toBeTypeOf('function'));
  const input = screen.getByLabelText('操作令牌'); input.focus();
  await act(async () => resolve(response(previewFixture())));
  expect(input).toHaveFocus();
});

test.each([
  ['missing', 404, { error: { code: 'report_not_found' } }, '该日期尚无日报'],
  ['unauthorized', 401, { error: { code: 'operation_unauthorized' } }, '操作令牌无效或未提供'],
  ['network', 0, null, '无法连接日报服务'],
] as const)('preview_feedback_failure_is_explicit_and_cannot_send: %s', async (_kind, status, body, message) => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(null));
  if (status) fetchMock.mockResolvedValue(response(body, status)); else fetchMock.mockRejectedValue(new TypeError('synthetic network loss'));
  setup(fetchMock); await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  await screen.findByText(message);
  expect(screen.queryByRole('button', { name: '推送日报' })).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});


test('preview_feedback_loading_before_response', async () => {
  setup(vi.fn().mockResolvedValueOnce(response(null)).mockImplementation(() => new Promise<Response>(() => {})));
  await screen.findByText('令牌已验证'); fireEvent.click(screen.getByRole('button', { name: '预览日报' }));
  expect(screen.getByRole('button', { name: '正在加载日报预览…' })).toBeDisabled();
});

test('query_feedback_completion_describes_the_execution_date', async () => {
  const value = { ...operationFixture('succeeded'), report_date: '2026-09-24' };
  setup(vi.fn().mockImplementation(() => Promise.resolve(response(value)))); await screen.findByText('正在查看 2026-09-24 的操作结果');
  fireEvent.click(screen.getByRole('button', { name: '查询执行结果' }));
  await screen.findByText(/执行结果查询完成/);
  expect(screen.getByLabelText('本次查询时间')).toBeVisible();
  expect(screen.getByText(/操作：生成日报 · 2026-09-24/)).toBeVisible();
});


function recipientPreview() {
  const value = previewFixture(); value.targets.email.recipients = ['member@example.com', 'mentor@example.com']; return value;
}
async function setupRecipients(previous: string | null = null, legacy = false) {
  const preview = recipientPreview();
  if (previous) preview.targets.email.previous = { status: previous, attempts: 1, error_code: null } as any;
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(legacy ? { ...deliveryFixture(), email_recipients: null } : operationFixture('succeeded')));
    if (options.method === 'POST') {
      const body = JSON.parse(options.body as string);
      return Promise.resolve(response({ ...deliveryFixture('succeeded', 'accepted', 'not_requested'),
        request_id: (options.headers as Record<string, string>)['Idempotency-Key'], email_recipients: body.email_recipients,
        deliveries: { email: { status: 'accepted', attempts: 1, error_code: null }, lark: { status: 'not_requested', attempts: 0, error_code: null } } }));
    }
    return Promise.resolve(response(preview));
  });
  setup(fetchMock); await screen.findByRole('heading', { name: '示例研发团队' }); return fetchMock;
}

test('email_selection_requires_explicit_recipient_and_confirmation', async () => {
  const fetchMock = await setupRecipients();
  expect(screen.getByRole('checkbox', { name: 'mentor@example.com' })).not.toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'member@example.com' })).not.toBeChecked();
  expect(screen.getByText('请选择至少一位邮件收件人')).toBeVisible();
  expect(screen.getByRole('button', { name: '推送日报' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '飞书' }));
  fireEvent.click(screen.getByRole('checkbox', { name: 'mentor@example.com' }));
  fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText('mentor@example.com')).toBeVisible();
  expect(within(dialog).queryByText('member@example.com')).not.toBeInTheDocument();
  expect(within(dialog).getByText('再次推送可能产生重复邮件')).toBeVisible();
  fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
  expect(fetchMock.mock.calls.filter(call => call[1].method === 'POST')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: '推送日报' })); fireEvent.click(screen.getByRole('button', { name: '确认推送' }));
  await screen.findByText('所选渠道已受理，请核对实际收件');
  const posts = fetchMock.mock.calls.filter(call => call[1].method === 'POST');
  expect(posts).toHaveLength(1); expect(JSON.parse(posts[0][1].body as string)).toMatchObject({ channels: ['email'], email_recipients: ['mentor@example.com'] });
  expect(within(screen.getByRole('region', { name: '推送执行结果' })).getByText(/本次邮件收件人：mentor@example.com/)).toBeVisible();
});

test.each(['accepted', 'unknown', 'partial_failure'])('repeatable_email_%s_requires_new_explicit_confirmation', async previous => {
  const fetchMock = await setupRecipients(previous);
  expect(screen.getByRole('checkbox', { name: '邮件' })).toBeEnabled();
  fireEvent.click(screen.getByRole('checkbox', { name: 'mentor@example.com' }));
  fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  expect(within(screen.getByRole('dialog')).getByText('再次推送可能产生重复邮件')).toBeVisible();
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});

test('legacy_target_is_not_inferred_from_current_preview', async () => {
  await setupRecipients(null, true);
  expect(screen.getByText('历史记录未记录具体收件人')).toBeVisible();
});

test.each(['报告日期', '操作令牌', '预览日报'])('changing_%s_invalidates_recipient_confirmation', async field => {
  const fetchMock = await setupRecipients();
  fireEvent.click(screen.getByRole('checkbox', { name: 'mentor@example.com' })); fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  await screen.findByRole('dialog');
  if (field === '预览日报') fireEvent.click(screen.getByRole('button', { name: field }));
  else fireEvent.change(screen.getByLabelText(field), { target: { value: field === '报告日期' ? '2026-09-24' : 'changed-token' } });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  if (field === '预览日报') {
    await screen.findByRole('checkbox', { name: 'mentor@example.com' });
    expect(screen.getByRole('checkbox', { name: 'mentor@example.com' })).not.toBeChecked();
  }
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});


test('lost_delivery_response_keeps_confirmed_recipient_snapshot_on_explicit_original_retry', async () => {
  const posts: { key: string; body: string }[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(operationFixture('succeeded')));
    if (url.includes('/by-key/')) return Promise.resolve(response({ error: { code: 'operation_not_found' } }, 404));
    if (options.method === 'POST') {
      posts.push({ key: (options.headers as Record<string, string>)['Idempotency-Key'], body: options.body as string });
      return posts.length === 1 ? Promise.reject(new TypeError('synthetic loss')) : Promise.resolve(response({ ...deliveryFixture(),
        request_id: posts[0].key, email_recipients: ['mentor@example.com'] }));
    }
    return Promise.resolve(response(recipientPreview()));
  });
  setup(fetchMock); await screen.findByRole('checkbox', { name: 'mentor@example.com' });
  fireEvent.click(screen.getByRole('checkbox', { name: 'mentor@example.com' })); fireEvent.click(screen.getByRole('checkbox', { name: '飞书' }));
  fireEvent.click(screen.getByRole('button', { name: '推送日报' })); fireEvent.click(screen.getByRole('button', { name: '确认推送' }));
  await screen.findByText('执行结果尚未确认'); expect(posts).toHaveLength(1);
  // Later edits may not change what an explicit original-request retry submits.
  fireEvent.click(screen.getByRole('checkbox', { name: 'member@example.com' }));
  expect(screen.getByRole('button', { name: '推送日报' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '重试原请求' }));
  await screen.findByText('所选渠道已受理，请核对实际收件');
  expect(posts).toHaveLength(2); expect(posts[1]).toEqual(posts[0]);
  expect(JSON.parse(posts[1].body).email_recipients).toEqual(['mentor@example.com']);
});

test('email_selection_lark_only_sends_empty_address_list', async () => {
  const posts: Record<string, unknown>[] = [];
  const fetchMock = vi.fn().mockImplementation((url: string, options: RequestInit) => {
    if (url.endsWith('/current')) return Promise.resolve(response(operationFixture('succeeded')));
    if (options.method === 'POST') {
      posts.push(JSON.parse(options.body as string));
      return Promise.resolve(response({ ...deliveryFixture(), request_id: (options.headers as Record<string, string>)['Idempotency-Key'], email_recipients: [] }));
    }
    return Promise.resolve(response(recipientPreview()));
  }); setup(fetchMock); await screen.findByRole('checkbox', { name: 'mentor@example.com' });
  fireEvent.click(screen.getByRole('checkbox', { name: '邮件' })); fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  const dialog = screen.getByRole('dialog'); expect(within(dialog).queryByText('mentor@example.com')).not.toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button', { name: '确认推送' })); await screen.findByText('所选渠道已受理，请核对实际收件');
  expect(posts).toEqual([{ report_date: '2026-09-25', report_revision: 'a'.repeat(64), channels: ['lark'], email_recipients: [] }]);
});

test.each(['accepted', 'partial_failure', 'unknown', 'pending'])('mixed_repeatable_email_and_blocked_lark_%s_never_sends', async status => {
  const preview = recipientPreview(); preview.targets.lark.previous = { status, attempts: 1, error_code: null } as any;
  const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(response(url.endsWith('/current') ? operationFixture('succeeded') : preview)));
  setup(fetchMock); await screen.findByRole('checkbox', { name: 'mentor@example.com' });
  const lark = screen.getByRole('checkbox', { name: '飞书' });
  expect(lark).toBeDisabled(); expect(lark).not.toBeChecked();
  fireEvent.click(screen.getByRole('checkbox', { name: 'mentor@example.com' }));
  fireEvent.click(screen.getByRole('button', { name: '推送日报' }));
  expect(within(screen.getByRole('dialog')).queryByText('配置的日报群')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '取消' }));
  expect(fetchMock.mock.calls.every(call => call[1].method === 'GET')).toBe(true);
});


test('email_selection_count_explains_exactly_how_many_addresses_will_receive', async () => {
  await setupRecipients();
  expect(screen.getByText('已选择 0 位邮件收件人')).toBeVisible();
  fireEvent.click(screen.getByRole('checkbox', { name: 'mentor@example.com' }));
  expect(screen.getByText('已选择 1 位邮件收件人')).toBeVisible();
  fireEvent.click(screen.getByRole('checkbox', { name: 'member@example.com' }));
  expect(screen.getByText('已选择 2 位邮件收件人')).toBeVisible();
});
