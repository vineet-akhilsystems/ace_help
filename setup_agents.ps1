# Connects every installed coding agent to the ace-timesheet MCP server and installs the ace-timesheet skill.
# Safe to run again: each server is removed and re-added.
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$shim = Join-Path $PSScriptRoot 'ace_timesheet_mcp.py'
$skill = Join-Path $PSScriptRoot 'agent\ace-timesheet'
if (-not (Test-Path $python)) { throw 'Run start.ps1 once first so the Python environment exists.' }

function Installed($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Report($agent, $ok, $note) { Write-Host ("{0,-12} {1}  {2}" -f $agent, $(if ($ok) { 'ok' } else { 'FAILED' }), $note) }
function CopySkill($folder) {
    New-Item -ItemType Directory -Force (Join-Path $folder 'ace-timesheet') | Out-Null
    Copy-Item (Join-Path $skill 'SKILL.md') (Join-Path $folder 'ace-timesheet\SKILL.md') -Force
}

if (Installed 'claude') {
    claude mcp remove ace-timesheet --scope user 2>$null | Out-Null
    claude mcp add --scope user ace-timesheet -- $python $shim | Out-Null
    $ok = $LASTEXITCODE -eq 0
    CopySkill (Join-Path $HOME '.claude\skills')
    Report 'Claude Code' $ok 'MCP server + skill (~\.claude\skills\ace-timesheet)'
}
if (Installed 'agy') {
    agy mcp remove ace-timesheet 2>$null | Out-Null
    agy mcp add ace-timesheet $python $shim | Out-Null
    $ok = $LASTEXITCODE -eq 0
    # Headless agy auto-denies tools without an allow rule; allow only the ace-timesheet tools.
    & $python -c @'
import json, pathlib
path = pathlib.Path.home() / '.gemini' / 'antigravity-cli' / 'settings.json'
data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
allow = data.setdefault('permissions', {}).setdefault('allow', [])
allow[:] = [rule for rule in allow if not rule.startswith('mcp(ace-timesheet')]
allow += [f'mcp(ace-timesheet/{tool})' for tool in ('get_day_context', 'get_ticket', 'submit_draft', 'list_dir',
                                                    'read_file', 'git_log', 'git_show')]
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2), encoding='utf-8')
'@
    Report 'Antigravity' ($ok -and $LASTEXITCODE -eq 0) 'MCP server + permission mcp(ace-timesheet) (instructions arrive with get_day_context)'
}
if (Installed 'gemini') {
    gemini mcp remove --scope user ace-timesheet 2>$null | Out-Null
    gemini mcp add --scope user --trust ace-timesheet $python $shim | Out-Null
    $ok = $LASTEXITCODE -eq 0
    gemini skills uninstall ace-timesheet 2>$null | Out-Null
    gemini skills link $skill --consent 2>$null | Out-Null
    Report 'Gemini CLI' $ok 'MCP server (trusted) + linked skill'
}
if (Installed 'codex') {
    codex mcp remove ace-timesheet 2>$null | Out-Null
    codex mcp add ace-timesheet -- $python $shim | Out-Null
    $ok = $LASTEXITCODE -eq 0
    CopySkill (Join-Path $HOME '.codex\skills')
    Report 'Codex' $ok 'MCP server + skill (~\.codex\skills\ace-timesheet)'
}
Write-Host ''
Write-Host 'Done. Keep the ACE assistant running (start.ps1), then ask your agent: "fill my ACE for <date>".'
