# ACE Portal (Akhil Systems) — Full System Map + Automation Plan

Site: `http://ace.akhilsystems.com`  ·  User: **Vineet Kukreti** (Dept: ADMINISTRATION)
Explored: 2026-09-23. You are logged in; the session is live.

Tech stack: **ASP.NET WebForms + Telerik RadControls** (RadComboBox, RadDateInput, RadTimePicker). Dropdowns are NOT plain HTML `<select>` — they are widgets, so automation drives them via clicks or the Telerik client API, not by setting `.value`.

---

## PART 1 — SITE MAP (every page / button explored)

### Global top nav (on every page)
`HOME` · `Documents` · `Search` · `Logout` (top-right). Left edge has a collapsible category tree.

### Page A — Daily Task Report (Timesheet)
`http://ace.akhilsystems.com/TimeSheet/TimeSheet.aspx?Mpg=P3`
This is where you log your day. Top buttons: **New**, **Save**, and **Date of Report** (date picker). One entry row + a grid of added rows. Buttons per grid row: **Edit**, **Remove**. Bottom: **Add Row**, running **Total Hour**.

### Page B — Tasks / Tickets
`http://ace.akhilsystems.com/Tasks/TaskPageN.aspx`
Three top buttons:
- **Assigned** — tickets assigned **to you** (your inbox).
- **Sent** — tickets **you** created/assigned to others.
- **New Task** — opens the create-ticket form.

Ticket list columns: Ticket No, Client Name, Module Name, Task Type, AMC DueDate, InSupport, Status, Priority, ASPL Priority, Task Description, Assigned By, Target Date, Assigned Date, DueTime, File, and a **Select** link (opens the ticket to update it).

Your current Augastam tickets:
| Ticket | Task Type | Status | Priority | Assigned By |
|--------|-----------|--------|----------|-------------|
| ASPL-169999 | Bug | Open | High | Satyendra Kumar Prajapati |
| ASPL-169209 | Change/Enhancement | Open | High | Vineet Kukreti |
| ASPL-168271 | Change/Enhancement | Completed | Immediate | Vineet Kukreti |

---

## PART 2 — TIMESHEET FORM (field export)

| Field | Control | Element ID |
|-------|---------|-----------|
| Name of Client | RadComboBox (~340 opts) | `ctl00_ContentPlaceHolder1_ddlClientName` |
| Task Name | RadComboBox (24 opts) | `ctl00_ContentPlaceHolder1_ddlTaskName` |
| Module | RadComboBox (~100 opts) | `ctl00_ContentPlaceHolder1_ddlModule` |
| Work Place | RadComboBox (Office/Client/Home) | `ctl00_ContentPlaceHolder1_ddlWorkPlace` |
| Task Description | RadTextBox, max 500 chars | (textarea) |
| Start Time | RadTimePicker | `ctl00_ContentPlaceHolder1_RadTimeFrom` |
| End Time | RadTimePicker | `ctl00_ContentPlaceHolder1_RadTimeEnd` |
| Date of Report | RadDateInput | `ctl00_ContentPlaceHolder1_RadReportDate` |

**Task Name options:** Analyzing, Application Deployment, Bug, Conduct Interview, Configuration, Critical Issue, Data Import, Demo, Design, Discussion Only, Documentation, Enhancement, HIS Enquiry, HTML, Machine Interface, Meeting, Merging, **New Requirement**, News Update, Online/Offline Support, Testing, Through Change Request, Training.
**Work Place options:** Office, Client, Home.

---

## PART 3 — CREATE / UPDATE TICKET (Page B forms — field export)

### New Task form (click **New Task**)
Left panel: **Assign To: Employee** — a checkbox list of **188 employees** (check one or more to assign; "Vineet Kukreti" = assign to yourself).

| Field | ID (prefix `ctl00_ContentPlaceHolder1_Tasks1_`) | Required |
|-------|-----|:--:|
| Task Type | `ddlTaskType` | ✓ |
| Priority | `ddlPriority` | ✓ |
| Client Name | `ddlTaskClientName` | ✓ |
| Module | `ddlTaskModule` | ✓ |
| FRD Nature | (ASPL Priority) `ddlASPLPriority` | |
| Target Date | RadDateTime | ✓ |
| Effort in Days | `` (textbox) | ✓ |
| Keyword | textbox | ✓ |
| Description | `txtNote` | ✓ |
| Client Remarks | `TextBox1` | ✓ |
| Employee Remarks | `txtEmployeeRemarks` | ✓ |
| Change Task Status | `ddlstatusset` | |
| **Save & Leave Open** | `Save` (button) | |

**Task Type options:** Bug, New Requirement, Query, Change/Enhancement, Activity, Publish, Functional, Code Merging, Integration, Interface.
**Priority / ASPL Priority options:** Low, Medium, Immediate, High.
**Status options:** Open, Working, Completed, Delivered, Verified, Tested, Halt, Not Feasible, Cancel, Re-Open, Quotation Sent, Quotation Approved, Delivered On UAT, Auto-Verified, Point Discussed, New Requirement, Change Request, Pending At Business, Publish, Under Discussion, Delivered On QA, UAT Approved, QA Approved, Assigned.

### Update Task (click **Select** on a ticket row)
Same form, pre-filled, header shows `TicketNo / Current Task Status / AssignedBy`. Button is **Update** (not Save).
- **To assign a ticket to yourself/someone:** check the person in the left list → Update.
- **To submit "I have done the ticket":** set **Change Task Status → Completed** (or Delivered), fill **Employee Remarks**, click **Update**.

### ~100 Modules (Augastam-relevant subset)
Augastam - Administration, Augastam - ATD, Augastam - Billing, Augastam - Registration, **Augastam ai**, Augastam EMR. (Full list also covers ABDM, ACE, ACE Portal, Appointment, Billing, Blood Bank, EMR, Emergency, Inventory, LIS, MRD, Pharmacy, Radiology, etc.)

---

## PART 4 — YOUR RULES (for the timesheet tool)

**Fixed defaults (every entry):**
- Client Name = **`Augastam (New Product)`**  *(exact string — you say "Augastam New Product")*
- Module = **`Augastam ai`**
- Task Name = **`New Requirement`**  *(unless a task is clearly a bug → could be `Bug`)*

**Work Place (day-of-week rule):** **Friday → Home; all other days → Office.**

**Task Description:** written up to **500 characters** from what you dictate.

**Times:**
- Start time picker **defaults to 10:00** → use **~10:00 (or 09:45)**.
- End time: **after 19:00 but not beyond 19:30**.
- So a full single-task day ≈ **09:45 → 19:15** (~9.5h). Total must be **≥ 9 hours**.

**Multiple tasks / auto time math:**
- Segregate each spoken task into its own row (intelligence: "next task", "then", "after that" → new row).
- If you give durations ("2 hours on X, 3 hours on Y"), chain them: start at 10:00, each task's end = start + duration, next task starts where previous ended. E.g. Task1 10:00→12:00, Task2 12:00→15:00, etc., padded so the day still totals ≥9h and ends ≤19:30.
- If you give no times, split the ~9.5h window evenly across the tasks.

**With vs without ticket:**
- With ticket → reference `ASPL-xxxxx` in the description; optionally also go update that ticket's status.
- Without ticket → plain description.

---

## PART 5 — THE TOOL (what we'll build)

Goal: a **voice-first panel** — you press a mic, say everything you did today, and it fills + reviews the timesheet, then you confirm and it saves.

**Flow:**
1. **Speak** → transcript (Web Speech API in browser, or you type/paste).
2. **Parse** (intelligence layer): split into tasks, extract durations/times, detect ticket numbers, pick Task Name, apply the Friday/Home workplace rule, compute contiguous start/end times summing to ≥9h within 09:45–19:30.
3. **Preview card**: shows each row (client/task/module/workplace/description/start/end/total) for you to eyeball/edit.
4. **Fill**: automation drives the Telerik combos + time pickers + Add Row for each task on the correct Date of Report.
5. **Save**: I always pause and ask before clicking Save (irreversible submit).

**Two build options for the panel:**
- **(Recommended) A local HTML tool** (single file) with the mic + preview, that outputs a clean structured plan; I then drive the browser to fill it. Fast to iterate, no server.
- A fuller app if you want history/one-click repeat later.

The browser-fill automation uses the exact element IDs above; combos are set via `$find(id).findItemByText(text).select()` with a UI-click fallback.

---

## OPEN QUESTIONS before first live run
1. **Workplace:** Friday = Home, all other days = Office. (Today 2026-09-23 is a Tuesday → Office.) ✓ confirmed
2. For a **bug** you did, keep Task Name = `New Requirement`, or use `Bug`?
3. Default window **09:45 → 19:15** OK, or a specific end you prefer?
4. Should the tool also **auto-update the ticket status** (e.g. mark ASPL-xxxxx Completed) when you mention finishing it, or only fill the timesheet for now?
5. Voice input: build the **mic panel** now, or start with type/paste and add mic after the fill logic works?
