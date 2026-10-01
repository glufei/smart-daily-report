import { useEffect, useRef, useState } from 'react';
import { validDate } from './api';
import { generateReport, getCurrentOperation, getOperation, getOperationByKey, getPreview, OperationError } from './operations';
import type { OperationView, PreviewView } from './operations';

type Props = { date: string; onPreview: (value: PreviewView | null) => void };
export function OperationPanel({ date, onPreview }: Props) {
  const [token, setToken] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [operation, setOperation] = useState<OperationView | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [canRetry, setCanRetry] = useState(false);
  const work = useRef<{ id: number; controller?: AbortController; timer?: ReturnType<typeof setTimeout>; deadline?: ReturnType<typeof setTimeout> }>({ id: 0 });
  const locked = useRef(false);
  const pending = useRef<{ key: string; date: string } | null>(null);
  function stop() {
    work.current.id++; work.current.controller?.abort(); clearTimeout(work.current.timer); clearTimeout(work.current.deadline);
  }
  function begin() {
    stop(); const controller = new AbortController(); work.current.controller = controller;
    return { id: work.current.id, signal: controller.signal };
  }
  useEffect(() => { stop(); setBusy(false); onPreview(null); }, [date, onPreview]);
  useEffect(() => () => stop(), []);
  function failure(error: unknown) {
    if (error instanceof OperationError && error.code === 'operation_unauthorized') {
      setToken(''); setAuthenticated(false); stop();
    }
    setMessage(error instanceof OperationError ? error.message : '操作请求处理失败');
  }
  async function show(value: OperationView | null, ticket: ReturnType<typeof begin>, selectedDate: string) {
    if (ticket.id !== work.current.id) return;
    setOperation(value);
    if (!value) { setMessage('令牌已验证'); return; }
    if (value.status === 'running') {
      setMessage(value.kind === 'generation' ? '正在生成日报…' : '正在推送日报…');
      work.current.deadline = setTimeout(() => {
        if (ticket.id !== work.current.id) return;
        stop(); setMessage('执行结果尚未确认');
      }, 120000);
      const poll = async () => {
        if (ticket.id !== work.current.id) return;
        try {
          const next = await getOperation(value.operation_id, token, ticket.signal);
          if (ticket.id !== work.current.id) return;
          if (next.status === 'running') work.current.timer = setTimeout(poll, 2000);
          else { clearTimeout(work.current.deadline); await show(next, ticket, selectedDate); }
        } catch (error) { if (ticket.id === work.current.id) failure(error); }
      };
      work.current.timer = setTimeout(poll, 2000); return;
    }
    pending.current = null;
    const texts = { succeeded: '日报生成完成，推送需单独确认', partial_failure: '部分数据源获取失败，请核对预览',
      failed: '日报生成失败', skipped: '该日期为非工作日，已跳过', unknown: '执行结果尚未确认', interrupted: '操作已中断，未自动重试' };
    setMessage(texts[value.status]);
    if (value.report_revision && value.kind === 'generation' && value.report_date === selectedDate) {
      try {
        const preview = await getPreview(selectedDate, token, ticket.signal);
        if (ticket.id === work.current.id && preview.report.report_date === selectedDate) onPreview(preview);
      } catch (error) { if (ticket.id === work.current.id) failure(error); }
    }
  }
  async function authenticate() {
    const ticket = begin(); setBusy(true);
    try {
      const current = await getCurrentOperation(token, ticket.signal);
      if (ticket.id !== work.current.id) return;
      setAuthenticated(true); await show(current, ticket, date);
    } catch (error) { if (ticket.id === work.current.id) failure(error); }
    finally { if (ticket.id === work.current.id) setBusy(false); }
  }
  async function generate() {
    if (locked.current || !authenticated || !validDate(date) || operation?.status === 'running' || pending.current) return;
    await submitRequest({ key: crypto.randomUUID(), date });
  }
  async function submitRequest(request: { key: string; date: string }) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setCanRetry(false); onPreview(null);
    const ticket = begin(); pending.current = request;
    try {
      const accepted = await generateReport(request.date, token, request.key, ticket.signal);
      await show(accepted, ticket, date);
    } catch (error) {
      if (ticket.id !== work.current.id) return;
      if (error instanceof OperationError && !['network_error', 'invalid_response', 'operation_storage_failed', 'internal_error'].includes(error.code)) {
        pending.current = null; failure(error);
      } else {
        try { await show(await getOperationByKey(request.key, token, ticket.signal), ticket, date); }
        catch (lookupError) { if (ticket.id === work.current.id) { failure(lookupError); setCanRetry(lookupError instanceof OperationError && lookupError.code === 'operation_not_found'); setMessage('执行结果尚未确认'); } }
      }
    } finally { locked.current = false; if (ticket.id === work.current.id) setBusy(false); }
  }
  async function queryResult() {
    const ticket = begin(); setBusy(true);
    try {
      const result = pending.current ? await getOperationByKey(pending.current.key, token, ticket.signal)
        : operation ? await getOperation(operation.operation_id, token, ticket.signal) : await getCurrentOperation(token, ticket.signal);
      await show(result, ticket, date);
    } catch (error) { if (ticket.id === work.current.id) failure(error); }
    finally { if (ticket.id === work.current.id) setBusy(false); }
  }
  return <section className="query-card" aria-label="日报操作">
    <label htmlFor="operation-token">操作令牌</label>
    <input id="operation-token" className="input" type="password" autoComplete="off" value={token}
      onChange={event => { stop(); setToken(event.target.value); setAuthenticated(false); setBusy(false); }} />
    <button type="button" className="btn btn-accent-outline" disabled={!token || busy} onClick={() => void authenticate()}>验证令牌</button>
    <button type="button" className="btn btn-primary" disabled={!authenticated || !validDate(date) || busy || operation?.status === 'running' || !!pending.current}
      onClick={() => void generate()}>采集并生成</button>
    {authenticated && <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void queryResult()}>查询执行结果</button>}
    {authenticated && canRetry && pending.current && <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void submitRequest(pending.current!)}>重试原请求</button>}
    {operation && operation.report_date !== date && <p>正在查看 {operation.report_date} 的操作结果</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
