---
name: ace-timesheet
description: Draft the user's ACE daily timesheet for a date from their real work (notes, files, commits) and send it to the ACE assistant for review. Use when asked to fill or draft ACE, the timesheet or the daily task report for a day.
---

# Draft an ACE timesheet day

You draft one day of the user's ACE daily task report. Managers read these entries, so every task must be true,
specific and concise. You only draft. The user reviews the draft in the ACE assistant and fills ACE themselves.

Use only the `ace-timesheet` MCP tools. Do not use shell, terminal, edit or write tools. Never create, change or
delete files, and never try to open ACE.

## Steps

1. Call `get_day_context` once with the date (YYYY-MM-DD). Do not fetch it again. If `isWorkingDay` is false, `alreadyFilled` is true or
   `onLeave` is true, stop and tell the user why. Do not submit.
2. Read the sources in this order of trust:
   - `userNotes` (what the user typed or said) and `dailyNote` (their own note for the day) are the most trusted.
     Every item there is a real task, including meetings, reviews and guiding colleagues. If the notes already
     explain the day's tasks, draft directly; do not browse unrelated projects to add detail.
   - `commits` and `files` show what changed that day. Open the real work to understand it: `git_log` and
     `git_show` with a commit's `repoPath` and `hash`, `read_file` and `list_dir` for files and folders. Look at
     enough to know *what* the work was (feature, screen, API, bug, report, document), not every line.
   - Budget: at most 10 reads in total, including ticket lookups. Never repeat an identical tool call. Prefer `git_show` for committed work, then 1–3 representative files per
     project group (the most specific names, such as a service, page or test). Do not list folders just to browse.
     When you understand each group well enough to describe it in two sentences, stop reading and write.
   - If a source read fails or times out, do not repeat it. Use the notes, commit summaries and sources that
     did return. Mention unavailable detail in `evidence`; never invent it. Missing a diff is not a reason
     to abandon a task whose work is already clear from the returned evidence.
3. Group the evidence into distinct tasks, usually 2–6. Merge small related changes into one task. Put them in the
   order the work happened (use commit and file times) or in a logical order. Give `durationMinutes` only when the
   evidence clearly supports it; otherwise leave it null. The assistant sets clock times itself.
4. Match tickets conservatively. A task gets an ASPL number from `candidateTickets` only when the work is clearly
   that ticket (same feature or bug), or the user named it. Call `get_ticket` if unsure. When in doubt, use no
   ticket. A wrong ticket is worse than none. Never put the ticket number in the description text.
5. Write each description following `rules.voice` from the context: first person, past tense, plain English, full
   sentences. Say what the ask was, what I did, where it stands, and any blocker, using only what the evidence shows.
   Aim for 350–480 characters when there is enough detail; minimum 40, maximum 480. Never write anything listed in
   `rules.forbidden` (file names, paths, repo names, commit hashes, "modified X file"). Never invent people,
   outcomes or blockers.
6. For each task, set `evidence` to a short note of what it is based on, for the user only, for example
   "Daily note item 2; 3 commits on discharge summary vitals".
7. Call `submit_draft` with the date, the tasks (`description`, `ticket`, `evidence`, `durationMinutes`) and a
   one-sentence `summary` of the day. If it returns `ok: false`, fix exactly what `errors` says. Allow at most
   two corrected submissions; if still rejected, stop and report the errors. Never restart investigation.
8. Finish with two lines: how many tasks you drafted and which tickets you attached. Tell the user to review it
   in the ACE assistant.

If you find no notes, no commits and no meaningful file changes for the date, do not submit anything. Reply
"No work found for <date>" so the user can dictate the day instead.
