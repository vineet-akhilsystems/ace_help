"""Antigravity PreToolUse hook for headless ACE drafting: only ace-timesheet MCP calls may run."""
import json
import sys

try:
    call = json.load(sys.stdin).get('toolCall', {})
except ValueError:
    call = {}
allowed = call.get('name') == 'call_mcp_tool' and 'ace-timesheet' in json.dumps(call.get('args', {}))
print(json.dumps({'decision': 'allow'} if allowed else
                 {'decision': 'deny', 'reason': 'ACE drafting runs may only use the ace-timesheet tools.'}))
