---
name: creating-project-skills
description: Use when the user asks for a new skill, guide or reusable instructions for this ACE project, or when a hard-won fact about ACE, the agents or the app should be written down for future sessions.
---

# Creating skills for this project

## Two kinds of skill live here

| Kind | Location | Read by | Rules |
|---|---|---|---|
| Developer skills (how to work on this repo) | `.claude/skills/<name>/SKILL.md` | Claude Code sessions in this repo | anything useful to a developer agent |
| The timesheet-drafting skill | `agent/ace-timesheet/SKILL.md` | the agents the app launches (via the `get_day_context` `instructions`) and chat agents (copied by `setup_agents.ps1`) | tools-only: no shell, no writes, no ACE; edits need tests (testing-agent-drafts) and a rerun of `setup_agents.ps1` |

Never put developer instructions into `agent/ace-timesheet/SKILL.md`; the drafting agents must stay read-only.

## Writing one

**REQUIRED BACKGROUND:** superpowers:writing-skills (format, description rules, testing).

- Folder and `name`: lowercase, hyphens, verb-first (`debugging-ace-fills`).
- `description`: starts "Use when…", lists triggers and symptoms (error texts, UI labels, file names); never a
  summary of the steps.
- Body under ~500 words: overview, a table to scan, one example, common mistakes. Point to code by path and
  function name instead of copying it.
- **Only verified facts.** ACE behaviour must have been observed (read-only probe, the audit log, a user
  screenshot); mark anything unverified as such. Example: Keyword max 25 chars was measured, not guessed.
- Cross-reference other skills by name (`verifying-ace-app`), not with `@` paths.
- No secrets, no colleague names copied from real data, no real ticket text.

## Testing a new skill

Give a fresh subagent a realistic task that needs the skill (e.g. "the user says 'ACE did not keep: module' —
what do you check?") with only the repo, and see whether it finds and applies the skill correctly. Fix gaps it
hits, then list the skill in CLAUDE.md if it covers a core workflow.

## Current skills

creating-ace-tickets, driving-ace-portal, verifying-ace-app, debugging-ace-fills, testing-agent-drafts,
testing-voice-transcription, optimizing-agent-prompts, extending-ace-assistant, creating-project-skills.
Update this list when adding one.
