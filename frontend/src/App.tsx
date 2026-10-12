import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, ReactNode, RefObject } from 'react';
import type { PreviewView } from './operations';
import { OperationPanel } from './OperationPanel';
import { queryReport, safeUrl, validDate } from './api';
import type { QueryResult, Report, SourceStatus } from './api';

type View = { kind: 'initial' } | { kind: 'loading' } | (QueryResult & { date: string });
const sources = [['github_commits', '代码提交'], ['lark_tasks', '任务进展'], ['lark_messages', '协作沟通']] as const;

function RecordLink({ url, children }: { url: string | null; children: ReactNode }) {
  const href = safeUrl(url);
  return href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <>{children}</>;
}
function Section({ title, status, children, empty }: {
  title: string; status: SourceStatus[keyof SourceStatus] | 'disabled' | 'pending'; children: ReactNode; empty: boolean;
}) {
  return <section className="block"><h5 className="block-label">{title}</h5>
    {status === 'disabled' ? <p className="record-empty">未启用</p> : status === 'pending' ? <p>正在采集…</p> : status === 'failure' ? <p className="record-failed">数据获取失败</p>
      : empty ? <p className="record-empty">今日无记录</p> : <ul className="records">{children}</ul>}
  </section>;
}

function formatTimestamp(timestamp: string) {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/.exec(timestamp);
  if (!match) return timestamp;
  const offset = match[3] === 'Z' ? '+00:00' : match[3];
  return `${match[1]} ${match[2]}（UTC${offset}）`;
}

function formatChinaTimestamp(timestamp: string) {
  const parsed = new Date(timestamp);
  if (!Number.isFinite(parsed.getTime())) return timestamp;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(parsed);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}（中国标准时间，UTC+08:00）`;
}

function ReportContent({ report, sources: outcomes, headingRef }: { report: Report; sources?: PreviewView['sources']; headingRef?: RefObject<HTMLHeadingElement | null> }) {
  const status = (key: keyof SourceStatus) => outcomes?.[key]?.status ?? report.source_status[key];
  const summaryValue = (key: keyof SourceStatus, count: number) => {
    const value = status(key);
    if (value === 'failure') return '获取失败，数量未知';
    if (value === 'disabled') return '未启用';
    if (value === 'pending') return '正在采集…';
    return `${count} 条`;
  };
  const failures = sources.filter(([key]) => status(key) === 'failure').map(([, label]) => label);
  return <div className="report">
    {failures.length > 0 && <div className="banner" role="status"><strong>部分数据源获取失败：{failures.join('、')}</strong>
      <p>日报已加载，对应板块显示“数据获取失败”。</p></div>}
    {outcomes === null && <p>来源启用情况未记录</p>}
    <header className="report-head"><h2 ref={headingRef} tabIndex={-1} className="report-team">{report.team_name}</h2>
      <p className="report-origin-note">本日报由系统自动生成，内容依据已配置并成功采集的数据。</p>
      <dl className="report-meta"><div><dt>报告日期</dt><dd>{report.report_date}</dd></div>
        <div><dt>生成时间</dt><dd><time dateTime={report.generated_at}>{formatTimestamp(report.generated_at)}</time></dd></div></dl>
      <ul className="source-status" aria-label="来源状态">{sources.map(([key, label]) => <li key={key}>{label}：{status(key) === 'disabled' ? '未启用' : status(key) === 'pending' ? '正在采集…' : status(key) === 'success' ? '获取成功' : '数据获取失败'}</li>)}</ul>
    </header>
    <div className="members">{report.members.map(member => <article className="member" key={member.member_id} aria-label={member.display_name}>
      {report.members.length > 1 && <h3 className="member-name">{member.display_name}</h3>}<div className="blocks">
        <section className="block member-summary" aria-label="今日总结"><h4 className="block-label">今日总结</h4>
          <p className="summary-note">系统自动统计：仅依据下方成功采集的记录，不作人工编辑或 AI 推断。</p>
          <ul className="summary-list">
            <li>代码提交：{summaryValue('github_commits', member.commits.length)}</li>
            <li>已完成任务：{summaryValue('lark_tasks', member.tasks.length)}</li>
            <li>协作沟通：{summaryValue('lark_messages', member.messages.length)}</li>
          </ul>
        </section>
        <section className="source-group" aria-label="GitHub｜代码提交">
          <h4 className="source-group-title">GitHub｜代码提交</h4>
          <Section title="提交明细" status={status('github_commits')} empty={member.commits.length === 0}>
            {member.commits.map((record, index) => <li key={`${record.record_id}-${index}`}><RecordLink url={record.url}><span className="code">{record.repository}</span>：{record.message}</RecordLink>
              <small><time dateTime={record.committed_at}>{formatChinaTimestamp(record.committed_at)}</time> · +{record.additions} / −{record.deletions} · {record.files_changed} 个文件</small></li>)}
          </Section>
        </section>
        <section className="source-group" aria-label="飞书｜任务与工作消息">
          <h4 className="source-group-title">飞书｜任务与工作消息</h4>
          <Section title="任务进展" status={status('lark_tasks')} empty={member.tasks.length === 0}>
            {member.tasks.map((record, index) => <li key={`${record.record_id}-${index}`}><RecordLink url={record.url}>{record.title}（{record.status === 'completed' ? '已完成' : record.status}）</RecordLink>
              <small>{record.changed_at}{record.status_from !== null && record.status_to !== null ? ` · ${record.status_from} → ${record.status_to}` : ''}</small></li>)}
          </Section>
          <Section title="工作消息" status={status('lark_messages')} empty={member.messages.length === 0}>
            {member.messages.map((record, index) => <li key={`${record.record_id}-${index}`}><RecordLink url={record.url}>{record.content}</RecordLink><small>{record.sent_at}{record.chat_name ? ` · ${record.chat_name}` : ''}</small></li>)}
          </Section>
        </section>
      </div>
    </article>)}</div>
  </div>;
}

export default function App() {
  const [date, setDate] = useState('');
  const [controlPreview, setControlPreview] = useState<PreviewView | null>(null);
  const reportHeading = useRef<HTMLHeadingElement>(null);
  const previewFocus = useRef(false);
  const onPreview = useCallback((value: PreviewView | null, focus = false) => {
    if (!value || value.report.report_date === date) { previewFocus.current = !!value && focus; setControlPreview(value); }
  }, [date]);
  useEffect(() => {
    if (!controlPreview || !previewFocus.current) return;
    previewFocus.current = false;
    reportHeading.current?.focus({ preventScroll: true });
    reportHeading.current?.scrollIntoView?.({ block: 'start', behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }, [controlPreview]);
  const [view, setView] = useState<View>({ kind: 'initial' });
  const request = useRef<{ id: number; controller?: AbortController; timer?: ReturnType<typeof setTimeout> }>({ id: 0 });
  function cancel() {
    request.current.id += 1;
    request.current.controller?.abort();
    clearTimeout(request.current.timer);
  }
  useEffect(() => () => cancel(), []);

  async function query() {
    cancel(); setControlPreview(null);
    if (!validDate(date)) { setView({ kind: 'error', date, message: '日期无效，请使用 YYYY-MM-DD' }); return; }
    const id = request.current.id;
    const controller = new AbortController();
    request.current.controller = controller;
    setView({ kind: 'loading' });
    request.current.timer = setTimeout(() => {
      if (id !== request.current.id) return;
      request.current.id += 1;
      controller.abort();
      setView({ kind: 'error', date, message: '无法连接日报服务' });
    }, 10_000);
    try {
      const result = await queryReport(date, controller.signal);
      if (id === request.current.id) setView({ ...result, date });
    } catch {
      if (id === request.current.id) setView({ kind: 'error', date, message: '无法连接日报服务' });
    } finally {
      if (id === request.current.id) clearTimeout(request.current.timer);
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void query(); }

  return <>
    {![undefined, '', 'readonly', 'operations'].includes(import.meta.env.VITE_API_MODE) && <p role="alert">前端运行模式配置无效</p>}
    <header className="topnav"><div className="container topnav-inner"><div className="brand"><h1 className="logo">智能日报</h1><span className="tag">{import.meta.env.VITE_API_MODE === 'operations' ? '采集与推送' : '只读'}</span></div><span className="topnav-sub">研发团队 · 日报查看</span></div></header>
    <main id="content"><section className="section"><div className="container"><form className="query-card" onSubmit={submit} noValidate>
      <div className="query-bar"><div className="field query-field"><label htmlFor="report-date">报告日期</label>
        <input id="report-date" type="date" className="input" value={date} onChange={event => { cancel(); setControlPreview(null); setDate(event.target.value); setView({ kind: 'initial' }); }} /></div>
        <button type="submit" className="btn btn-primary query-btn">查看日报</button></div>
      <p className="query-hint">选择日期，查看已生成并保存的日报。</p>
    </form></div></section>
    {import.meta.env.VITE_API_MODE === 'operations' && <div className="container"><OperationPanel date={date} onPreview={onPreview} preview={controlPreview} /></div>}
    <section className="result-section" aria-live="polite" aria-busy={view.kind === 'loading'}><div className="container">
      {controlPreview ? <ReportContent report={controlPreview.report} sources={controlPreview.sources} headingRef={reportHeading} /> : view.kind === 'report' ? <ReportContent report={view.report} /> : <div className={`state-card ${view.kind === 'error' ? 'state-card-error' : ''}`} role={view.kind === 'error' ? 'alert' : 'status'}>
        {view.kind === 'initial' && <><span className="state-icon" aria-hidden="true">▦</span><h2>选择日期查看日报</h2><p>请选择报告日期并点击“查看日报”，加载当日的团队日报。</p></>}
        {view.kind === 'loading' && <><div className="spinner" aria-hidden="true" /><p>正在加载日报…</p></>}
        {view.kind === 'missing' && <><span className="state-icon" aria-hidden="true">▦</span><h2>该日期尚无日报</h2><p>所选日期 {view.date} 暂无日报记录，请换一个日期查看。</p></>}
        {view.kind === 'error' && <><span className="state-icon" aria-hidden="true">!</span><h2>查询失败</h2><p>{view.message}</p><button type="button" className="btn btn-accent-outline" onClick={() => void query()}>重新查询</button></>}
      </div>}
    </div></section></main>
    <footer className="pagefoot"><div className="container"><strong>智能日报 · {import.meta.env.VITE_API_MODE === 'operations' ? '预览后确认推送' : '只读查看'}</strong><span className="meta">查看已保存的团队日报</span></div></footer>
  </>;
}
