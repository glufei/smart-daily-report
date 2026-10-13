"""Real API/SQLite/pipeline with synthetic HTTP/SMTP boundaries; never user config."""
import argparse
from datetime import date, datetime, timezone
from email.utils import getaddresses
import json
import logging
from pathlib import Path
import smtplib
import time

import httpx
import uvicorn

from smart_daily_report.shared.logging import JsonFormatter, configure_logging
from smart_daily_report.shared.models import MemberConfig, RunConfig, SmtpConfig
from smart_daily_report.shared.operation_storage import OperationStore
from smart_daily_report.web.app import create_app
from smart_daily_report.web.operations import OperationService

TOKEN = 'public-e2e-only-token-not-a-real-secret-123456'


def delivery_counts(directory):
    events = directory / 'deliveries.jsonl'
    values = [json.loads(line)['channel'] for line in events.read_text(encoding='utf-8').splitlines()] if events.exists() else []
    return {name: values.count(name) for name in ('email','lark')}


def create_fixture(directory):
    directory.mkdir(parents=True, exist_ok=True)
    def scenario():
        path = directory / 'scenario.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    def event(channel, recipients=None):
        with (directory/'deliveries.jsonl').open('a',encoding='utf-8') as output:
            output.write(json.dumps({'channel':channel, **({'recipients':recipients} if recipients is not None else {})})+'\n')
    at = datetime(2026,9,25,2,tzinfo=timezone.utc)
    def transport(request):
        options = scenario()
        if request.url.host == 'hook.invalid':
            event('lark')
            if options.get('lark') == 'unknown':
                raise httpx.ReadTimeout('synthetic response loss', request=request)
            return httpx.Response(200,json={'code':19024 if options.get('lark')=='rejected' else 0})
        if request.url.path.endswith('/tenant_access_token/internal'):
            return httpx.Response(200,json={'code':0,'tenant_access_token':'external-private-id','expire':3600})
        if request.url.host == 'github.invalid':
            time.sleep(options.get('delay',0))
            attack = '<img src=x onerror="window.attack=1">'
            return httpx.Response(200,json=[{'sha':'fixture-sha','author':{'login':'fixture-user'},
                'commit':{'message':attack if options.get('malicious') else '完成真实接口联调','author':{'name':'Fixture','date':at.isoformat()}},
                'html_url':'javascript:alert(1)' if options.get('malicious') else 'https://example.com/commit',
                'stats':{'additions':7,'deletions':2},'files':[{'filename':'a.ts'}]}])
        if '/tasklists/' in request.url.path:
            if options.get('task_failure'):
                return httpx.Response(403)
            return httpx.Response(200,json={'code':0,'data':{'items':[{'guid':'fixture-task','summary':'完成任务清单接入',
                'completed_at':str(int(at.timestamp()*1000)),'members':[{'id':'external-private-id','type':'user','role':'assignee'}]}],'has_more':False}})
        if request.url.path.endswith('/messages'):
            return httpx.Response(200,json={'code':0,'data':{'items':[{'message_id':identifier,'sender':{'id':'external-private-id'},
                'body':{'content':json.dumps({'text':text})},'create_time':str(int(at.timestamp()*1000)),'chat_name':'示例研发群'}
                for identifier,text in [('normal','日报：完成前后端联调'),('sensitive','日报 sensitive-message-marker')]],'has_more':False}})
        raise AssertionError('Unexpected fixture upstream request')
    class SMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def starttls(self, *, context=None): pass
        def send_message(self,message):
            event('email', [address for _,address in getaddresses(message.get_all('To', []))])
            if scenario().get('email') == 'rejected':
                raise smtplib.SMTPRecipientsRefused({'fixture@example.invalid':(550,b'rejected')})
            if scenario().get('email') == 'unknown':
                raise TimeoutError('synthetic response loss')
            return {}
    config = RunConfig(team_name='联调示例团队',timezone='Asia/Shanghai',
        members=[MemberConfig('fixture-member','示例成员甲',['fixture-user'],['external-private-id'])],
        github_repositories=['fixture/report'],lark_project_ids=['fixture-list'],lark_chat_ids=['fixture-chat'],
        report_keywords=['日报'],sensitive_keywords=['sensitive-message-marker'],holidays=set(),
        database_path=str(directory/'reports.sqlite3'),github_api_base_url='https://github.invalid',lark_api_base_url='https://lark.invalid/open-apis',
        github_token=None,lark_app_id='synthetic-app',lark_app_secret='synthetic-secret',lark_webhook='https://hook.invalid/fixed',
        lark_task_search_path='/task/v2/tasklists/{tasklist_guid}/tasks',lark_message_path='/im/v1/messages',
        lark_token_path='/auth/v3/tenant_access_token/internal',smtp=SmtpConfig('smtp.invalid',587,None,None,'fixture@example.invalid',['fixture@example.invalid','mentor@example.invalid']))
    service=OperationService(config,OperationStore(directory/'reports.sqlite3.operations.sqlite3'),
        client_factory=lambda:httpx.Client(transport=httpx.MockTransport(transport)),smtp_factory=SMTP)
    app=create_app(directory/'reports.sqlite3',operations=service,operation_token=TOKEN,allowed_origins=('http://127.0.0.1:5174',))
    return app,service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8775)
    args=parser.parse_args()
    directory=Path(__file__).resolve().parents[2]/'.runtime'/'e2e-operations'
    directory.mkdir(parents=True,exist_ok=True)
    # Fixed synthetic files only. No recursive deletion, user config or .env.
    for filename in ('reports.sqlite3','reports.sqlite3.operations.sqlite3','deliveries.jsonl','scenario.json'):
        (directory/filename).unlink(missing_ok=True)
    logger=configure_logging()
    handler=logging.FileHandler(directory/'api.log',mode='w',encoding='utf-8'); handler.setFormatter(JsonFormatter()); logger.addHandler(handler)
    app,_=create_fixture(directory)
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning')


if __name__=='__main__':
    main()
