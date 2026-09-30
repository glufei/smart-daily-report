import { readFile, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';

export default async function teardown() {
  const directory = path.resolve('../.runtime/e2e');
  for (const port of [8765, 8766]) {
    const baseline = JSON.parse(await readFile(path.join(directory, `baseline-${port}.json`), 'utf8'));
    const hash = createHash('sha256').update(await readFile(path.join(directory, baseline.database))).digest('hex');
    assert.equal(hash, baseline.sha256, 'Viewing must preserve SQLite bytes');
    const log = await readFile(path.join(directory, `api-${port}.log`), 'utf8');
    for (const marker of ['sensitive-message-marker', 'external-private-id', 'private-path-marker', 'private-payload-marker', 'private-html-marker', 'private-markdown-marker']) {
      assert(!log.includes(marker), 'Normal API logs must not expose private markers');
    }
    for (const line of log.trim().split('\n').filter(Boolean)) assert(JSON.parse(line).run_id, 'Request logs require run IDs');
  }
  let forbidden = false;
  try { await access(path.join(directory, 'forbidden-call.txt')); forbidden = true; } catch { /* absent is expected */ }
  assert.equal(forbidden, false, 'Viewing must never invoke pipeline or notifications');
  console.log('SQLite unchanged; no forbidden pipeline calls or sensitive log markers.');
}
