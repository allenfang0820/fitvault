import sys
sys.path.insert(0, '.')
import llm_backend
import requests
import json
import unittest.mock

real_post = requests.post

def fake_post(*args, **kwargs):
    print('=== CAPTURED REQUEST ===')
    print('URL:', args[0] if args else kwargs.get('url'))
    print('HEADERS:')
    for k, v in (kwargs.get('headers') or {}).items():
        print(f'  {k}: {v}')
    print('BODY:')
    print(json.dumps(kwargs.get('json'), ensure_ascii=False, indent=2))
    raise SystemExit(0)

import llm_backend as lb
lb.requests.post = fake_post

try:
    lb.chat_completions(
        url='http://localhost:28789/v1/chat/completions',
        api_key='4c81c50693620e5f1b3d5e5d9d3252ef5254540e4ac51d1a',
        model='openclaw',
        messages=[{'role':'user','content':'hi'}],
        session_id='test',
        agent_id='8665944a',
        timeout=10,
    )
except SystemExit:
    pass
except Exception as e:
    print('error:', e)
