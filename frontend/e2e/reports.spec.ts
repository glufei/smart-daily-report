import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import path from 'node:path';

async function query(page: Page, date: string) {
  await page.getByLabel('报告日期', { exact: true }).fill(date);
  await page.getByRole('button', { name: '查看日报', exact: true }).click();
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}
async function screenshot(page: Page, project: string, state: string) {
  await noOverflow(page);
  await page.screenshot({ path: path.resolve(process.env.DAILY_REPORT_E2E_SCREENSHOT_DIR || '../docs/frontend/screenshots', `${project}-${state}.png`), fullPage: true, animations: 'disabled' });
}

test('real saved reports retain every member, sections, timestamps and source states', async ({ page }, info) => {
  const requests: string[] = [];
  const bodies: string[] = [];
  page.on('request', request => { if (request.resourceType() === 'fetch') requests.push(`${request.method()} ${request.url()}`); });
  page.on('response', async response => { if (response.url().includes('/api/v1/reports/')) bodies.push(await response.text()); });
  await page.goto('/'); await screenshot(page, info.project.name, 'initial');
  await query(page, '2026-09-25'); await expect(page.getByRole('heading', { name: '示例研发团队' })).toBeVisible();
  await expect(page.getByText(/UTC\+00:00/)).toBeVisible();
  await expect(page.getByRole('article')).toHaveCount(2);
  for (const name of ['示例成员甲', '示例成员乙']) {
    await expect(page.getByRole('article', { name }).getByRole('heading', { level: 4 })).toHaveText(['代码提交', '任务进展', '协作沟通']);
  }
  await expect(page.getByRole('article', { name: '示例成员乙' }).getByText('今日无记录')).toHaveCount(3);
  await screenshot(page, info.project.name, 'normal');
  await query(page, '2026-09-26'); await expect(page.getByText('部分数据源获取失败：任务进展')).toBeVisible();
  for (const name of ['示例成员甲', '示例成员乙']) await expect(page.getByRole('article', { name }).getByText('数据获取失败', { exact: true })).toBeVisible();
  await screenshot(page, info.project.name, 'source-failure');
  await query(page, '2026-09-30'); await expect(page.getByRole('article').getByText('今日无记录')).toHaveCount(6);
  await screenshot(page, info.project.name, 'empty-records');
  expect(requests).toHaveLength(3);
  expect(requests.every(value => /^GET http:\/\/127\.0\.0\.1:8765\/api\/v1\/reports\//.test(value))).toBe(true);
  for (const marker of ['sensitive-message-marker', 'external-private-id', 'private-html-marker', 'private-markdown-marker']) {
    expect((await page.content()) + bodies.join('')).not.toContain(marker);
  }
});

test('missing history and corrupt payload are different page states', async ({ page }, info) => {
  await page.goto('/'); await query(page, '2026-09-27');
  await expect(page.getByRole('heading', { name: '该日期尚无日报' })).toBeVisible();
  await expect(page.getByText('今日无记录')).toHaveCount(0); await screenshot(page, info.project.name, 'missing');
  await query(page, '2026-09-28'); await expect(page.getByText('日报数据格式异常')).toBeVisible();
  await expect(page.getByRole('heading', { name: '该日期尚无日报' })).toHaveCount(0);
  await expect(page.getByText('今日无记录')).toHaveCount(0); await screenshot(page, info.project.name, 'bad-payload');
});

test('real storage read failure is an error and never leaks diagnostic paths', async ({ page }, info) => {
  await page.route('**/api/v1/reports/*', route => route.continue({ url: route.request().url().replace(':8765', ':8766') }));
  await page.goto('/'); await query(page, '2026-09-25');
  await expect(page.getByText('日报读取失败，请稍后重新查询')).toBeVisible();
  await expect(page.getByText('今日无记录')).toHaveCount(0);
  expect(await page.content()).not.toContain('private-path-marker'); await screenshot(page, info.project.name, 'storage-error');
});

test('offline query clears old content and waits for an explicit retry', async ({ page, context }, info) => {
  await page.goto('/'); await query(page, '2026-09-25'); await expect(page.getByRole('article')).toHaveCount(2);
  await context.setOffline(true); await query(page, '2026-09-26');
  await expect(page.getByText('无法连接日报服务')).toBeVisible(); await expect(page.getByRole('article')).toHaveCount(0);
  await screenshot(page, info.project.name, 'offline');
  await context.setOffline(false); await page.getByRole('button', { name: '重新查询' }).click();
  await expect(page.getByText('部分数据源获取失败：任务进展')).toBeVisible();
});

test('late real A response cannot overwrite B or hide B source failure', async ({ page }, info) => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let fetched!: () => void;
  const ready = new Promise<void>(resolve => { fetched = resolve; });
  await page.route('**/api/v1/reports/2026-09-25', async route => {
    const response = await route.fetch(); fetched(); await gate;
    await route.fulfill({ response }).catch(() => {}); // Browser may abort old A.
  });
  await page.goto('/'); await query(page, '2026-09-25'); await ready;
  await expect(page.getByText('正在加载日报…')).toBeVisible(); await screenshot(page, info.project.name, 'loading');
  await query(page, '2026-09-26'); await expect(page.getByText('部分数据源获取失败：任务进展')).toBeVisible();
  release();
  await expect(page.locator('.report-meta')).toContainText('2026-09-26');
  await expect(page.getByText('部分数据源获取失败：任务进展')).toBeVisible();
});

test('malicious records remain text, links remain safe, long content wraps', async ({ page }, info) => {
  await page.goto('/'); await query(page, '2026-09-29');
  await expect(page.getByText('<img src=x onerror="window.attack=1">', { exact: false })).toBeVisible();
  await expect(page.locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).attack)).toBeUndefined();
  expect(await page.locator('a[href]').count()).toBe(0);
  await screenshot(page, info.project.name, 'long-safe-content');
});

test('keyboard navigation reaches named query and retry controls', async ({ page }, info) => {
  await page.goto('/'); await page.getByLabel('报告日期', { exact: true }).fill('2026-09-25');
  await page.getByLabel('报告日期', { exact: true }).focus();
  const button = page.getByRole('button', { name: '查看日报', exact: true });
  for (let i = 0; i < 8 && !(await button.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press('Tab');
  await expect(button).toBeFocused(); await page.keyboard.press('Enter'); await expect(page.getByRole('article')).toHaveCount(2);
  await screenshot(page, info.project.name, 'keyboard');
  await query(page, '2026-09-28'); await expect(page.getByText('日报数据格式异常')).toBeVisible();
  await button.focus(); await page.keyboard.press('Tab'); await expect(page.getByRole('button', { name: '重新查询' })).toBeFocused();
  await page.keyboard.press('Enter'); await expect(page.getByText('日报数据格式异常')).toBeVisible();
});
