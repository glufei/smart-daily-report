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
  await expect(page.getByRole('button', { name: '推送日报', exact: true })).toBeEnabled();
}
async function confirm(page: Page) {
  await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: '确认推送', exact: true }).click();
}
async function screenshot(page: Page, project: string, state: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: path.resolve(`../docs/frontend/screenshots/v1.2/${project}-${state}.png`), fullPage: true, animations: 'disabled' });
}
test.beforeEach(async () => scenario({}));

test('generation_preview_confirmation_and_delivery', async ({ page }, info) => {
  const before = await counts(); await authenticate(page); await generate(page);
  expect(await counts()).toEqual(before);
  await expect(page.getByText('代码提交：获取成功')).toBeVisible();
  await expect(page.getByText(/完成任务清单接入（已完成）/)).toBeVisible();
  await expect(page.getByText('日报：完成前后端联调')).toBeVisible();
  await screenshot(page, info.project.name, 'preview');
  await page.getByRole('button', { name: '推送日报', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('邮件（1 位收件人）');
  await expect(page.getByRole('dialog')).toContainText('配置的日报群');
  await screenshot(page, info.project.name, 'confirmation');
  await page.getByRole('button', { name: '取消', exact: true }).click(); expect(await counts()).toEqual(before);
  await confirm(page); await expect(page.getByText('所选渠道已受理，请核对实际收件')).toBeVisible();
  expect(await counts()).toEqual({ email: before.email + 1, lark: before.lark + 1 });
  await expect(page.getByRole('checkbox', { name: '邮件', exact: true })).toBeDisabled();
  await expect(page.getByRole('checkbox', { name: '飞书', exact: true })).toBeDisabled();
  await screenshot(page, info.project.name, 'accepted');
});

test('duplicate_click_uses_one_post', async ({ page }) => {
  const before = await counts(); let posts = 0;
  page.on('request', request => { if (request.url().endsWith('/deliveries') && request.method() === 'POST') posts++; });
  await authenticate(page); await generate(page); await page.getByRole('button', { name: '推送日报', exact: true }).click();
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

test('unknown_not_repeatable_even_after_refresh', async ({ page }, info) => {
  await authenticate(page); await generate(page); await scenario({email:'unknown'}); const before=await counts();
  await confirm(page); await expect(page.getByText('推送结果未知，请先核实，不能重复推送')).toBeVisible();
  await expect(page.getByRole('checkbox',{name:'邮件',exact:true})).toBeDisabled(); await screenshot(page,info.project.name,'unknown');
  await page.reload(); await authenticate(page); await expect(page.getByRole('button',{name:'推送日报',exact:true})).toBeDisabled();
  expect(await counts()).toEqual({email:before.email+1,lark:before.lark+1});
});

test('report_updated_confirmation_invalidated_before_send', async ({ page,request }) => {
  await authenticate(page); await generate(page); const before=await counts();
  await page.getByRole('button',{name:'推送日报',exact:true}).click();
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
  await page.getByRole('button',{name:'推送日报',exact:true}).focus(); await page.keyboard.press('Enter');
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
