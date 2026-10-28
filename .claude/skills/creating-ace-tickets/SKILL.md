---
name: creating-ace-tickets
description: Use when the user asks to create, draft or fill ACE tickets/tasks (New Task, TaskPageN, ASPL numbers) for their work, or when changing the Create tasks / Ticket ideas ticket flow in this app.
---

# Creating ACE tickets

## Overview

An ACE ticket is created on the New Task form (`/Tasks/TaskPageN.aspx?Mpg=P171`). The user reviews every field
before anything reaches ACE, and ACE gets **saved only for tickets the user ticked and explicitly asked to create**.

## Field values for the user's own work

| Field (ACE id suffix) | Value |
|---|---|
| Task Type (`ddlTaskType`) | `New Requirement` (or `Change/Enhancement`, `Functional`, `Bug` when the work clearly is one) |
| Priority (`ddlPriority`) | `Medium` unless the work says otherwise |
| Client (`ddlTaskClientName`) | `Augastam (New Product)` (ACE text may carry a trailing space; snap to the exact option) |
| Module (`ddlTaskModule`) | `Augastam ai` |
| FRD Nature (`ddlASPLPriority`) | `Medium` (the user calls it "FLD") |
| Status (`ddlstatusset`) | `Open`; `Completed` only when the user answers **yes** to "Have you completed this?" |
| Target date (`RadDateTimePicker1`) | next working day 18:00 (1–3 days for bigger work), `YYYY-MM-DDTHH:MM`. **Never earlier than now:** ACE answers "Target date can not be less than current date" and saves the current time instead. Past work days (`workDate`) are shown to the user only. ACE sets Assigned Date itself on save |
| Effort (`txtEfforts`) | days; from time spent (minutes ÷ 480, min 0.25) or size |
| Keyword (`txtKeyword`) | 2–3 words, comma separated, **≤ 25 characters** (ACE silently cuts longer text) |
| Description (`txtNote`) | the field that matters: clear, complete, factual — what, where in the product, what was/must be done. ACE sets no maxLength; the app caps it at 4000 chars |
| Client Remarks (`TextBox1`), Employee Remarks (`txtEmployeeRemarks`) | exactly `.` |
| Assign To (`chlstEmployee` checkbox) | `ACE_ASSIGNEE` (default `Vineet Kukreti`) ticked |

Working days are Monday–Saturday; only Sunday is off.

## Workflow

1. **Check existing tickets first.** Compare the work with the user's assigned tickets (`runtime/tickets_cache.json`,
   or `GET /tickets`). Work an assigned ticket already covers gets no new ticket — report it as "already covered by
   ASPL-…".
2. **Draft** one ticket per distinct piece of work with the values above and show them to the user, with any open
   questions (priority, completed or not).
3. **Wait for the user's review.** They may edit fields and pick some or all tickets.
4. **Create only what they picked**, only after they say to: in the app that is `POST /tasks/create`
   ("Create selected in ACE"); `POST /tasks/fill` ("Fill only") fills and verifies without saving.
5. After Save ACE shows green "Saved" and clears the form, with **no ticket number**. Find the new ASPL number in
   the Assigned list by description (`match_new_tickets`) and report it.

## Never

- Save a ticket the user didn't select, or save a timesheet (daily task report) — those are never saved.
- Re-save a ticket after an unclear result: check the user's Assigned list first, or ACE gets a duplicate.
- Write file names, paths or commit hashes into the description.

## In the code

`backend/app_tasks.py`: `make_task_drafts` (agent drafting, `existingTicket`), `ticket_drafts_for_timesheet`,
`short_keyword`, `TaskCreator.fill(drafts, save)` (`saved` dict prevents duplicates), `match_new_tickets`.
Frontend: `frontend/src/tasks.jsx` (review, pick, create), `frontend/src/ticket-ideas.jsx`, helpers in `plan.js`.
