"""Stands in for a coding agent CLI in runner tests: talks to the backend like the MCP server would."""
import os
import sys
import time
import httpx

mode, day = sys.argv[1], sys.argv[2]
base, headers = os.environ['ACE_BACKEND_URL'], {'X-ACE-Client': '1'}
if mode == 'sleep':
    time.sleep(60)
if mode in ('submit', 'silent', 'reject', 'invalid-shape', 'idle', 'loop', 'linger'):
    httpx.get(f'{base}/agent/context', params={'date': day}, headers=headers, timeout=30)
    httpx.post(f'{base}/agent/event', json={'message': 'Reading notes'}, headers=headers, timeout=30)
if mode in ('submit', 'linger'):
    httpx.post(f'{base}/agent/submit', headers=headers, timeout=30, json={'date': day, 'tasks': [{
        'description': 'I reviewed the discharge summary API data with the team and corrected the vitals mapping.',
        'ticket': None, 'evidence': 'Daily note item 1', 'durationMinutes': None}]})
if mode in ('idle', 'linger'):
    time.sleep(60)
if mode == 'loop':
    for _ in range(6):
        httpx.post(f'{base}/agent/event', json={'message': 'Reading the same file'}, headers=headers, timeout=30)
    time.sleep(60)
if mode == 'reject':
    for _ in range(3):
        httpx.post(f'{base}/agent/submit', headers=headers, timeout=30, json={'date': day, 'tasks': [{
            'description': 'too short', 'ticket': None, 'evidence': 'x', 'durationMinutes': None}]})
    time.sleep(60)
if mode == 'invalid-shape':
    for _ in range(3):
        httpx.post(f'{base}/agent/submit', headers=headers, timeout=30, json={'date': day, 'tasks': [{}]})
    time.sleep(60)
if mode == 'fail':
    sys.exit(3)
