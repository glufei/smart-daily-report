import { readFile } from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
export default async function teardown() {
  const log = await readFile(path.resolve('../.runtime/e2e-operations/api.log'), 'utf8');
  for (const marker of ['public-e2e-only-token', 'synthetic-secret', 'external-private-id', 'sensitive-message-marker']) assert(!log.includes(marker), 'Normal logs must not expose private fixture markers');
  console.log('Real API/SQLite browser regression; external boundaries synthetic; no private log markers.');
}
