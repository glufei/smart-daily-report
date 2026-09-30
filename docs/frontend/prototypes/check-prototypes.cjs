// Reproduce layout/state evidence from unmodified OpenDesign exports.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const fs = require('node:fs/promises');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const results = [];
  try {
    for (const version of process.argv.slice(2)) {
      for (const [width, height] of [[375, 812], [1440, 900]]) {
        const page = await browser.newPage({ viewport: { width, height } });
        await page.goto(pathToFileURL(path.join(__dirname, `${version}.html`)).href);
        for (const state of ['查询前', '加载中', '正常日报', '尚无日报', '查询失败', '任务来源失败']) {
          await page.getByRole('button', { name: state, exact: true }).click();
          if (state === '正常日报' || state === '任务来源失败') {
            assert.equal(await page.locator('.member').count(), 2);
            assert.deepEqual(await page.locator('.member').first().locator('h4').allTextContents(), ['代码提交', '任务进展', '协作沟通']);
          }
          if (state === '任务来源失败') assert.equal(await page.getByText('数据获取失败', { exact: true }).count(), 2);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, `${version}/${width}/${state} overflow`);
          await page.screenshot({ path: path.join(__dirname, `${version}-${width}-${state}.png`), fullPage: true, animations: 'disabled' });
          results.push({ version, width, height, state, noHorizontalOverflow: true });
        }
        await page.getByRole('button', { name: '查询前', exact: true }).click();
        await page.getByLabel('报告日期', { exact: true }).focus();
        // Chromium's native date field has several keyboard-editable segments.
        for (let i = 0; i < 8; i++) {
          if (await page.getByRole('button', { name: '查看日报', exact: true }).evaluate(el => el === document.activeElement)) break;
          await page.keyboard.press('Tab');
        }
        assert.equal(await page.getByRole('button', { name: '查看日报', exact: true }).evaluate(el => el === document.activeElement), true);
        await page.keyboard.press('Enter');
        await page.getByRole('heading', { name: '示例研发团队', exact: true }).waitFor();
        results.push({ version, width, keyboardQuery: true });
        await page.close();
      }
    }
    await fs.writeFile(path.join(__dirname, 'checks.json'), JSON.stringify(results, null, 2) + '\n');
    console.log(`Passed ${results.length} prototype layout/state/keyboard checks`);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
