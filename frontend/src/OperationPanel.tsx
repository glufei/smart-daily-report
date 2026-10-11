import { useEffect, useRef, useState } from 'react';
import { validDate } from './api';
import { deliverReport, generateReport, getCurrentOperation, getOperation, getOperationByKey, getPreview, OperationError } from './operations';
import type { OperationView, PreviewView } from './operations';

type Channel = 'email' | 'lark';
type PendingRequest = { kind: 'generation'; key: string; date: string } | { kind: 'delivery'; key: string; date: string; revision: string; channels: Channel[]; emailRecipients: string[] };
type Confirmation = { date: string; revision: string; channels: Channel[]; targets: string[]; emailRecipients: string[] };
type Props = { date: string; onPreview: (value: PreviewView | null, focus?: boolean) => void; preview: PreviewView | null };
type ActionFeedback = { kind: 'query' | 'preview'; pending: boolean; text: string; completedAt?: string; failed?: boolean };
export function OperationPanel({ date, onPreview, preview }: Props) {
  const [token, setToken] = useState('');
  const [authenticated, setAuthenticated] = useState(false);
  const [operation, setOperation] = useState<OperationView | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionFeedback, setActionFeedback] = useState<ActionFeedback | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [emailRecipients, setEmailRecipients] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const tokenInput = useRef<HTMLInputElement>(null);
  const work = useRef<{ id: number; controller?: AbortController; timer?: ReturnType<typeof setTimeout>; deadline?: ReturnType<typeof setTimeout>; actionTimer?: ReturnType<typeof setTimeout> }>({ id: 0 });
  const locked = useRef(false);
  const pending = useRef<PendingRequest | null>(null);
  function stop() {
    work.current.id++; work.current.controller?.abort(); clearTimeout(work.current.timer); clearTimeout(work.current.deadline); clearTimeout(work.current.actionTimer);
  }
  function begin() {
    stop(); setActionFeedback(null); const controller = new AbortController(); work.current.controller = controller;
    return { id: work.current.id, signal: controller.signal };
  }
  useEffect(() => { stop(); setBusy(false); setActionFeedback(null); onPreview(null); }, [date, onPreview]);
  useEffect(() => () => stop(), []);
  function blocked(channel: Channel) {
    return !preview?.targets[channel].enabled || (channel === 'lark' && ['accepted', 'partial_failure', 'unknown', 'pending'].includes(preview.targets[channel].previous?.status || ''));
  }
  useEffect(() => {
    setConfirmation(null); setEmailRecipients([]);
    setChannels(preview ? (['email', 'lark'] as Channel[]).filter(channel => !blocked(channel)) : []);
  }, [preview]);
  useEffect(() => { if (confirmation) dialog.current?.showModal(); }, [confirmation]);
  function failure(error: unknown) {
    if (error instanceof OperationError && error.code === 'operation_unauthorized') {
      setToken(''); setAuthenticated(false); setBusy(false); setActionFeedback(null); setConfirmation(null); onPreview(null); stop();
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
      unknown: '推送结果未知，请先核实；未自动重发', interrupted: '操作已中断，未自动重试' };
    setMessage(value.kind === 'generation' ? texts[value.status] : deliveryTexts[value.status]);
    if (value.report_revision && value.report_date === selectedDate) {
      try {
        const preview = await getPreview(selectedDate, token, ticket.signal);
        if (ticket.id === work.current.id && preview.report.report_date === selectedDate) {
          if (preview.report_revision === value.report_revision) onPreview(preview);
          else {
            onPreview(null);
            setMessage(`${value.kind === 'generation' ? texts[value.status] : deliveryTexts[value.status]}。日报已更新，请重新预览；执行结果仍属于原版本。`);
          }
        }
      } catch (error) { if (ticket.id === work.current.id) failure(error); }
    }
  }
  async function authenticate() {
    if (!token.trim()) { setMessage('请输入操作令牌'); tokenInput.current?.focus(); return; }
    const ticket = begin(); setBusy(true); setCanRetry(false);
    try {
      const current = pending.current ? await getOperationByKey(pending.current.key, token, ticket.signal)
        : await getCurrentOperation(token, ticket.signal);
      if (ticket.id !== work.current.id) return;
      setAuthenticated(true); await show(current, ticket, date);
    } catch (error) {
      if (ticket.id === work.current.id) {
        failure(error);
        if (pending.current && error instanceof OperationError && error.code === 'operation_not_found') {
          setAuthenticated(true); setCanRetry(true);
        }
      }
    }
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
        : await deliverReport(request.date, request.revision, request.channels, request.emailRecipients, token, request.key, ticket.signal);
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
  function startAction(kind: 'query' | 'preview', ticket: ReturnType<typeof begin>) {
    setMessage('');
    setActionFeedback({ kind, pending: true, text: kind === 'query' ? '正在查询执行结果…' : '正在加载日报预览…' });
    work.current.actionTimer = setTimeout(() => {
      if (ticket.id !== work.current.id) return;
      stop(); setBusy(false);
      setActionFeedback({ kind, pending: false, failed: true, text: `请求超时，请重新${kind === 'query' ? '查询执行结果' : '预览日报'}。` });
    }, 10000);
  }
  async function queryResult() {
    const ticket = begin(); setBusy(true); setCanRetry(false); startAction('query', ticket);
    try {
      const result = pending.current ? await getOperationByKey(pending.current.key, token, ticket.signal)
        : operation ? await getOperation(operation.operation_id, token, ticket.signal) : await getCurrentOperation(token, ticket.signal);
      if (ticket.id !== work.current.id) return;
      if (result) await show(result, ticket, date);
      else { setOperation(null); setMessage(''); }
      if (ticket.id !== work.current.id) return;
      const states = { running: '执行中', succeeded: '执行成功', partial_failure: '部分失败', failed: '执行失败', skipped: '已跳过', unknown: '结果待核实', interrupted: '已中断' };
      setActionFeedback({ kind: 'query', pending: false, completedAt: new Date().toISOString(),
        text: result ? `执行结果查询完成。操作：${result.kind === 'generation' ? '生成日报' : '推送日报'} · ${result.report_date} · ${states[result.status]}；服务器更新时间：${new Date(result.updated_at).toLocaleString()}。` : '暂无执行记录' });
    } catch (error) {
      if (ticket.id === work.current.id) {
        setActionFeedback({ kind: 'query', pending: false, failed: true, text: '执行结果查询失败，请查看错误提示。' });
        failure(error); setCanRetry(!!pending.current && error instanceof OperationError && error.code === 'operation_not_found');
      }
    } finally { if (ticket.id === work.current.id) { clearTimeout(work.current.actionTimer); setBusy(false); } }
  }
  async function previewReport() {
    const ticket = begin(); setBusy(true); onPreview(null); startAction('preview', ticket);
    try {
      const value = await getPreview(date, token, ticket.signal);
      if (ticket.id === work.current.id) {
        onPreview(value, true);
        setActionFeedback({ kind: 'preview', pending: false, text: `已加载 ${value.report.report_date} 日报预览，请核对下方正文。` });
      }
    } catch (error) {
      if (ticket.id === work.current.id) {
        setActionFeedback({ kind: 'preview', pending: false, failed: true, text: '日报预览失败，请查看错误提示。' }); failure(error);
      }
    } finally { if (ticket.id === work.current.id) { clearTimeout(work.current.actionTimer); setBusy(false); } }
  }
  function confirmDelivery() {
    if (!confirmation || !preview || confirmation.date !== date || confirmation.revision !== preview.report_revision || !authenticated || locked.current) return;
    const request: PendingRequest = { kind: 'delivery', key: crypto.randomUUID(), date: confirmation.date, revision: confirmation.revision, channels: confirmation.channels, emailRecipients: [...confirmation.emailRecipients] };
    setConfirmation(null); void submitRequest(request);
  }
  const outcomeText = { not_requested: '本次未选择', pending: '结果待确认', accepted: '服务商已受理', rejected: '明确拒绝，可单独重提',
    partial_failure: '部分受理，请先核实实际收件', unknown: '结果未知，请先核实实际收件' };
  return <section className="query-card operation-panel" aria-label="日报操作">
    <label htmlFor="operation-token">操作令牌</label>
    <input ref={tokenInput} id="operation-token" className="input" type="password" autoComplete="off" value={token}
      aria-describedby={!authenticated ? 'operation-token-hint' : undefined}
      onChange={event => { stop(); setToken(event.target.value); setAuthenticated(false); setBusy(false); setActionFeedback(null); setConfirmation(null); onPreview(null); if (message === '请输入操作令牌') setMessage(''); }} />
    <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void authenticate()}>验证令牌</button>
    <button type="button" className="btn btn-primary" disabled={!authenticated || !validDate(date) || busy || operation?.status === 'running' || !!pending.current}
      aria-describedby={!authenticated ? 'operation-token-hint' : undefined}
      onClick={() => void generate()}>采集并生成</button>
    {!authenticated && <p id="operation-token-hint" className="query-hint">请先输入并验证操作令牌，验证成功后才能采集并生成。</p>}
    {authenticated && <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void queryResult()}>{actionFeedback?.kind === 'query' && actionFeedback.pending ? '正在查询执行结果…' : '查询执行结果'}</button>}
    {authenticated && canRetry && pending.current && <button type="button" className="btn btn-accent-outline" disabled={busy} onClick={() => void submitRequest(pending.current!)}>重试原请求</button>}
    {authenticated && <button type="button" className="btn btn-accent-outline" disabled={!validDate(date) || busy || operation?.status === 'running'} onClick={() => void previewReport()}>{actionFeedback?.kind === 'preview' && actionFeedback.pending ? '正在加载日报预览…' : '预览日报'}</button>}
    {actionFeedback && <div className="operation-feedback" role={actionFeedback.failed ? 'alert' : 'status'} aria-busy={actionFeedback.pending}>
      <p>{actionFeedback.text}</p>
      {actionFeedback.completedAt && <p>本次查询时间：<time aria-label="本次查询时间" dateTime={actionFeedback.completedAt}>{new Date(actionFeedback.completedAt).toLocaleString()}（{Intl.DateTimeFormat().resolvedOptions().timeZone}）</time></p>}
    </div>}
    {authenticated && preview && <div className="delivery-options">
      <p>预览版本：<code>{preview.report_revision}</code></p>
      {(['email', 'lark'] as Channel[]).map(channel => <div key={channel}>
        <label><input type="checkbox" aria-label={channel === 'email' ? '邮件' : '飞书'} checked={channels.includes(channel)} disabled={busy || blocked(channel)}
          onChange={event => { setConfirmation(null); setChannels(current => event.target.checked ? [...current, channel].sort() : current.filter(value => value !== channel)); if (channel === "email") setEmailRecipients([]); }} />{preview.targets[channel].label}</label>
        <p>{channel === 'email' ? '邮件' : '飞书'}：{preview.targets[channel].previous ? outcomeText[preview.targets[channel].previous.status] : '无本轮推送记录'}</p>
      </div>)}
      {channels.includes('email') && <fieldset disabled={busy}>
        <legend>邮件收件人（仅发送给勾选的邮箱）</legend>
        {preview.targets.email.recipients.map(address => <label key={address}><input type="checkbox" aria-label={address}
          checked={emailRecipients.includes(address)} onChange={event => { setConfirmation(null); setEmailRecipients(current => event.target.checked ? [...current, address].sort() : current.filter(value => value !== address)); }} />{address}</label>)}
        <p aria-live="polite">已选择 {emailRecipients.length} 位邮件收件人</p>
        {!emailRecipients.length && <p id="email-recipient-hint">请选择至少一位邮件收件人</p>}
      </fieldset>}
      <button type="button" className="btn btn-primary" aria-describedby={channels.includes('email') && !emailRecipients.length ? 'email-recipient-hint' : undefined}
        disabled={busy || !channels.length || (channels.includes('email') && !emailRecipients.length) || channels.some(blocked) || operation?.status === 'running' || !!pending.current}
        onClick={() => setConfirmation({ date: preview.report.report_date, revision: preview.report_revision, channels: [...channels], emailRecipients: channels.includes('email') ? [...emailRecipients] : [],
          targets: channels.flatMap(channel => channel === 'email' ? emailRecipients : [preview.targets[channel].label]) })}>推送日报</button>
    </div>}
    {authenticated && operation?.kind === 'delivery' && <section className="delivery-options" aria-label="推送执行结果">
      <h3>推送执行结果</h3>
      <p>执行日期：{operation.report_date}</p>
      <p>执行版本：<code>{operation.report_revision}</code></p>
      <p>{operation.email_recipients === null ? '历史记录未记录具体收件人' : operation.email_recipients.length ? `本次邮件收件人：${operation.email_recipients.join('、')}` : '本次未选择邮件收件人'}</p>
      {(['email', 'lark'] as Channel[]).map(channel => <p key={channel}>
        本次{channel === 'email' ? '邮件' : '飞书'}结果：{outcomeText[operation.deliveries[channel].status]}
      </p>)}
    </section>}
    {confirmation && authenticated && preview && confirmation.date === date && confirmation.revision === preview.report_revision &&
      <dialog ref={dialog} className="confirm-dialog" aria-labelledby="delivery-title" onCancel={event => { event.preventDefault(); setConfirmation(null); }}>
        <h2 id="delivery-title">确认推送日报</h2><p>{confirmation.date}</p><code>{confirmation.revision}</code>
        <ul>{confirmation.targets.map(target => <li key={target}>{target}</li>)}</ul>
        {confirmation.channels.includes('email') && <p>再次推送可能产生重复邮件</p>}
        <p>仅推送已预览内容。服务商受理后仍需核对实际收件。</p>
        <button type="button" className="btn btn-accent-outline" autoFocus onClick={() => setConfirmation(null)}>取消</button>
        <button type="button" className="btn btn-primary" onClick={confirmDelivery}>确认推送</button>
      </dialog>}
    {operation && operation.report_date !== date && <p>正在查看 {operation.report_date} 的操作结果</p>}
    {message && <p role="status">{message}</p>}
  </section>;
}
