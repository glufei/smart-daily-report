import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { vi, test, expect } from 'vitest';
import App from './App';
import { reportFixture } from './test/fixture';

function response(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
function select(date = '2026-09-25') { fireEvent.change(screen.getByLabelText('报告日期'), { target: { value: date } }); }
function query() { fireEvent.click(screen.getByRole('button', { name: '查看日报' })); }
function setup(fetchMock: ReturnType<typeof vi.fn>) { vi.stubGlobal('fetch', fetchMock); render(<App />); select(); }

test('viewing saved history preserves every member and the distinction between empty records and failure', async () => {
  const report = reportFixture();
  report.source_status.lark_tasks = 'failure'; report.members[0].tasks = [];
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.getByText(/UTC\+08:00/)).toBeInTheDocument();
  for (const name of ['示例成员甲', '示例成员乙']) {
    const member = screen.getByRole('article', { name });
    expect(within(member).getByRole('heading', { name, level: 3 })).toBeInTheDocument();
    expect(within(member).getAllByRole('heading', { level: 4 }).map(el => el.textContent)).toEqual(['今日总结', 'GitHub｜代码提交', '飞书｜任务与工作消息']);
    expect(within(member).getByText('数据获取失败')).toBeInTheDocument();
  }
  expect(within(screen.getByRole('article', { name: '示例成员乙' })).getAllByText('今日无记录')).toHaveLength(2);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'GET', cache: 'no-store', credentials: 'omit' });
});

test('shows the shared 高畅智能日报 brand in the webpage masthead', () => {
  vi.stubGlobal('fetch', vi.fn());
  render(<App />);
  expect(screen.getByRole('heading', { name: '高畅智能日报', level: 1 })).toBeInTheDocument();
});

test('shows a deterministic summary before each member’s source details', async () => {
  const report = reportFixture();
  const secondMember = report.members[1];
  secondMember.commits = []; secondMember.tasks = []; secondMember.messages = [];
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });

  const first = within(screen.getByRole('article', { name: '示例成员甲' }));
  const summary = first.getByRole('region', { name: '今日总结' });
  expect(within(summary).getByText('代码提交：1 条')).toBeInTheDocument();
  expect(within(summary).getByText('已完成任务：1 条')).toBeInTheDocument();
  expect(within(summary).getByText('协作沟通：1 条')).toBeInTheDocument();
  expect(first.getAllByRole('heading', { level: 4 }).map(el => el.textContent)).toEqual([
    '今日总结', 'GitHub｜代码提交', '飞书｜任务与工作消息',
  ]);
  expect(first.getAllByRole('heading', { level: 5 }).map(el => el.textContent)).toEqual([
    '提交明细', '任务进展', '工作消息',
  ]);

  const second = within(screen.getByRole('article', { name: '示例成员乙' }));
  const emptySummary = second.getByRole('region', { name: '今日总结' });
  expect(within(emptySummary).getByText('代码提交：0 条')).toBeInTheDocument();
  expect(within(emptySummary).getByText('已完成任务：0 条')).toBeInTheDocument();
  expect(within(emptySummary).getByText('协作沟通：0 条')).toBeInTheDocument();
});

test('single-member report omits the repeated member heading while keeping the summary first', async () => {
  const report = reportFixture();
  report.team_name = '示例成员甲';
  report.members = report.members.slice(0, 1);
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByText('2026-09-25', { exact: true });

  const member = within(screen.getByRole('article', { name: '示例成员甲' }));
  expect(member.queryByRole('heading', { name: '示例成员甲' })).not.toBeInTheDocument();
  expect(member.getByRole('region', { name: '今日总结' })).toBeInTheDocument();
  expect(member.getAllByRole('heading').map(heading => heading.textContent)).toEqual([
    '今日总结', 'GitHub｜代码提交', '提交明细', '飞书｜任务与工作消息', '任务进展', '工作消息',
  ]);
});

test('separates GitHub from Feishu and labels summaries as automatic', async () => {
  const report = reportFixture();
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  const member = screen.getByRole('article', { name: '示例成员甲' });
  expect(within(member).getByText(/系统自动统计/)).toBeInTheDocument();
  expect(within(member).getByRole('region', { name: 'GitHub｜代码提交' })).toBeInTheDocument();
  const feishu = within(member).getByRole('region', { name: '飞书｜任务与工作消息' });
  expect(within(feishu).getByRole('heading', { name: '任务进展' })).toBeInTheDocument();
  expect(within(feishu).getByRole('heading', { name: '工作消息' })).toBeInTheDocument();
  expect(within(feishu).getByText('完成页面契约评审（已完成）')).toBeInTheDocument();
  expect(within(feishu).getByText('日报：已完成只读页面原型')).toBeInTheDocument();
  expect(screen.getByText(/本日报由系统自动生成/)).toBeInTheDocument();
});

test('renders generated time in the timezone returned by the API', async () => {
  const report = reportFixture();
  report.generated_at = '2026-09-25T18:00:00+08:00';
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.getByText('2026-09-25 18:00:00（UTC+08:00）')).toBeInTheDocument();
});

test('summary reports failed source counts as unknown instead of zero', async () => {
  const report = reportFixture();
  report.source_status.github_commits = 'failure'; report.members[0].commits = [];
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  const summary = within(screen.getByRole('article', { name: '示例成员甲' })).getByRole('region', { name: '今日总结' });
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

test('external content is readable text and unsafe links never become executable elements', async () => {
  const report = reportFixture(); const attack = '<img src=x onerror="window.attack=1">';
  report.members[0].commits[0].message = attack; report.members[0].commits[0].url = 'javascript:alert(1)';
  report.members[0].tasks[0].url = 'data:text/html,attack';
  const fetchMock = vi.fn().mockResolvedValue(response(report)); setup(fetchMock); query();
  await screen.findByRole('heading', { name: '示例研发团队' });
  expect(screen.getByText(attack, { exact: false })).toBeInTheDocument(); expect(document.querySelector('img')).toBeNull();
  expect(screen.queryAllByRole('link')).toHaveLength(0);
});
