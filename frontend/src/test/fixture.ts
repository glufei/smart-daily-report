import type { Report } from '../api';
export function reportFixture(date = '2026-09-25'): Report {
  return {
    report_date: date, team_name: '示例研发团队', generated_at: `${date}T18:00:00+08:00`,
    source_status: { github_commits: 'success', lark_tasks: 'success', lark_messages: 'success' },
    members: [{ member_id: 'member-a', display_name: '示例成员甲',
      commits: [{ record_id: 'c1', url: 'https://example.com/commit', repository: 'example/report', message: '修正日期选择交互', committed_at: `${date}T16:00:00+08:00`, additions: 10, deletions: 2, files_changed: 1 }],
      tasks: [{ record_id: 't1', url: null, title: '完成页面契约评审', status: '已完成', status_from: '进行中', status_to: '已完成', changed_at: `${date}T17:00:00+08:00` }],
      messages: [{ record_id: 'm1', url: null, content: '日报：已完成只读页面原型', chat_name: '示例研发群', sent_at: `${date}T17:30:00+08:00` }],
    }, { member_id: 'member-b', display_name: '示例成员乙', commits: [], tasks: [], messages: [] }],
  };
}
