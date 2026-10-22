import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, RefObject } from 'react';
import type { PreviewView } from './operations';
import { OperationPanel } from './OperationPanel';
import { queryReport, validDate } from './api';
import type { QueryResult, Report, SourceStatus } from './api';
import { formatChinaTimestamp } from './time';

type View = { kind: 'initial' } | { kind: 'loading' } | (QueryResult & { date: string });
const sources = [['github_commits', '代码提交'], ['lark_tasks', '任务进展'], ['lark_messages', '协作沟通']] as const;

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
      <p>对应统计项的数量未知，其余成功来源仍可查看。</p></div>}
    {outcomes === null && <p>来源启用情况未记录</p>}
    <header className="report-head"><h2 ref={headingRef} tabIndex={-1} className="report-team">{report.team_name}</h2>
      <p className="report-origin-note">本日报由系统自动生成，只展示汇总统计，不展示工作细节。</p>
      <dl className="report-meta"><div><dt>报告日期</dt><dd>{report.report_date}</dd></div>
        <div><dt>生成时间</dt><dd><time dateTime={report.generated_at}>{formatChinaTimestamp(report.generated_at)}</time></dd></div></dl>
      <ul className="source-status" aria-label="来源状态">{sources.map(([key, label]) => <li key={key} data-status={status(key)}>{label}：{status(key) === 'disabled' ? '未启用' : status(key) === 'pending' ? '正在采集…' : status(key) === 'success' ? '获取成功' : '数据获取失败'}</li>)}</ul>
    </header>
    <div className="members">{report.members.map(member => {
      const counts = [
        { key: 'github_commits' as const, label: '代码提交', count: member.commits.length },
        { key: 'lark_tasks' as const, label: '已完成任务', count: member.tasks.length },
        { key: 'lark_messages' as const, label: '协作沟通', count: member.messages.length },
      ];
      const known = counts.filter(item => status(item.key) === 'success');
      const failed = counts.filter(item => status(item.key) === 'failure').length;
      const maximum = Math.max(0, ...known.map(item => item.count));
      return <article className="member" key={member.member_id} aria-label={member.display_name}>
      {report.members.length > 1 && <h3 className="member-name">{member.display_name}</h3>}<div className="blocks">
        <section className="block member-summary" aria-label="今日概览"><h4 className="block-label">今日概览</h4>
          <p className="summary-note">仅依据成功采集的记录统计；代码提交来自 GitHub，任务与协作沟通来自飞书。</p>
          <p className="summary-total">已获取记录合计：{known.reduce((sum, item) => sum + item.count, 0)} 条</p>
          <p className="summary-note">有记录类别：{known.filter(item => item.count > 0).length} 项</p>
          {failed > 0 && <p className="summary-caveat">{failed} 类来源获取失败，未计入合计</p>}
          {counts.some(item => status(item.key) === 'disabled' || status(item.key) === 'pending') &&
            <p className="summary-caveat">未启用或正在采集的来源未计入合计</p>}
          <ul className="summary-list">
            {counts.map(item => <li key={item.key}>{item.label}：{summaryValue(item.key, item.count)}</li>)}
          </ul>
          <p className="summary-chart-title">记录数量对比</p>
          <ul className="summary-chart" aria-label="记录数量对比">{counts.map(item => <li key={item.key}>
            <span>{item.label}</span><span className="summary-track" aria-hidden="true"><span style={{ width: status(item.key) === 'success' && item.count > 0 && maximum > 0 ? `${Math.max(2, Math.round(item.count / maximum * 100))}%` : '0%' }} /></span>
            <span>{summaryValue(item.key, item.count)}</span>
          </li>)}</ul>
          <p className="summary-note summary-footnote">记录数量仅供了解采集情况，不代表工作量或成果质量。</p>
        </section>
      </div>
    </article>; })}</div>
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
