import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import App from './App';
import { reportFixture } from './test/fixture';

function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
function select(date = '2026-09-25') { fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: date } }); }
function query() { fireEvent.click(screen.getByRole('button', { name: '查看日报' })); }
function setup(fetchMock: ReturnType<typeof vi.fn>) { vi.stubGlobal('fetch', fetchMock); render(<App />); select(); }

test('shared webpage keeps useful counts without exposing source details', async () => {
  const report = reportFixture();
  report.members[0].commits[0].message = 'classified-project-marker';
  report.members[0].commits[0].repository = 'classified-project-marker';
  report.members[0].tasks[0].title = 'classified-project-marker';
  report.members[0].messages[0].content = 'classified-project-marker';
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  const member = await screen.findByRole('article', { name: '示例成员甲' });
  expect(within(member).getByText('代码提交：1 条')).toBeInTheDocument();
  expect(within(member).getByText('已完成任务：1 条')).toBeInTheDocument();
  expect(within(member).getByText('协作沟通：1 条')).toBeInTheDocument();
  expect(member).not.toHaveTextContent('classified-project-marker');
  expect(within(member).queryByRole('link')).not.toBeInTheDocument();
});

test('saved history keeps every member and distinguishes zero from source failure', async () => {
  const report = reportFixture();
  report.source_status.lark_tasks = 'failure'; report.members[0].tasks = [];
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  for (const name of ['示例成员甲', '示例成员乙']) {
    const member = within(screen.getByRole('article', { name }));
    expect(member.getByRole('heading', { name: '今日概览' })).toBeInTheDocument();
    expect(member.getByText('已完成任务：获取失败，数量未知')).toBeInTheDocument();
    expect(member.queryByText('已完成任务：0 条')).not.toBeInTheDocument();
  }
  expect(within(screen.getByRole('article', { name: '示例成员乙' })).getByText('代码提交：0 条')).toBeInTheDocument();
  expect(screen.getByText('部分数据源获取失败：任务进展')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store', credentials: 'omit' });
});

test('keeps the webpage brand generic and omits the personal name', () => {
  vi.stubGlobal('fetch', vi.fn());
  render(<App />);
  expect(screen.getByRole('heading', { name: '智能日报', level: 1 })).toBeInTheDocument();
  expect(screen.getByText('智能日报 · 只读查看')).toBeInTheDocument();
  expect(screen.queryByText(/高畅/)).not.toBeInTheDocument();
});

test('single-member report omits the repeated member heading', async () => {
  const report = reportFixture();
  report.team_name = '示例成员甲';
  report.members = report.members.slice(0, 1);
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByText('2026-09-25', { exact: true });
  const member = within(screen.getByRole('article', { name: '示例成员甲' }));
  expect(member.queryByRole('heading', { name: '示例成员甲' })).not.toBeInTheDocument();
  expect(member.getAllByRole('heading').map(heading => heading.textContent)).toEqual(['今日概览']);
});

test('renders only the report generation time in China Standard Time', async () => {
  const report = reportFixture();
  report.generated_at = '2026-09-25T10:00:00Z';
  report.members[0].commits[0].committed_at = '2026-09-25T12:37:19Z';
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.getByText('2026-09-25 18:00:00（中国标准时间，UTC+08:00）')).toHaveAttribute('datetime', '2026-09-25T10:00:00Z');
  expect(screen.queryByText('2026-09-25 20:37:19（中国标准时间，UTC+08:00）')).not.toBeInTheDocument();
});

test('source failure count is unknown rather than zero', async () => {
  const report = reportFixture();
  report.source_status.github_commits = 'failure'; report.members[0].commits = [];
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  const summary = within(screen.getByRole('article', { name: '示例成员甲' })).getByRole('region', { name: '今日概览' });
  expect(within(summary).getByText('代码提交：获取失败，数量未知')).toBeInTheDocument();
  expect(within(summary).queryByText('代码提交：0 条')).not.toBeInTheDocument();
});

test.each([
  [404, 'report_not_found', '该日期尚无日报'], [400, 'invalid_report_date', '日期无效，请使用 YYYY-MM-DD'],
  [500, 'storage_read_failed', '日报读取失败，请稍后重新查询'],
])('HTTP %i must not masquerade as an existing empty report', async (status, code, text) => {
  const fetchMock = vi.fn().mockResolvedValue(response({ error: { code, message: 'private-server-marker' } }, status));
  setup(fetchMock); query(); await screen.findByText(text);
  expect(screen.queryByText('今日无记录')).not.toBeInTheDocument();
  expect(screen.queryByText('private-server-marker')).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test('no selected date does not read history', () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock); render(<App />); query();
  expect(screen.getByText('日期无效，请使用 YYYY-MM-DD')).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each(['invalid-json', 'invalid-schema'])('bad response %s is an error, not fabricated history', async kind => {
  const fetchMock = vi.fn().mockResolvedValue(kind === 'invalid-json' ? new Response('{') : response({ members: [] }));
  setup(fetchMock); query(); await screen.findByText('日报响应格式异常');
  expect(screen.queryByText('今日无记录')).not.toBeInTheDocument(); expect(fetchMock).toHaveBeenCalledTimes(1);
});

test('network failure retries only when the user explicitly asks', async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('private-network-marker')).mockResolvedValueOnce(response(reportFixture()));
  setup(fetchMock); query(); await screen.findByText('无法连接日报服务'); expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: '重新查询' }));
  await screen.findByRole('heading', { name: '示例研发团队' }); expect(fetchMock).toHaveBeenCalledTimes(2);
});

test('ten-second timeout completes even if transport ignores abort and late data cannot replace the error', async () => {
  vi.useFakeTimers(); let resolve!: (response: Response) => void;
  const fetchMock = vi.fn().mockImplementation(() => new Promise<Response>(done => { resolve = done; })); setup(fetchMock); query();
  expect(screen.getByText('正在加载日报…')).toBeInTheDocument();
  await act(() => vi.advanceTimersByTimeAsync(10_000)); expect(screen.getByText('无法连接日报服务')).toBeInTheDocument();
  expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  await act(async () => resolve(response(reportFixture())));
  expect(screen.queryByRole('heading', { name: '示例研发团队' })).not.toBeInTheDocument(); expect(fetchMock).toHaveBeenCalledTimes(1);
});

test('late A cannot overwrite B and selection/failure immediately removes previous content', async () => {
  let resolveA!: (value: Response) => void;
  const reportB = reportFixture('2026-09-26'); reportB.team_name = 'B 日期团队';
  const fetchMock = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { resolveA = resolve; }))
    .mockResolvedValueOnce(response(reportB)).mockRejectedValueOnce(new Error('offline'));
  setup(fetchMock); query(); select('2026-09-26'); query();
  await screen.findByRole('heading', { name: 'B 日期团队' });
  await act(async () => resolveA(response(reportFixture())));
  expect(screen.queryByRole('heading', { name: '示例研发团队' })).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'B 日期团队' })).toBeInTheDocument();
  select('2026-09-27'); expect(screen.queryByRole('heading', { name: 'B 日期团队' })).not.toBeInTheDocument();
  query(); await screen.findByText('无法连接日报服务'); expect(fetchMock).toHaveBeenCalledTimes(3);
});

test('aborted A cannot report an error over active B', async () => {
  const fetchMock = vi.fn().mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
  })).mockResolvedValueOnce(response(reportFixture('2026-09-26')));
  setup(fetchMock); query(); select('2026-09-26'); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('external source content never enters the visible summary', async () => {
  const report = reportFixture(); const attack = '<img src=x onerror="window.attack=1">';
  report.members[0].commits[0].message = attack; report.members[0].commits[0].url = 'javascript:alert(1)';
  report.members[0].tasks[0].url = 'data:text/html,attack';
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.queryByText(attack, { exact: false })).not.toBeInTheDocument(); expect(document.querySelector('img')).toBeNull();
  expect(screen.queryAllByRole('link')).toHaveLength(0);
});
