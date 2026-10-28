# ACE portal reference (for Playwright automation)

Base URL: `http://ace.akhilsystems.com` (plain HTTP). Probed read-only on **2026-10-28** as user Vineet Kukreti,
using `backend.app_session.Session().background()` (headless Chrome, saved `runtime/storage_state.json`).
Nothing was saved, updated or deleted; every POST was passed through a guard that aborted anything naming a
Save/Update/Delete/Add/Remove-style control.

Legend: **[O]** observed directly in the live DOM/behaviour; **[C]** taken from this repo's code (works in
production but not re-tested here); **[I]** inferred, not verified.

Raw dumps (JSON, HTML, screenshots) and the probe scripts are in `runtime/portal_dump/` (gitignored).
`runtime/portal_dump/scripts/probe.py` is a reusable read-only harness (write-blocking route guard + DOM dumpers).

---

## 1. Platform basics

| Item | Detail |
|---|---|
| Stack | ASP.NET WebForms, one `<form>` per page posting to itself, `__VIEWSTATE`, `__doPostBack`, ASP.NET AJAX `UpdatePanel`s **[O]** |
| Widgets | Telerik RadControls: `RadComboBox`, `RadDatePicker`, `RadDateTimePicker`, `RadTimePicker`, `RadSplitter`/sliding panes, `RadWindowManager` **[O]** |
| Widget access | `window.$find(clientId)`; all combos are listed in `Telerik.Web.UI.RadComboBox.ComboBoxes` **[O]** |
| ID prefixes | Page content: `ctl00_ContentPlaceHolder1_`. Task page user control: `ctl00_ContentPlaceHolder1_Tasks1_` (`T` in `backend/app_tasks.py`) **[O]** |
| `name` vs `id` | Names use `$` (`ctl00$ContentPlaceHolder1$Tasks1$Save`), ids use `_` **[O]** |
| Async postback idle check | `Sys.WebForms.PageRequestManager.getInstance().get_isInAsyncPostBack()`; `backend/app_timesheet.settle()` waits for networkidle plus this flag **[O/C]** |
| Time zone | Server time is IST; New Task "Target Date" defaults to *now* IST with seconds **[O]** |
| Layout | Content is inside fixed-size Telerik splitter panes (`ctl00_RadSplitter1`, `ctl00_MiddlePane1`). Page `full_page` screenshots stop at the viewport (950px); the grid continues inside the pane **[O]** |

### Login page `/login.aspx`

| Control | id | Notes |
|---|---|---|
| User | `txtUserID` | text |
| Password | `txtPassword` | password |
| Submit | `btnLogin` | value "Log in" |

* DOMContentLoaded in about 0.7s; the full `load` event took about 5s (large background image) **[O]**. `Session.navigate` therefore waits for
  `domcontentloaded` only (45s timeout) **[C]**.
* The login form can come back a second time after the first submit; `Session.login` submits up to 3 rounds until no
  password field remains **[C]**.
* Detecting the login page: `input[type=password]` present **[C]**.
* Logout is `window.location='/login.aspx?Logout=1'` (top bar `ctl00_pd1_a1`). **Never click it**: it would kill the shared session **[O]**.

---

## 2. Site menu and page map

There are two master-page layouts:

* **Main master** (TaskPageN, TimeSheet): a collapsed left sliding pane "Menu" (`ctl00_rsp1`) holds a module list
  grid `ctl00_gvModules` (rows posted with `__doPostBack('ctl00$gvModules','Select$N')`) and a page tree
  `ctl00_tvCategory` whose leaf links call `showDia('<url>')` (just `window.location = url`).
  Selecting a module POSTs, gets a **302 to that module's landing page**, and the selection is kept **in the server session**: the
  tree then shows that module's pages everywhere **[O]**. (The probe restored "Tasks" afterwards.)
* **Alternate master** (Release Report, Change Password, Client Issues): a full dropdown menu with absolute links (no Mpg) **[O]**.

Top bar (main master, `ctl00_pd1_*`): `HOME` → `../dashboard-new.aspx`, `Documents` → `../MPages/DriveLinkSearch.aspx`,
`Search` → `../TimeSheet/SearchOptionNameReport.aspx`, `Logout`. The alternate master adds `Support Portal` → `../../home.aspx`.

| Module (gvModules row) | Landing URL after Select | Pages (Mpg code) |
|---|---|---|
| 0 Time Sheet | `/TimeSheet/TimeSheet.aspx?Mpg=P3` | Time Sheet `/TimeSheet/TimeSheet.aspx?Mpg=P3`; Time Sheet Approval `/TimeSheet/TimeSheetApproval.aspx?Mpg=P230` |
| 1 Reports | `/Tasks/ReleaseReport.aspx?Mpg=P209` | Release Report `/Tasks/ReleaseReport.aspx` (P209); Employee Wise Report `/TimeSheet/EmpWiseReport.aspx` (Mpg not seen) |
| 2 Change Password | `/MPages/ChangePassword.aspx?Mpg=P170` | Change Password |
| 3 Tasks | `/Tasks/TaskPageN.aspx?Mpg=P171` | Task `/Tasks/TaskPageN.aspx?Mpg=P171`; Client Summary/Status Report `/Tasks/ClientIssueReport.aspx?Mpg=P176`; Client Issue Report `/Tasks/ClientReport.aspx?Mpg=P182`; Release Master `/MPages/ReleaseMaster.aspx?Mpg=P207`; Dashboard `/dashboard-new.aspx?Mpg=P206`; Call Record Show `/Tasks/CallRecordShow.aspx?Mpg=P215`; Ticket Tracker `/Tasks/CallRecord.aspx?Mpg=P202`; Issue Tracker Report `/Tasks/CallRecordReport.aspx?Mpg=P203` |
| 4 Dashboard | `/mpages/Dashboard.aspx?Mpg=P188` | Dashboard |
| 5 Attach Documents | `/mpages/AttachDocument.aspx?Mpg=P192` | Attach Documents |
| 6 Client Issues | `/ClientIssues/NewRequirement.aspx?Mpg=P216` | New Requirement (has New / Excel / **Save** buttons: write page, not explored) |

The app uses only two pages: **TaskPageN** (`backend/app_tasks.PATH = '/Tasks/TaskPageN.aspx?Mpg=P171'`; `Timesheets.tickets()` opens
it without `Mpg`, which also works **[C]**) and **TimeSheet** (`backend/app_timesheet.PATH = '/TimeSheet/TimeSheet.aspx?Mpg=P3'`).
Going straight to these URLs works without touching the menu **[O]**.

---

## 3. Task page `/Tasks/TaskPageN.aspx?Mpg=P171`

Loads in about 3s with a saved session **[O]**. The default view is **Assigned**. Everything below lives in
`ctl00_ContentPlaceHolder1_Tasks1_UpdatePanel1` (async postbacks).

### 3.1 View buttons (always shown at the top)

| id (suffix after `T`) | Label | Shows | Notes |
|---|---|---|---|
| `btnSent` | **Assigned** | Tickets assigned to me, grid `gvTasks` | The naming is inverted: `btnSent` is labelled "Assigned" **[O]** |
| `btnPosted` | **Sent** | Tickets I created, grid `grvPosted` | **[O]** |
| `btnNewTask` | **New Task** | Blank New Task form | **[O]** |

All three are `input type=submit`, class `buttonBlue`, with no onclick. They are ordinary postbacks. Clicking them through
`el => setTimeout(() => el.click(), 0)` works (see Gotchas). Section headings: "Assigned Tasks" / "Sent Tasks" **[O]**.

### 3.2 Assigned view (`btnSent`, default)

**Filters** (ids are suffixes after `T`):

| Label | id | Type | Default / options |
|---|---|---|---|
| Client Name : | `ddlClientNameSearch` | native `<select>` | blank; 345 clients + blank (same list as New Task) |
| Search On : | `ddlFilter` | native `<select>`, autopostback (`onchange` → `__doPostBack(...ddlFilter)`) | `1` Status (default), `2` Ticket No, `4` Module Name (no 3) |
| (status, when Search On = Status) | `ddlStatus1` | RadComboBox | "All" (value `0`) + 24 statuses (same as §3.4 status list) |
| (when Search On = Ticket No) | `txtTicket` | text | replaces `ddlStatus1` |
| (when Search On = Module Name) | `ddlModuleFilter` | native `<select>` | replaces `ddlStatus1` |
| Task Type | `ddlTaskTypefl` | RadComboBox | "Select Task Type" (value "") + the 10 task types |
| From | `AssignedFromDate` | RadDatePicker, format `dd/MM/yyyy` | **today − 30 days** |
| To | `AssignedToDate` | RadDatePicker | today |
| Search | `btnSearch` | submit | about 0.9s round-trip |

The date range filters on **Assigned Date** **[I: consistent with results]**. Change the dates with
`set_widget(page, 'Tasks1_AssignedFromDate', 'YYYY-MM-DD', 'date')` **[O/C]**.

**Grid `gvTasks`**: 16 columns, in order:

| # | Header | Sort arg | Notes |
|---|---|---|---|
| 0 | Ticket No | – | `<span id=..._gvTasks_ctlNN_lblClientTokenNo>ASPL-173227</span>` |
| 1 | Client Name | `Sort$ClientName` | |
| 2 | Module Name | `Sort$ModuleName` | |
| 3 | Task Type | `Sort$TaskType` | |
| 4 | AMC DueDate | `Sort$PaymentDueDate` | usually blank |
| 5 | InSupport | `Sort$InSupport` | "NO" |
| 6 | Status | – | |
| 7 | Priority | `Sort$TaskPriority` | |
| 8 | ASPL Priority | `Sort$ASPLPriority` | = FRD Nature |
| 9 | Task Description | `Sort$TaskMessage` | full text (seen ~900 chars, not cut) |
| 10 | Assigned By | `Sort$assignedby` | the creator; may contain double spaces ("Vineet  Kukreti") |
| 11 | Target Date | `Sort$DueDate` | `dd/MM/yyyy  h:mmAM` |
| 12 | Assigned Date | `Sort$AssignedDate` | `dd/MM/yyyy` |
| 13 | DueTime | – | e.g. "2 Hr(s) 35 Min(s) Ago", "In 1 Day(s)", blank when Completed |
| 14 | File | – | holds hidden inputs (below) |
| 15 | (blank) | – | `Select` link |

`backend/app_timesheet.Timesheets.tickets()` relies on cells `[0]` ticket, `[2]` module, `[3]` task type, `[6]` status and `[9]` description **[C, matches O]**.

Per-row hidden inputs (`..._gvTasks_ctlNN_<name>`): `hdnTaskStatus1` (status text), `hdnTaskTaskId` (task id, e.g. 187715),
`hdnFileName2`, `hdnEfforts` (effort days), `hdnClientIssueId` (ticket/issue id, e.g. 454867), `hdnSupportRemarks` **[O]**.
Row ids start at `ctl02` for the first data row.

**Paging**: page size **10**. The pager row is `tr.pagination` with links `javascript:__doPostBack('ctl00$ContentPlaceHolder1$Tasks1$gvTasks','Page$N')`;
the current page is a `<span>`. With From = 2020-01-01 there were 4 pages **[O]**.

**Row action**: `Select` → `__doPostBack('...$gvTasks','Select$<rowIndex>')` loads the ticket into the edit form (§3.5). It is read-only by
itself **[O]**.

**Observed quirks**:
* The counter `lblGridStatus` is wrong: "Showing 1 - 10 of 0 Record(s)", "Showing 11 - 0 of 0 Record(s)". Don't parse it **[O]**.
* The same ticket can appear twice (ASPL-172282 was on two rows, identical). De-duplicate by ticket number **[O]**.
* No results renders **one blank data row** (empty cells), not a "no records" message **[O]**.
* **A ticket I created and assigned to myself appears in Assigned** (ASPL-173227, Assigned By = Vineet Kukreti) **and** in Sent **[O]**.
* Ticket No search needs the full `ASPL-172177`. `172177` alone returns nothing. The date range still applies to a ticket search
  (with From = 27/10 the 15/10 ticket was not found) **[O]**.

### 3.3 Sent view (`btnPosted`)

**Filters**:

| Label | id | Type | Options |
|---|---|---|---|
| Search On | `ddlSendFilter` | native select, autopostback | `1` Status, `2` Ticket No, `3` Client Name, `4` Module Name, `5` Assigned To |
| Status (mode 1) | `ddlstatus` | RadComboBox | All + 24 statuses |
| Ticket (mode 2) | `txtSendTicket` | text | |
| Client (mode 3) | `ddlSendClientNameSearch` | native select | |
| Module (mode 4) | `ddlSendModuleFilter` | native select | |
| Assigned To (mode 5) | `ddlAssigneTo` (sic) | native select | |
| From / To | `SendFromDate` / `SendToDate` | RadDatePicker | today − 30 / today (From max = today) |
| Search | `btnSearchSend` | submit | |

**Grid `grvPosted`**: 14 columns: Ticket No, Client Name (`Sort$ClientName`), Module Name (`Sort$ModuleName`), AMC DueDate
(`Sort$PaymentDueDate`), InSupport, Status (`Sort$TaskStatus`), Priority (`Sort$TaskPriority`), ASPL Priority
(`Sort$ASPLPriority`), Task Description (`Sort$TaskMessage`), **Assigned To** (`Sort$EmployeeName`), **Posted Date**
(`Sort$CreatedDate`), DueTime, File, (Select). Compared with Assigned, there is **no Task Type, Assigned By, Target Date or Assigned Date** column, so the
column indexes differ from `gvTasks` **[O]**.
Per-row ids: `lblClientTokenNo`, `lblEmployeeName`, hidden `hdnTaskStatus`, `hdnFileName1`, `hdnEfforts`, `hdnClientIssueId`.
Counter `lblGridStatus1` was correct here ("Showing 1 - 7 of 7 Record(s)"). Page size not observed (only 7 rows) **[I: 10]**.

**WARNING:** `grvPosted` `Select$N` **never returned**. The async postback hung for more than 20s, and afterwards *every* request in
that ASP.NET session (including fresh `page.goto` in other browsers using the same cookies) timed out for about 1–2 minutes **[O, twice]**.
Use the Assigned grid (or a ticket search there) to open a ticket instead.

### 3.4 New Task form (`btnNewTask`)

After `btnNewTask`, the form shows with hidden `hdnTaskId = 0` and the button `Save` labelled **"Save & Leave Open"**.
A left panel holds "Assign To : Employee" (span `rbEmp`) with the checkbox list.

| Label (as shown) | id (suffix) | Control | Required marker | Validator | Default | Notes |
|---|---|---|---|---|---|---|
| Task Type* | `ddlTaskType` | RadComboBox (input readOnly) | * | **none** | **"Bug" (value 1)**, no blank option | Leaving it alone creates a Bug |
| Priority * | `ddlPriority` | RadComboBox (readOnly) | * | `RequiredFieldValidator1` "Select Priority" | blank | Has a postback reference, but selecting via API made no request; hidden `hdnPriority` stayed `0` **[O]** |
| Client Name * | `ddlTaskClientName` | RadComboBox, typing filter = Contains (`filter 1`) | * | `RequiredFieldValidator4` "Select Client Name" | blank | 345 options |
| Module * | `ddlTaskModule` | RadComboBox, filter Contains | * | `RequiredFieldValidator5` "Select Module" | blank | 101 options |
| FRD Nature | `ddlASPLPriority` | RadComboBox (readOnly) | – | none | blank | optional; grid column "ASPL Priority" |
| Target Date* | `RadDateTimePicker1` (+ `_dateInput`, `_dateInput_display`, `_popupButton`, `_timePopupLink`) | RadDateTimePicker, format `dd/MM/yyyy HH:mm` | * | **none** | now (IST, with seconds) | range 1980-01-01..2099-12-31; time popup has whole hours 12:00 AM..11:00 PM. `input.value` is in the internal format `yyyy-MM-dd-HH-mm-ss` |
| Effort in Days* | `txtEfforts` (label span `lblEfforts`) | text | * | **none** | empty | no maxLength |
| Keyword* | `txtKeyword` | text, **maxLength 25** | * | `RequiredFieldValidator7` "Enter Keyword" | empty | stored value is cut to 25 (seen in edit view) |
| Description* | `txtNote` | textarea (rows 2) | * | `rqrtxtNote` "Enter Discription" (sic) | empty | no maxLength attribute; server limit unknown |
| Client Remarks* | `TextBox1` | textarea | * | `rqrtxtRemarks` "Enter Remarks" | empty | |
| Employee Remarks* | `txtEmployeeRemarks` | textarea | * | `RequiredFieldValidator8` "Employee Remarks" | empty | |
| Change Task Status | `ddlstatusset` | RadComboBox (readOnly) | – | none | "Open" (value 11) | Has a postback reference; selecting via API made no request **[O]** |
| Assign To : Employee | `chlstEmployee_0..189` | checkboxes, labels via `c.labels[0]` | – | **none** | none checked | 190 employees, alphabetical; e.g. `ACE Agent` = `_7`, `Admin` = `_10`, `Vineet Kukreti` = `_182`. **Indexes shift when staff change; match by label** (as `TaskCreator.fill_page` does) |
| Save & Leave Open | `Save` | submit, `WebForm_DoPostBackWithOptions(... "ctl00$...$Save", "", true, "SaveTask", ...)` | | | | **Writes. Never click while exploring** |

Other labels on the form (empty on a new task): `lblToken`, `lblstatus`, `lblClientEmail`, `lblConDetail`, `txtassignedby`,
`lblIssueReportedBy`, `lblReopenTicket`, `lblRefTicketNo`, `lblSupportRemarksShow`, `lbltaskMsg` (after Save it shows "Saved" and the
form clears **[C]**), `Label10` "PLEASE WAIT" (hidden progress text).

**Validation** (validation group **`SaveTask`**, all `RequiredFieldValidatorEvaluateIsValid`, `display: None`):
`ValidationSummary1` has `showmessagebox=True`, `showsummary=False`, so missing fields produce a **browser `alert()`** listing them. Running
`Page_ClientValidate('SaveTask')` on a blank form (client-side only, no request) raised this dialog **[O]**:

```
- Select Priority
- Select Client Name
- Select Module
- Enter Keyword
- Enter Discription
- Enter Remarks
- Employee Remarks
```

Task Type, Target Date, Effort and Assign To have **no client validator** even though most are marked `*`. What the server does
with an empty Effort or no assignee is **unknown** (not tested, because that would mean saving).

#### Option lists (text (value))

**Task Type** (10): Bug (1), New Requirement (3), Query (9), Change/Enhancement (10), Activity (11), Publish (12), Functional (13),
Code Merging (14), Integration (15), Interface (16). The same list is in the Assigned filter `ddlTaskTypefl`.

**Priority** (4) and **FRD Nature** (4), in this order: Low (1), Medium (2), Immediate (3), High (4), plus a blank first item.

**Task status** `ddlstatusset` (24): Open (11), Working (12), Completed (13), Delivered (14), Verified (15), Tested (16), Halt (17),
Not Feasible (18), Cancel (21), Re-Open (25), Quotation Sent (26), Quotation Approved (27), Delivered On UAT (28),
Auto-Verified (29), Point Discussed (30), New Requirement (31), Change Request (32), Pending At Business (34), Publish (35),
Under Discussion (36), Delivered On QA (37), UAT Approved (38), QA Approved (39), Assigned (40).
The grid filters `ddlStatus1`/`ddlstatus` have the same list with "All" (0) first.

**Client Name** (345 + blank): examples `Augastam (New Product)` (10531), `Internal Training` (10535), `Care Aurangabad` (8433),
`Akhil Cloud` (8362), `Ovum-Augastam`, `1HPLUS MEDPARK HOSPITAL` (9457). These 13 texts have leading/trailing spaces:
`' Medtrial Interface'` (first item, 8218), `'Cloud LIS '`, `'Dayaram Verma Hospital '`, `'eIcore '`, `'EMR STD Version  '`, `'GUT GI '`,
`'Hanuman Prasad Poddar Cancer Hospital '`, `'LMH Buldi hospital  '`, `'Mission Hospital '`, `'PRO-HEALTH DIAGNOSTIC '`,
`'Sales & Marketing '`, `'Santevita Hospital '`, `'Suraj Prakash Hospital '`. One contains a mojibake character (`Avenue Health Care �Kenya`).
The full list is in `runtime/ace_task_form.json` / `runtime/portal_dump/newtask_form.json`.

**Module** (101): ABDM (4093), ACE (2019), ACE Portal (3081), Administration (17), All Modules (2021), Ambulance (3063),
API Interface (3050), Appointment (16), ATD (3046), Augastam - Administration (4096), Augastam - ATD (4098), Augastam - Billing (4094),
Augastam - LIS (4099), Augastam - Registration (4095), Augastam ai (4097), Augastam EMR (3085), Azure Cloud (3051), Blood Bank (9),
Book Appointment Portal (3075), Clinical Master (2005), Cloud Version (3054), CRM Interface (3056), CSSD (15), 'Customer Connect ' (3088),
'CXO App ' (3086), Dashboards (3078), Database (2011), Database & Hospital setup Configuration (3053), Design Stuff (3089),
Dietry Management (11), Discharge Summary (2013), Doctor Accounting (8), EDC Payment (3049), Emergency (14), EMR (2),
Equipment Management (10), FA Linkage (2032), Facility (2030), GST Update (3087), Home Sample Collection (3064), Housekeeping (3082),
HRD (2025), ICCA Interface (2009), IFS Integration (3065), Insurance (2020), Interface (3057), Internal Meeting (3080), Inventory (4),
IP Billing (1), IVF (2034), 'Kickoff Meeting ' (2045), Linen Laundry (12), LIS (2003), Machine Interface (2017), 'Marketing ' (3059),
'MCI ' (3077), MEETING (2018), MIS App (3079), MIS Dashboard (1003), MMR (3058), MobileApp (2004), MPHRX Integration (3060), MRD (5),
**NABH (3083), NABH (3073)** (duplicate text), New Machine Interfacing (3084), News Update (3055), 'NHCX ' (4092), 'Nurse workbench ' (3068),
OP Billing (21), 'Optical ' (3090), `Oracle - HIS� Interface` (2008, mojibake), OT (7), PACS Integration (2012), Patient Monitor (3048),
Patient Portal (2035), Payment Getway (3052), PHLEBOTOMY (6), QMS (2010), QR Code App (4090), Receivable (2026), Registration (19),
Reports (18), Reports - Billing (3070), Reports - Inventory (3069), 'Reports - Lab ' (3071), RIS (13), Sage Interface (3072),
SAP Interface (3045), Security (2028), SMS (2016), Software Management (2029), 'Support ' (3066), Tally Interface (2031),
'Teleconsulation ' (3061), Tumor Board (4091), Voice OC (3074), `Ward  (Clinical)` (2042, double space), Ward (Non Clinical) (22),
'Whatsapp Integration ' (3076), Word Reporting (3047).
(Quoted items have trailing spaces. The TimeSheet `ddlModule` list is identical.)

### 3.5 Ticket detail / edit view (Assigned grid → `Select`)

`Select` reuses **the same form controls** as New Task, filled with the ticket, and switches the button to **"Update"** (same id
`Save`, same `SaveTask` group) **[O]**. Header labels: `lblToken` "TicketNo: ASPL-173224", `lblstatus` "Current Task Status: Open",
`txtassignedby` "AssignedBy: Amit Kumar Gupta", `lblIssueReportedBy` "Issue ReportedBy: AmitKumar". `hdnTaskId` = the task id
(= grid `hdnTaskTaskId`), `hdnPriority` = priority value.

| Field | Editable in edit mode? (observed on 2 tickets) |
|---|---|
| Task Type, Priority, Change Task Status (`ddlstatusset`) | yes (combo enabled) |
| Client Name, Module | no (combo disabled) |
| FRD Nature | disabled when it already had a value; enabled when blank **[O, n=2]** |
| Target Date | yes |
| Effort, Keyword, Description | readOnly |
| Client Remarks (`TextBox1`), Employee Remarks (`txtEmployeeRemarks`) | yes, **empty** (new remark each update); still required by validators |
| Assign To checkboxes | enabled; current assignee pre-checked (Vineet Kukreti on ASPL-173224) |

History grids shown below the form:
* `gvComments`: SNo., Date Time, Comment Posted By, Client Remarks, Priority Remarks, File Uploded (span ids `gvComments_ctlNN_lblSNo/lblEncodedDatetime/lblCommentPostedBy/lblRemarks`).
* `GvEmpRemarks`: SNo., Date Time, Comment Posted By, Internal Remarks, Assign To (`..._lblAssignTo`).

**Changing status / completing a ticket** (controls only, never executed): choose `ddlstatusset` (e.g. "Completed" = 13), fill
`TextBox1` + `txtEmployeeRemarks` (validators require them), click `Save` ("Update") **[I]**.

> **Automation hazard:** after any `Select`, the `Save` button **updates that existing ticket**. Before a "create" save, always
> click `btnNewTask` first and check `hdnTaskId == '0'` and `Save.value == 'Save & Leave Open'`.

---

## 4. Daily Task Report `/TimeSheet/TimeSheet.aspx?Mpg=P3`

Heading `lblHeader` "Daily Task Report", `lblEmpDetail` "Employee Name: … Department: ADMINISTRATION". Prefix `ctl00_ContentPlaceHolder1_`.

### 4.1 Header controls

| Control | id | Notes |
|---|---|---|
| Date of Report | `RadReportDate` (+ `_dateInput` readOnly, `_popupButton`, `_calendar`, `_calendar_Title`, `_calendar_NP`/`_NN` prev/next month, `_FNP`/`_FNN` fast) | RadDatePicker `dd/MM/yyyy`, **max date = today** (future dates can't be picked). Changing it posts back and reloads the grid. `set_report_date()` drives the calendar popup by clicking days, because `_dateInput` is readOnly **[O/C]** |
| New | `btnNew` | submit, no onclick. Clears the draft grid **[C comment]** |
| Save | `btnSave` | submit, **no client validation**. **Writes** |
| Total Hour | `lblShowTotalSum` | e.g. "09:21" = sum of the saved rows' Total Hours |

### 4.2 Entry row (above the grid)

| Header | id | Control | Options / format |
|---|---|---|---|
| Name of Client | `ddlClientName` | RadComboBox (no typing filter), text "Select" | same 345 clients as TaskPageN (same values) |
| Task Name | `ddlTaskName` | RadComboBox | Analyzing (1016), Application Deployment (1017), Bug (1), Conduct Interview (1023), Configuration (1029), Critical Issue (1011), Data Import (1020), Demo (8), Design (1026), Discussion Only (7), Documentation (1019), Enhancement (2), HIS Enquiry (1025), HTML (1027), Machine Interface (9), Meeting (1012), Merging (1022), New Requirement (1010), News Update (1028), Online/Offline Support (1021), Testing (3), Through Change Request (4), Training (5) |
| Module | `ddlModule` | RadComboBox | identical to the TaskPageN module list |
| Work Place | `ddlWorkPlace` | RadComboBox | Office, Client, Home (value = text) |
| Task Description (Max. 500 Character) | `txtTaskDescription` | textarea, no maxLength attr; `onkeyup="return validateMaxLength(this)"` cuts to 500 chars **only on keyup** | Playwright `fill()` fires no keyup, so longer text is not cut client-side **[I]**. The app limits rows to 500 **[C]** |
| Start Time (HH:MM) | `RadTimeFrom` (+ `_dateInput` readOnly) | RadTimePicker `hh:mmtt` | popup list 01:00AM…11:45PM in 15-min steps (92 items; 12:xxAM not offered). Set through `$find().set_selectedDate()` (`set_widget(..., 'time')`) **[O/C]** |
| End Time (HH:MM) | `RadTimeEnd` | same | |
| Add Row | `btnAdd` | submit, `WebForm_DoPostBackWithOptions(... "ctl00$ContentPlaceHolder1$btnAdd", "", true, "Save", ...)` | adds a **draft** row to the grid (not persisted until `btnSave`) **[C]** |

Validators (group **`Save`**, fired by `btnAdd`): `RequiredFieldValidator1` ddlClientName "Name of Client Cannot Be Blank",
`RequiredFieldValidator2` ddlTaskName "Task Name Cannot Be Blank", `RequiredFieldValidator3` ddlModule "Module Cannot Be Blank",
`RequiredFieldValidator13` ddlWorkPlace "Work Place Cannot Be Blank", `RequiredFieldValidator4` txtTaskDescription "Task Description Cannot Be Blank",
`RequiredFieldValidator5` RadTimeFrom "Start Time Cannot Be Blank", `RequiredFieldValidator6` RadTimeEnd "End Time Cannot Be Blank".

### 4.3 Grid `gvEntries`

11 headers: Sno, Name of Client, Task Name, Module, Work Place, Task Description (Max. 500 Character), Start Time (HH:MM),
End Time (HH:MM), Total Hours, Edit, Remove. `Timesheets.grid()` checks for 11 headers with `headers[1] == 'Name of Client'` **[C/O]**.
Times display as `9:45AM`, totals as `02:30`.

Per-row controls (`gvEntries_ctlNN_*`):
* Links (all postbacks): `lnkTotalHour` (the Total Hours value), `lbtnEdit` "Edit", `lbtnRemove` "Remove". **Remove writes or alters the
  draft. Edit loads the row into the entry fields [I]. Not clicked.**
* Hidden: `hdnId`, `hdnRowId`, `hdnTaskStatusId`, `hdnClientIssueId`, `hdnTicketId`, `hdnOptionName`, `hdnclientid`, `hdnTaskID`, `hdnModuleID`, `hdnWorkPlace`.

**Saved rows vs ACE-injected ticket rows** (observed on 27/10, 28/10 and 21/10):

| | Saved timesheet row | Injected ticket row |
|---|---|---|
| `hdnRowId` | real id (e.g. 697281) | **`0`** |
| Start / End | entered times | **both = current clock time at page load** (e.g. 9:57PM on every date) |
| Total | real | `00:00` |
| Description | as entered | `"ASPL-nnnnnn" <ticket description>` (ticket in double quotes) |
| `hdnTicketId` / `hdnClientIssueId` | empty / 0 | ticket's issue id (= TaskPageN `hdnClientIssueId`) |
| `hdnTaskStatusId` | 0 | ticket task id (= TaskPageN `hdnTaskTaskId`) |
| `hdnOptionName` | empty | the ticket's Keyword |
| Task Name | set | Testing/Bug/New Requirement, or **blank** (`hdnTaskID` empty) |

ACE adds these rows itself on every load, for my tickets (6 on 28/10, 13 on 27/10 and 21/10, including tickets created after that
date). **The rule for which tickets appear is unknown.** They are unsaved (`hdnRowId=0`). Clicking Save probably persists them as the
zero-length rows that `parse_grid()` already skips (`start == end` and total `00:00`) **[I + C]**. A faster test than the time check is
`hdnRowId != '0'` for "really saved".

---

## 5. Gotchas (all observed unless marked)

1. **Strict-mode evaluate frame:** Telerik/ASP.NET postback code reads `arguments.callee`. Calling `item.select()` or `el.click()`
   directly inside `page.evaluate` can throw, so defer it: `setTimeout(() => ..., 0)` (`set_widget`, `dom_click`) **[C]**.
2. **Splitter panes clip:** a normal Playwright `click()` on far-right controls can fail with "outside of the viewport". Use DOM clicks (`dom_click`) **[C]**.
   Screenshots also only cover the viewport.
3. **RadComboBox needs `$find`:** the visible `_Input` boxes are mostly `readOnly`. Use `$find(id).findItemByText(text).select()`.
   `findItemByText` is **exact**, so keep trailing/leading spaces (`' Medtrial Interface'`, `'Customer Connect '`, `'Ward  (Clinical)'`).
   `NABH` exists twice (3083, 3073) and `findItemByText` returns the first. Use `findItemByValue` where it matters.
4. **RadDateTimePicker visible text:** `set_selectedDate` updates the hidden value but not the visible text, and ACE re-parses the stale
   text on blur. `TaskCreator.fill_page` therefore types `dd/MM/yyyy HH:mm` into `RadDateTimePicker1_dateInput` and presses Tab **[C]**.
   `input.value` on these inputs uses the internal format `yyyy-MM-dd-HH-mm-ss`. Read dates via `$find(id).get_selectedDate()`, or the
   `_dateInput_display` span for the shown text.
5. **Keyword maxLength 25:** longer text is silently cut (`short_keyword()` trims at a word boundary) **[O/C]**.
6. **Task Type defaults to Bug** and has no blank option or validator: always set it explicitly.
7. **Validation = `alert()`:** a missing required field shows a JS alert from `ValidationSummary1`. Handle `page.on('dialog')`
   (`save_page` accepts it and records the message) **[O/C]**.
8. **Inverted button names:** `btnSent` = "Assigned", `btnPosted` = "Sent".
9. **Assigned record counter is wrong** (`lblGridStatus` "… of 0 Record(s)"). Page by following `Page$N+1` links until there are none (as `tickets()` does).
10. **Default 30-day window** on both grids; widen `AssignedFromDate`/`SendFromDate` to see older tickets. Ticket-number search still honours the window and needs the `ASPL-` prefix.
11. **Empty grid = one blank row.** Filter rows by `/^ASPL-\d+$/` on cell 0.
12. **Duplicate rows** for one ticket in Assigned. De-duplicate, preferring the `Open` row (as `tickets()` does).
13. **ASP.NET session lock / hang:** `grvPosted` `Select` hung, and the stuck request blocked the whole session for about 1–2 min (all page
    loads timed out at 45s, while `/login.aspx` without cookies answered in 0.5s). The headed and headless browsers share
    `storage_state.json` cookies, so one stuck request stalls both. Retry `goto` with back-off; avoid the Sent `Select`.
14. **Edit mode reuses `Save`:** after `Select`, `Save` = "Update" on an existing ticket. Check `hdnTaskId == '0'` before creating.
15. **No past Target Date (server):** saving or updating with a Target Date before now returns "Target date can not be less
    than current date" *and still saves*, with the current time as Target Date **[O, 2026-10-28, ASPL-173230]**.
16. **Completing a ticket works as in §3.5:** Select → wait for `lblToken` to show the ticket (the postback can lag; a
    single settle was not enough) → `ddlstatusset` = Completed, `TextBox1` and `txtEmployeeRemarks` = "." → Update →
    `lbltaskMsg` "Saved"; the grid then shows Completed and keeps the Target Date **[O, ASPL-173231..173238]**.
15. **Module menu selection is session state:** posting `ctl00$gvModules Select$N` redirects (302) and changes the left tree for the
    whole session. Navigate by URL instead.
16. **Login:** the form can repeat after the first submit (re-submit up to 3 times). `load` can take about 5s or more (background image), so wait for `domcontentloaded` **[C/O]**.
17. **Timesheet description 500 chars** are only enforced on keyup (client side) **[O]**. Server behaviour for longer text is unknown.
18. **Timesheet date max = today:** `RadReportDate` can't be set in the future.
19. **Injected zero-length ticket rows** on the timesheet grid carry the current time and `hdnRowId=0` (see §4.3).

---

## 6. Not determined

* Server-side limits for `txtNote` / remarks (no maxLength attribute; the app caps them at 4000) and timesheet descriptions over 500 characters.
* What the server does on Save with an empty Effort, no Target Date or no assignee (no client validators). Not tested, because it would mean writing.
* Exact text of the post-save message beyond "Saved" in `lbltaskMsg` and the content of `lblRefTicketNo` (from code only).
* Page size of the Sent grid (only 7 rows existed); Mpg code of Employee Wise Report.
* The rule for which tickets ACE injects as zero-length rows on a timesheet date, and whether `btnSave` persists them.
* Whether the Priority/Status `RadComboBox` postbacks fire on a real user click (selecting through the API sent no request).
* Sent-grid ticket detail (its `Select` hangs). Whether Assigned `Select` has server side effects (no visible change was seen).
* Time Sheet Approval (P230), Client Issues/New Requirement (P216) and the report pages were only listed, not inspected.
