import { useEffect, useRef, useState } from 'react';
import { validDate } from './api';
import { deliverReport, generateReport, getCurrentOperation, getOperation, getOperationByKey, getPreview, OperationError } from './operations';
import type { OperationView, PreviewView } from './operations';

type Channel = 'email' | 'lark';
type PendingRequest = { kind: 'generation'; key: string; date: string } | { kind: 'delivery'; key: string; date: string; revision: string; channels: Channel[] };
type Confirmation = { date: string; revision: string; channels: Channel[]; targets: string[] };
type Props = { date: string; onPreview: (value: PreviewView | null) => void; preview: PreviewView | null };
export function OperationPanel({ date, onPreview, preview }: Props) {
  const [token, setToken] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [operation, setOperation] = useState<OperationView | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [canRetry, setCanRetry] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const work = useRef<{ id: number; controller?: AbortController; timer?: ReturnType<typeof setTimeout>; deadline?: ReturnType<typeof setTimeout> }>({ id: 0 });
  const locked = useRef(false);
  const pending = useRef<PendingRequest | null>(null);
  function stop() {
    work.current.id++; work.current.controller?.abort(); clearTimeout(work.current.timer); clearTimeout(work.current.deadline);
  }
  function begin() {
    stop(); const controller = new AbortController(); work.current.controller = controller;
    return { id: work.current.id, signal: controller.signal };
  }
  useEffect(() => { stop(); setBusy(false); onPreview(null); }, [date, onPreview]);
  useEffect(() => () => stop(), []);
  function blocked(channel: Channel) {
    return !preview?.targets[channel].enabled || ['accepted', 'partial_failure', 'unknown', 'pending'].includes(preview.targets[channel].previous?.status || '');
  }
  useEffect(() => {
    setConfirmation(null);
    setChannels(preview ? (['email', 'lark'] as Channel[]).filter(channel => !blocked(channel)) : []);
  }, [preview]);
  useEffect(() => { if (confirmation) dialog.current?.showModal(); }, [confirmation]);
  function failure(error: unknown) {
    if (error instanceof OperationError && error.code === 'operation_unauthorized') {
      setToken(''); setAuthenticated(false); setBusy(false); setConfirmation(null); onPreview(null); stop();
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
    const deliveryTexts = { succeeded: '所选渠道已受理，请核对实际收件', partial_failure: '部分渠道受理失败，请核对渠道结果',
      failed: '所选渠道明确拒绝，可核对后仅重试失败渠道', skipped: '该日期为非工作日，已跳过',
      unknown: '推送结果未知，请先核实，不能重复推送', interrupted: '操作已中断，未自动重试' };
    setMessage(value.kind === 'generation' ? texts[value.status] : deliveryTexts[value.status]);
    if (value.report_revision && value.report_date === selectedDate) {
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
    await submitRequest({ kind: 'generation', key: crypto.randomUUID(), date });
  }
  async function submitRequest(request: PendingRequest) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setCanRetry(false);
    if (request.kind === 'generation') onPreview(null);
    const ticket = begin(); pending.current = request;
    try {
      const accepted = request.kind === 'generation' ? await generateReport(request.date, token, request.key, ticket.signal)
        : await deliverReport(request.date, request.revision, request.channels, token, request.key, ticket.signal);
      await show(accepted, ticket, date);
    } catch (error) {
      if (ticket.id !== work.current.id) return;
      if (error instanceof OperationError && !['network_error', 'invalid_response', 'operation_storage_failed', 'internal_error'].includes(error.code)) {
        pending.current = null; failure(error);
        if (error.code === 'report_revision_changed' || error.code === 'delivery_not_repeatable') onPreview(null);
      } else {
        try { await show(await getOperationByKey(request.key, token, ticket.signal), ticket, date); }
        catch (lookupError) { if (ticket.id === work.current.id) { failure(lookupError); setCanRetry(lookupError instanceof OperationError && lookupError.code === 'operation_not_found'); setMessage('执行结果尚未确认'); } }
      }
    } finally { locked.current = false; if (ticket.id === work.current.id) setBusy(false); }
  }
  async function queryResult() {
    const ticket = begin(); setBusy(true); setCanRetry(false);
    try {
      const result = pending.current ? await getOperationByKey(pending.current.key, token, ticket.signal)
        : operation ? await getOperation(operation.operation_id, token, ticket.signal) : await getCurrentOperation(token, ticket.signal);
      await show(result, ticket, date);
    } catch (error) { if (ticket.id === work.current.id) { failure(error); setCanRetry(!!pending.current && error instanceof OperationError && error.code === 'operation_not_found'); } }
    finally { if (ticket.id === work.current.id) setBusy(false); }
  }
  async function previewReport() {
    const ticket = begin(); setBusy(true); onPreview(null);
    try {
      const value = await getPreview(date, token, ticket.signal);
      if (ticket.id === work.current.id) onPreview(value);
    } catch (error) { if (ticket.id === work.current.id) failure(error); }
    finally { if (ticket.id === work.current.id) setBusy(false); }
  }
  function confirmDelivery() {
    if (!confirmation || !preview || confirmation.date !== date || confirmation.revision !== preview.report_revision || !authenticated || locked.current) return;
    const request: PendingRequest = { kind: 'delivery', key: crypto.randomUUID(), date: confirmation.date, revision: confirmation.revision, channels: confirmation.channels };
    setConfirmation(null); void submitRequest(request);
  }
  const outcomeText = { not_requested: '本次未选择', pending: '结果待确认', accepted: '服务商已受理', rejected: '明确拒绝，可单独重提',
    partial_failure: '部分受理，不能整渠道重发', unknown: '结果未知，请核实，不能重发' };
  return <section className="query-card operation-panel" aria-label="日报操作">
    <label htmlFor="operation-token">操作令牌</label>
    <input id="operation-token" className="input" type="password" autoComplete="off" value={token}
      onChange={event => { stop(); setToken(event.target.value); setAuthenticated(false); setBusy(false); setConfirmation(null); }} />
    <button type="button" className="btn btn-accent-outline" disabled={!token || busy} onClick={() => void authenticate()}>验证令牌</button>
    <button type="button" className="btn btn-primary" disabled={!authenticated || !validDate(date) || busy || operation?.status === 'running' || !!pending.current}
      onClick={() => void generate()}>采集并生成</button>
    {authenticated && <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void queryResult()}>查询执行结果</button>}
    {authenticated && canRetry && pending.current && <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void submitRequest(pending.current!)}>重试原请求</button>}
    {authenticated && <button type="button" className="btn btn-accent-outline" disabled={!validDate(date) || busy || operation?.status === 'running'} onClick={() => void previewReport()}>预览日报</button>}
    {authenticated && preview && <div className="delivery-options">
      <p>预览版本：<code>{preview.report_revision}</code></p>
      {(['email', 'lark'] as Channel[]).map(channel => <div key={channel}>
        <label><input type="checkbox" aria-label={channel === 'email' ? '邮件' : '飞书'} checked={channels.includes(channel)} disabled={busy || blocked(channel)}
          onChange={event => setChannels(current => event.target.checked ? [...current, channel].sort() : current.filter(value => value !== channel))} />{preview.targets[channel].label}</label>
        <p>{channel === 'email' ? '邮件' : '飞书'}：{preview.targets[channel].previous ? outcomeText[preview.targets[channel].previous.status] : '无本轮推送记录'}</p>
      </div>)}
      <button type="button" className="btn btn-primary" disabled={busy || !channels.length || operation?.status === 'running' || !!pending.current}
        onClick={() => setConfirmation({ date: preview.report.report_date, revision: preview.report_revision, channels: [...channels], targets: channels.map(channel => preview.targets[channel].label) })}>推送日报</button>
    </div>}
    {confirmation && authenticated && preview && confirmation.date === date && confirmation.revision === preview.report_revision &&
      <dialog ref={dialog} className="confirm-dialog" aria-labelledby="delivery-title" onCancel={event => { event.preventDefault(); setConfirmation(null); }}>
        <h2 id="delivery-title">确认推送日报</h2><p>{confirmation.date}</p><code>{confirmation.revision}</code>
        <ul>{confirmation.targets.map(target => <li key={target}>{target}</li>)}</ul>
        <p>仅推送已预览内容。服务商受理后仍需核对实际收件。</p>
        <button type="button" className="btn btn-accent-outline" autoFocus onClick={() => setConfirmation(null)}>取消</button>
        <button type="button" className="btn btn-primary" onClick={confirmDelivery}>确认推送</button>
      </dialog>}
    {operation && operation.report_date !== date && <p>正在查看 {operation.report_date} 的操作结果</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
