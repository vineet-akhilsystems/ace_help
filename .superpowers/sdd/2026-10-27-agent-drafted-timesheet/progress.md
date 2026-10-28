# SDD ledger — plan: docs/superpowers/plans/2026-10-27-agent-drafted-timesheet.md
Ruling: no git repo — backup tar at scratchpad/backup-pre-agent; checkpoints = full test suite — cost if wrong: none
Task 3: Ruling: rules.voice is an adapted paraphrase of the providers.gemini voice paragraph (evidence wording, no example names) — reads cleaner for agents — cost if wrong: one string edit
Task 3: Ruling: never-readable predicate lives in safe_fs.is_blocked_name (created in Task 3) — shared by context scan and file tools — cost: none
Task 6: Ruling: scan_root moved to safe_fs (re-exported by agent_context) — keeps the MCP server process free of Playwright imports — cost: none
Task 6: Ruling: ACE_BACKEND_URL env override in mcp_server.backend_url — lets tests/smoke runs target a second backend without rewriting runtime/port.json used by the live app — cost: none
Task 6: Ruling: day context keeps only the user's own commits (author matches ACE_GIT_AUTHOR, default vineet) and groups changed files per repo/project, dropping repo files changed only by pulled colleague commits — smoke test showed colleagues' pulled work would otherwise be attributed to the user (spec anti-goal) — cost if wrong: user commits under another author name are missed
Task 6: note: test_loose_files_group_by_project_folder was written after the grouping change (not watched failing); old per-parent grouping would have split video/a/b and video/c, so it discriminates
Task 6: complete (tests: pytest tests/test_mcp_server.py tests/test_agent_context.py → pass; stdio smoke: 7 tools + prompt, context 2.8s, .env refused)
Task 1: complete (pytest planner/rules/browser_fill 52 pass)
Task 2: complete (3 pass; live 21 tickets/13 completed)
Task 3: complete
Task 4: complete (5 pass)
Task 5: complete (14 pass)
Task 7: Ruling: ActiveRun.events is a deque (not asyncio.Queue) — request handlers and the runner may sit on different loops/threads; runner polls every 0.5s — cost: none
Task 7: Ruling: the agent prompt is one line and the skill text is delivered as `instructions` inside get_day_context — multi-line prompts get mangled through Windows .cmd shims (codex, gemini) — cost if wrong: agent ignores instructions field (prompt tells it to follow them)
Task 7: complete (tests: pytest tests/test_agent_runner.py → 10 pass)
Task 8: Ruling: agy recipe drops --mode plan/--disable-slash-commands (plan has no effect with slash commands disabled and blocked MCP calls); read-only comes from headless auto-deny + per-tool allow rules mcp(ace-timesheet/<tool>) written by setup_agents.ps1 into ~/.gemini/antigravity-cli/settings.json (backup in scratchpad) — cost if wrong: none observed; write_file and command were auto-denied in probes
Task 8: Ruling: codex recipe adds --disable shell_tool, default_tools_approval_mode="approve" and env_vars=["ACE_BACKEND_URL"] — shell could read outside akhil_system; MCP calls needed approval — cost: none
Task 8: Ruling: gemini not verified (IneligibleTierError on this account); hidden from the dropdown
Task 8: complete (real drafts for 2026-10-26: agy 102s/3 tasks, claude 52s/4 tasks, codex 55s/3 tasks; write probes blocked for all three; pytest test_agent_runner 11 pass)
Task 8: Ruling: agy recipe drops --mode plan/--disable-slash-commands (plan has no effect with slash commands disabled and blocked MCP calls); read-only comes from headless auto-deny + per-tool allow rules mcp(ace-timesheet/<tool>) written by setup_agents.ps1 into ~/.gemini/antigravity-cli/settings.json (backup in scratchpad) — cost if wrong: none observed; write_file and command were auto-denied in probes
Task 8: Ruling: codex recipe adds --disable shell_tool, default_tools_approval_mode="approve" and env_vars=["ACE_BACKEND_URL"] — shell could read outside akhil_system; MCP calls needed approval — cost: none
Task 8: Ruling: gemini not verified (IneligibleTierError on this account); hidden from the dropdown
Task 8: complete (real drafts for 2026-10-26: agy 102s/3 tasks, claude 52s/4 tasks, codex 55s/3 tasks; write probes blocked for all three; pytest test_agent_runner 11 pass)
Task 9: Ruling: unedited in-view plans are replaced automatically by a chat-path draft (plan: mergeIncomingDraft replaces when not edited); edited plans or other dates get the Load notice — cost if wrong: an untouched plan is swapped without a click
Task 9: complete (npm test 21 pass; npm run build ok)
Task 10: complete (UI on test port 8799: Load of chat-path draft for 26 Oct works; Draft with agent (Antigravity) for 27 Oct → 4 tasks in ~95s with Based-on lines; filled-day and Sunday guards return reasons; pytest + npm test green)
Task 10: fix: separate agentRunning label so Create my plan does not show Planning in progress during agent runs; agent row wraps
Final: Ruling: test_day_context_keeps_only_own_commits used relative repoPath 'p' (resolves into the project folder, now excluded); fixture changed to a tmp path — test intent unchanged
Final: user request mid-run: ace_portal_automation (the assistant itself) is excluded from scans, commits and file tools (excluded_folders(): ROOT + AGENT_EXCLUDE) — tests test_assistant_project_is_never_reported, test_default_exclusion_is_this_assistant, test_excluded_folder_cannot_be_opened RED→GREEN
Final: fixed I3 secrets readable (dot-names, *.env, credentials, case-insensitive git pathspecs) — test_refuses_dot_folders_and_credential_files, test_git_show_hides_secrets_case_insensitively RED→GREEN
Final: fixed I5 claude --tools "" (canary not leaked) and agy isolated workspace hook denying all but ace-timesheet MCP + allow-list preflight (canary not leaked; before fix it LEAKED) — tests test_claude_has_no_builtin_tools, test_antigravity_refuses_extra_allow_rules, test_antigravity_runs_from_hooked_workspace RED→GREEN
Final: added server-side read budget (25/run) after agy made 46 reads and timed out — test_read_budget_forces_writing RED→GREEN; default timeout 480s
Final: fixed I1 filled/leave days skipped before any agent starts; rejected-only runs raise with reasons — test_skip_reason_before_spawning_agent RED→GREEN
Final: fixed I4 notes payload — vitest single-day run keeps typed notes RED→GREEN
Final: fixed I2 per-date edited tracking (incl. adjust-long-day) — no unit test (component state); build ok
Final: fixed I6 shared range notes prefixed with scope + warning — no dedicated test (time-boxed at user request)
Final: minor (deferred): M1 junction walk, M2 slow repo 500 → wrong advice, M3 git status index lock, M4 partial range results on error, M5 chat traffic attributed to UI run, M6 out-of-view load discards edits, M7 DB creds inherited by agents, M8 ticket limit 5000, M9 stderr not logged, M10 sync taskkill, M11 bounded read, M12 author match consistency, M13 shared agent_mcp.json, M14 pyodbc unpinned/.env.example keys
