import { reportFixture } from './fixture';
export function operationFixture(status = 'running') {
  return { operation_id: 'd13e0218-2e9f-424e-bef6-8e5d6de79814', request_id: '96ff843b-f0c4-4c11-a23e-bd2d6e15c938',
    kind: 'generation', report_date: '2026-09-25', status, created_at: '2026-09-25T02:00:00Z', updated_at: '2026-09-25T02:00:00Z',
    report_revision: status === 'running' ? null : 'a'.repeat(64), error_code: null,
    sources: { github_commits: { status: 'success', error_code: null }, lark_tasks: { status: 'disabled', error_code: null }, lark_messages: { status: 'disabled', error_code: null } },
    deliveries: { email: { status: 'not_requested', attempts: 0, error_code: null }, lark: { status: 'not_requested', attempts: 0, error_code: null } } };
}
export function previewFixture() {
  return { report: reportFixture(), report_revision: 'a'.repeat(64), sources: operationFixture().sources,
    targets: { email: { enabled: true, label: '邮件（1 位收件人）', previous: null, recipients: ['fixture@example.invalid'] }, lark: { enabled: true, label: '配置的日报群', previous: null } } };
}
