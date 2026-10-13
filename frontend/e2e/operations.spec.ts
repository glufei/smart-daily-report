import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
const directory = path.resolve('../.runtime/e2e-operations');
const token = 'public-e2e-only-token-not-a-real-secret-123456';
const headers = { Authorization: `Bearer ${token}` };
async function counts() {
  const values = await readFile(path.join(directory, 'deliveries.jsonl'), 'utf8').catch(() => '');
  const channels = values.trim().split('\n').filter(Boolean).map(line => JSON.parse(line).channel);
  return { email: channels.filter(value => value === 'email').length, lark: channels.filter(value => value === 'lark').length };
}
async function scenario(value: Record<string, unknown>) { await writeFile(path.join(directory, 'scenario.json'), JSON.stringify(value)); }
async function authenticate(page: Page) {
  await page.goto('/'); await page.getByLabel('报告日期', { exact: true }).fill('2026-09-25');
  await page.getByLabel('操作令牌', { exact: true }).fill(token); await page.getByRole('button', { name: '验证令牌', exact: true }).click();
  await expect(page.getByRole('button', { name: '采集并生成', exact: true })).toBeEnabled();
}
async function generate(page: Page) {
  await page.getByRole('button', { name: '采集并生成', exact: true }).click();
  await expect(page.getByText('日报生成完成，推送需单独确认', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '联调示例团队' })).toBeVisible();
  await expect(page.locator('.report-meta')).toContainText(/UTC\+08:00/);
  await expect(page.getByRole('button', { name: '推送日报', exact: true })).toBeDisabled();
}
async function selectFixtureRecipient(page: Page) {
  await page.getByRole('checkbox', { name: 'fixture@example.invalid', exact: true }).check();
}
async function confirm(page: Page) {
  await selectFixtureRecipient(page);
  await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: '确认推送', exact: true }).click();
}
async function screenshot(page: Page, project: string, state: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(process.env.DAILY_REPORT_E2E_SCREENSHOT_DIR || '../docs/frontend/screenshots/operation-feedback-email-selection', `${project}-${state}.png`), fullPage: true, animations: 'disabled' });
}
test.beforeEach(async () => scenario({}));

test('generation_preview_confirmation_and_delivery', async ({ page }, info) => {
  const before = await counts(); await authenticate(page); await generate(page);
  expect(await counts()).toEqual(before);
  await expect(page.getByText('代码提交：获取成功')).toBeVisible();
  await expect(page.getByText(/完成任务清单接入（已完成）/)).toBeVisible();
  await expect(page.getByText('日报：完成前后端联调')).toBeVisible();
  await screenshot(page, info.project.name, 'preview');
  await selectFixtureRecipient(page); await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('fixture@example.invalid');
  await expect(page.getByRole('dialog')).toContainText('配置的日报群');
  await screenshot(page, info.project.name, 'confirmation');
  await page.getByRole('button', { name: '取消', exact: true }).click(); expect(await counts()).toEqual(before);
  await confirm(page); await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(await counts()).toEqual({ email: before.email + 1, lark: before.lark + 1 });
  await expect(page.getByRole('checkbox', { name: '邮件', exact: true })).toBeEnabled();
  await expect(page.getByRole('checkbox', { name: '飞书', exact: true })).toBeDisabled();
  await screenshot(page, info.project.name, 'accepted');
});

test('duplicate_click_uses_one_post', async ({ page }) => {
  const before = await counts(); let posts = 0;
  page.on('request', request => { if (request.url().endsWith('/deliveries') && request.method() === 'POST') posts++; });
  await authenticate(page); await generate(page); await selectFixtureRecipient(page); await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await page.getByRole('button', { name: '确认推送', exact: true }).evaluate(element => { (element as HTMLButtonElement).click(); (element as HTMLButtonElement).click(); });
  await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(posts).toBe(1); expect(await counts()).toEqual({ email: before.email+1, lark: before.lark+1 });
});

test('unauthorized_no_side_effects', async ({ page, request }) => {
  const before = await counts(); await page.goto('/'); await page.getByLabel('操作令牌', { exact: true }).fill('invalid-token');
  await page.getByRole('button', { name: '验证令牌', exact: true }).click();
  await expect(page.getByText('操作令牌无效或未提供')).toBeVisible(); await expect(page.getByLabel('操作令牌')).toHaveValue('');
  const result = await request.post('http://127.0.0.1:8775/api/v1/deliveries', { data: { report_date:'2026-09-25', report_revision:'a'.repeat(64), channels:['email','lark'] }, headers:{ 'Idempotency-Key':crypto.randomUUID() } });
  expect(result.status()).toBe(401); expect(await counts()).toEqual(before);
});

test('post_response_loss_no_resubmit', async ({ page }) => {
  const before = await counts(); let posts = 0;
  await authenticate(page); await generate(page);
  await page.route('**/api/v1/deliveries', async route => { posts++; await route.fetch(); await route.abort('failed'); });
  await confirm(page); await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(posts).toBe(1); expect(await counts()).toEqual({ email:before.email+1,lark:before.lark+1 });
});

test('refresh_resume_current_without_post', async ({ page }) => {
  await scenario({ delay:2 }); await authenticate(page);
  await page.getByRole('button', { name:'采集并生成', exact:true }).click(); await expect(page.getByText('正在生成日报…')).toBeVisible();
  await page.reload(); let posts = 0; page.on('request', r => { if (r.method()==='POST') posts++; });
  await page.getByLabel('报告日期', { exact:true }).fill('2026-09-25'); await page.getByLabel('操作令牌').fill(token);
  await page.getByRole('button', { name:'验证令牌', exact:true }).click();
  await expect(page.getByRole('heading', { name:'联调示例团队' })).toBeVisible(); expect(posts).toBe(0);
});

test('A_B_race_never_replaces_current_date', async ({ page }) => {
  await authenticate(page); await generate(page);
  let release!: () => void; const gate=new Promise<void>(done=>{release=done;});
  let ready!: () => void; const fetched=new Promise<void>(done=>{ready=done;});
  await page.route('**/api/v1/reports/2026-09-25/preview',async route=>{ const result=await route.fetch(); ready(); await gate; await route.fulfill({response:result}).catch(()=>{}); });
  await page.getByRole('button',{name:'预览日报',exact:true}).click(); await fetched;
  await page.getByLabel('报告日期',{exact:true}).fill('2026-09-24'); release();
  await expect(page.getByRole('heading',{name:'联调示例团队'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'推送日报',exact:true})).toHaveCount(0);
});

test('one_channel_failed_only_rejected_can_be_retried', async ({ page }, info) => {
  await authenticate(page); await generate(page); await scenario({ email:'rejected' }); const before=await counts();
  await confirm(page); await expect(page.getByText('部分渠道受理失败，请核对渠道结果')).toBeVisible();
  await expect(page.getByRole('checkbox',{name:'邮件',exact:true})).toBeEnabled();
  await expect(page.getByRole('checkbox',{name:'飞书',exact:true})).toBeDisabled(); await screenshot(page,info.project.name,'partial');
  await scenario({}); await confirm(page); await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(await counts()).toEqual({email:before.email+2,lark:before.lark+1});
});

test('unknown_email_never_automatically_repeats_after_refresh', async ({ page }, info) => {
  await authenticate(page); await generate(page); await scenario({email:'unknown'}); const before=await counts();
  await confirm(page); await expect(page.getByText('推送结果未知，请先核实；未自动重发')).toBeVisible();
  await expect(page.getByRole('checkbox',{name:'邮件',exact:true})).toBeEnabled(); await screenshot(page,info.project.name,'unknown');
  await page.reload(); await authenticate(page); await expect(page.getByRole('button',{name:'推送日报',exact:true})).toBeDisabled();
  expect(await counts()).toEqual({email:before.email+1,lark:before.lark+1});
});

test('report_updated_confirmation_invalidated_before_send', async ({ page,request }) => {
  await authenticate(page); await generate(page); const before=await counts();
  await selectFixtureRecipient(page); await page.getByRole('button',{name:'推送日报',exact:true}).click();
  const result=await request.post('http://127.0.0.1:8775/api/v1/generations',{headers:{...headers,'Idempotency-Key':crypto.randomUUID()},data:{report_date:'2026-09-25'}}); expect(result.status()).toBe(202);
  await expect.poll(async()=> (await request.get('http://127.0.0.1:8775/api/v1/operations/current',{headers})).json().then(v=>v.status)).toBe('succeeded');
  await page.getByRole('button',{name:'确认推送',exact:true}).click();
  await expect(page.getByText('日报已更新，请重新预览后推送')).toBeVisible();
  await expect(page.getByRole('button',{name:'推送日报',exact:true})).toHaveCount(0); expect(await counts()).toEqual(before);
});

test('malicious_text_safe_and_no_secret_markers', async ({ page },info) => {
  await scenario({malicious:true}); await authenticate(page); await generate(page);
  await expect(page.getByText('<img src=x onerror="window.attack=1">',{exact:false})).toBeVisible();
  expect(await page.locator('img').count()).toBe(0); expect(await page.evaluate(()=>(window as any).attack)).toBeUndefined();
  expect(await page.locator('a[href^="javascript:"]').count()).toBe(0);
  for(const marker of ['sensitive-message-marker','external-private-id','synthetic-secret']) expect(await page.content()).not.toContain(marker);
  await screenshot(page,info.project.name,'safe-content');
});

test('keyboard_dialog_blocks_background_and_escape_never_sends', async ({ page }) => {
  const before=await counts(); await authenticate(page); await generate(page);
  await selectFixtureRecipient(page); await page.getByRole('button',{name:'推送日报',exact:true}).focus(); await page.keyboard.press('Enter');
  const cancel=page.getByRole('button',{name:'取消',exact:true}); const send=page.getByRole('button',{name:'确认推送',exact:true});
  await expect(cancel).toBeFocused(); await page.keyboard.press('Tab'); await expect(send).toBeFocused();
  await page.getByRole('button',{name:'采集并生成',exact:true}).evaluate(element=>(element as HTMLButtonElement).focus());
  await expect(send).toBeFocused();
  await page.keyboard.press('Shift+Tab'); await expect(cancel).toBeFocused();
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0); expect(await counts()).toEqual(before);
  await page.getByRole('button',{name:'推送日报',exact:true}).focus(); await page.keyboard.press('Enter'); await page.keyboard.press('Tab'); await page.keyboard.press('Enter');
  await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(await counts()).toEqual({email:before.email+1,lark:before.lark+1});
});


test('manual_by_key_404_after_network_loss_recovers_same_request', async ({ page }) => {
  await authenticate(page); let posts=0; let queries=0; const keys:string[]=[]; const before=await counts();
  await page.route('**/api/v1/generations',async route=>{posts++; keys.push(route.request().headers()['idempotency-key']);
    if(posts===1) await route.abort('failed'); else await route.continue(); });
  await page.route('**/api/v1/operations/by-key/*',async route=>{ queries++; if(queries===1) await route.abort('failed'); else await route.continue(); });
  await page.getByRole('button',{name:'采集并生成',exact:true}).click(); await expect(page.getByText('执行结果尚未确认')).toBeVisible();
  await expect(page.getByRole('button',{name:'重试原请求',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'查询执行结果',exact:true}).click(); await expect(page.getByText('未找到该操作记录')).toBeVisible();
  await page.getByRole('button',{name:'重试原请求',exact:true}).click(); await expect(page.getByText('日报生成完成，推送需单独确认')).toBeVisible();
  expect(posts).toBe(2); expect(keys[1]).toBe(keys[0]); expect(await counts()).toEqual(before);
});


test('empty_token_feedback_and_disabled_generation_are_clear', async ({ page }, info) => {
  let apiRequests = 0;
  page.on('request', request => { if (request.url().startsWith('http://127.0.0.1:8775/api/v1/')) apiRequests++; });
  await page.goto('/');
  const input = page.getByLabel('操作令牌', { exact: true });
  const generation = page.getByRole('button', { name: '采集并生成', exact: true });
  await expect(generation).toBeDisabled();
  await expect(generation).toHaveAccessibleDescription(/请先输入并验证操作令牌/);
  await expect(generation).toHaveCSS('cursor', 'not-allowed');
  expect(await generation.evaluate(element => Number(getComputedStyle(element).opacity))).toBeLessThan(1);
  await page.getByRole('button', { name: '验证令牌', exact: true }).click();
  await expect(page.getByRole('region', { name: '日报操作' }).getByRole('status')).toContainText('请输入操作令牌');
  await expect(input).toBeFocused();
  await input.fill('   ');
  await page.getByRole('button', { name: '验证令牌', exact: true }).click();
  await expect(page.getByRole('region', { name: '日报操作' }).getByRole('status')).toContainText('请输入操作令牌');
  await expect(input).toBeFocused();
  expect(apiRequests).toBe(0);
  await screenshot(page, info.project.name, 'token-required');
});


test('manual_preview_focus_and_feedback', async ({ page }) => {
  await authenticate(page); await generate(page); await page.emulateMedia({ reducedMotion: 'reduce' });
  const before = await counts(); const methods: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/')) methods.push(request.method()); });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole('button', { name: '预览日报', exact: true }).click();
  await expect(page.getByText(/已加载 2026-09-25 日报预览/)).toBeVisible();
  const heading = page.getByRole('heading', { name: '联调示例团队' });
  await expect(heading).toBeFocused(); await expect(heading).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(methods.length).toBeGreaterThan(0); expect(methods.every(method => method === 'GET')).toBe(true);
  expect(await counts()).toEqual(before);
});

test('query_feedback_and_readonly_requests', async ({ page }) => {
  await authenticate(page); await generate(page); const before = await counts(); const methods: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/')) methods.push(request.method()); });
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/operations/*', async route => { await gate; await route.continue(); });
  await page.getByRole('button', { name: '查询执行结果', exact: true }).click();
  await expect(page.getByRole('button', { name: '正在查询执行结果…', exact: true })).toBeDisabled(); release();
  await expect(page.getByText(/执行结果查询完成/)).toBeVisible();
  const first = await page.getByLabel('本次查询时间', { exact: true }).getAttribute('datetime');
  await page.getByRole('button', { name: '查询执行结果', exact: true }).click();
  await expect(page.getByLabel('本次查询时间', { exact: true })).not.toHaveAttribute('datetime', first!);
  expect(methods.length).toBeGreaterThan(0); expect(methods.every(method => method === 'GET')).toBe(true);
  expect(await counts()).toEqual(before);
});


async function emailEvents() {
  const raw = await readFile(path.join(directory, 'deliveries.jsonl'), 'utf8').catch(() => '');
  return raw.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)).filter(value => value.channel === 'email');
}

test('email_selection_sends_only_confirmed_recipient', async ({ page }, info) => {
  const before = await counts(); const priorEvents = (await emailEvents()).length;
  await authenticate(page); await generate(page);
  const member = page.getByRole('checkbox', { name: 'fixture@example.invalid', exact: true });
  const mentor = page.getByRole('checkbox', { name: 'mentor@example.invalid', exact: true });
  await expect(member).not.toBeChecked(); await expect(mentor).not.toBeChecked();
  await expect(page.getByRole('button', { name: '推送日报', exact: true })).toBeDisabled();
  await expect(page.getByText('请选择至少一位邮件收件人')).toBeVisible();
  await page.getByRole('checkbox', { name: '飞书', exact: true }).uncheck(); await mentor.check();
  await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('mentor@example.invalid');
  await expect(page.getByRole('dialog')).not.toContainText('fixture@example.invalid');
  await expect(page.getByRole('dialog')).toContainText('再次推送可能产生重复邮件');
  await screenshot(page, info.project.name, 'selected-mentor');
  await page.getByRole('button', { name: '取消', exact: true }).click(); expect(await counts()).toEqual(before);
  await page.getByRole('button', { name: '推送日报', exact: true }).click(); await page.getByRole('button', { name: '确认推送', exact: true }).click();
  await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(await counts()).toEqual({ email: before.email + 1, lark: before.lark });
  expect((await emailEvents()).slice(priorEvents)).toEqual([{ channel: 'email', recipients: ['mentor@example.invalid'] }]);
});

test('email_new_confirmation_resends_while_lark_stays_blocked', async ({ page, request }) => {
  const before = await counts(); const bodies: Record<string, unknown>[] = []; const keys: string[] = [];
  page.on('request', call => { if (call.url().endsWith('/deliveries') && call.method() === 'POST') { bodies.push(call.postDataJSON()); keys.push(call.headers()['idempotency-key']); } });
  await authenticate(page); await generate(page); await confirm(page);
  await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  const replay = await request.post('http://127.0.0.1:8775/api/v1/deliveries', { headers: { ...headers, 'Idempotency-Key': keys[0] }, data: bodies[0] });
  expect(replay.status()).toBe(200); expect(await counts()).toEqual({ email: before.email + 1, lark: before.lark + 1 });
  await expect(page.getByRole('checkbox', { name: '飞书', exact: true })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'mentor@example.invalid', exact: true }).check();
  await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('mentor@example.invalid');
  await expect(page.getByRole('dialog')).not.toContainText('配置的日报群');
  await page.getByRole('button', { name: '确认推送', exact: true }).click();
  await expect.poll(counts).toEqual({ email: before.email + 2, lark: before.lark + 1 });
  expect(keys).toHaveLength(2); expect(keys[1]).not.toBe(keys[0]);
  expect(bodies[1]).toMatchObject({ channels: ['email'], email_recipients: ['mentor@example.invalid'] });
});

test('query_preview_feedback_timeout_and_keyboard_focus', async ({ page }) => {
  await authenticate(page); await generate(page); const before = await counts();
  await page.clock.install();
  await page.route('**/api/v1/reports/*/preview', route => route.abort('timedout'));
  await page.getByRole('button', { name: '预览日报', exact: true }).focus(); await page.keyboard.press('Enter');
  await expect(page.getByText('日报预览失败，请查看错误提示。')).toBeVisible();
  await page.unroute('**/api/v1/reports/*/preview');
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/reports/*/preview', async route => { await gate; await route.continue().catch(() => {}); });
  await page.getByRole('button', { name: '预览日报', exact: true }).click();
  await expect(page.getByRole('button', { name: '正在加载日报预览…', exact: true })).toBeDisabled();
  await page.clock.fastForward(10000);
  await expect(page.getByText('请求超时，请重新预览日报。')).toBeVisible(); release();
  await page.unroute('**/api/v1/reports/*/preview'); await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: '预览日报', exact: true }).focus(); await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: '联调示例团队' })).toBeFocused();
  await expect(page.getByRole('heading', { name: '联调示例团队' })).toBeInViewport();
  expect(await counts()).toEqual(before); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});


test('successful_query_keeps_completion_when_attached_preview_times_out', async ({ page }) => {
  await authenticate(page); await generate(page); const before = await counts();
  await selectFixtureRecipient(page); await page.clock.install();
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/reports/*/preview', async route => { await gate; await route.continue().catch(() => {}); });
  await page.getByRole('button', { name: '查询执行结果', exact: true }).click();
  await expect(page.getByText(/执行结果查询完成/)).toBeVisible();
  await expect(page.getByLabel('本次查询时间', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '推送日报', exact: true })).toHaveCount(0);
  await page.clock.fastForward(10000);
  await expect(page.getByText('日报预览请求超时，请点击“预览日报”重试。')).toBeVisible();
  await expect(page.getByText(/执行结果查询完成/)).toBeVisible();
  await expect(page.getByRole('button', { name: '查询执行结果', exact: true })).toBeEnabled(); release();
  await page.unroute('**/api/v1/reports/*/preview');
  await expect(page.getByRole('button', { name: '推送日报', exact: true })).toHaveCount(0);
  expect(await counts()).toEqual(before);
});
