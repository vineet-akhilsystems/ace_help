// Ticket assignment: turns Open rows of a sheet into ACE ticket drafts using editable mapping settings.

// Used only until ACE's own module list (/task-options) has loaded.
export const ACE_MODULES = ['Appointment', 'Augastam - Administration', 'Augastam - ATD', 'Augastam - Billing',
  'Augastam - LIS', 'Augastam - Registration', 'Augastam ai', 'Augastam EMR'];
export const SKIP = '__skip__';

export const EMPLOYEES = ['Aakash Sharma', 'Aaradhana', 'Aavishkar Sehatraw', 'Abdul Ayub', 'Abdul Kadir',
  'Abhishek Madhusoodhanan', 'Abhishek Yadav', 'ACE Agent', 'Adarsh Kumar', 'Aditya Singh', 'Admin', 'Ajay Kumar Mangal',
  'Ajesh Jogi', 'Akanksha rai', 'Akash Kumar Johar', 'Alok Sahoo', 'Aman Gupta', 'Aman Sharma', 'Aman Verma',
  'Amit Kumar Gupta', 'Anand Kumar', 'Ankur Singh', 'Anurag Kumar', 'Arif', 'Arun Bhandari', 'Arvind Sharma', 'Ashna Jain',
  'Ashok Yadav', 'Ashutosh Sharma', 'Avanindra Nath Dwivedi', 'Awadhesh Kumar Verma', 'Bal Kishan', 'Bikram Jena',
  'Bikram Nanda', 'Bimlesh Kumar', 'C Shankar', 'Chilukoti Seetha Ramakrishna Hanuman', 'ChristyPaul PV',
  'Debangshu Sengupta', 'Deepak Jha', 'Deepak Senapati', 'Deepak Singh', 'Dharmbeer Singh', 'Dhivakar', 'Digvijay Raushan',
  'Disha Bakshi', 'Drishti Mittal', 'Ebenezer Timothy', 'Fahimuddin Nasir', 'Faizan Alam', 'Gaurav Arora', 'Gaurav Bagouli',
  'Gaurav Gopal Tiwari', 'Hafiz Sajid Kamal', 'Harshit Gupta', 'Harshit Singh', 'Heramba Dash', 'Herjeet Singh Gaidu',
  'Himanshu Bhatt', 'Himanshu Maitray', 'Hitanshu', 'Hritwick Goyal', 'Jai Singh', 'Karan Kumar', 'Karan Raj Singh Verma',
  'Kashish Mahajan', 'Keshav Singh', 'Kirttinath Ojha', 'Kovid Gupta', 'Kritika Arora', 'Kuldeep Kumar', 'Kuldeep Singh',
  'Lakshmi', 'Lalit Kumar', 'Lalit Sharma', 'Lokesh Kashyap', 'Mahendra kumar Jaiswal', 'Manish Chokotiya',
  'Manoj Kumar Chauhan', 'Manoj Kumar Puri', 'MD MOHIM AKHTER', 'Md Saifuddin', 'Mehak Arora', 'Mehdi Abbas',
  'Mohammad Asad Khan', 'Mohammad Idrish', 'Mohammad Shoaib', 'Mohd Faisal', 'Mohd Tariq Khan', 'Mohit Sangwan', 'Monishka',
  'Mukesh Kumar', 'Muskan', 'Naeem Ahmad', 'Naman Thapa', 'Namit Kumar', 'Nandan Singh', 'Naresh kumar Sharma',
  'Naveen Shekhar Mishra', 'Navneet Pathak', 'Neeraj Bhatia', 'Nikita Arora', 'Nitesh Basoya', 'Nitin Kumar', 'Nitish Kumar',
  'Orhiaran Anthony Oare', 'Palak Arora', 'Pankaj Singh', 'Parikshit Shekhawat', 'Piyush Jaiswal', 'Poly Nandi',
  'Pooja Joshi', 'Prashant Gangal', 'Preeti Pandey', 'Rahul Kumar', 'Rahul Yadav', 'Ramesh Chand Mishra', 'Ranjeet Kumar',
  'Ravi Pal', 'Ravi Pratap Singh', 'Ravi Singh', 'Rekha Jain', 'Ritika Garg', 'Ritika Kinger', 'Ritvik Chhabra',
  'Rohit Kumar', 'Rohit Sangwan', 'Rupal Singh', 'Sagar Chaturvedi', 'Sahibe Alam', 'Sakshi Chauhan', 'Sanjana Yadav',
  'Sanjay Jain', 'Sanjay Kumar', 'Sanket Mohanty', 'Santosh Kumar', 'Santosh Kumar Singh', 'Sarika Rana',
  'Satender Datt Chamoli', 'Satveer singh', 'Satyendra Kumar Prajapati', 'Saurav Kumar', 'Shaivee Sharma',
  'SHASHI PRASAD GADDAM', 'Shatakshi', 'Shivi Sabbarwal', 'Shruti Narang', 'Sibgatullah', 'Siddharta Tiwari',
  'Siddharth Sharma', 'Siraj Ansari', 'Sneha Khurana', 'Sonu Kumar', 'Sourav Chatta', 'SPS Yadav', 'Subarna Sutar',
  'Suman Kumar', 'Suman Pandey', 'Sumit Kumar Jha', 'Sunil Kumar', 'Sunil kumar Kaushik', 'Sunita', 'Suparba Pal',
  'Suraj Singh', 'Suraj Soni', 'Surya Pratap Singh', 'Sushil Saini', 'Swadhin Kumar Senapati', 'Sworup Nayak',
  'Tanveer Alam', 'Tapan K Desai', 'Tapan Reddy', 'Taskeen Ara Begum', 'Tirendra Jada', 'Toofan Singh', 'Tushar Kumar',
  'Udit', 'Umesh Kumar Anand', 'Vaibhav Agarwal', 'Vaibhav Prashant', 'Ved Prakash', 'Vikas Tiwari', 'Vineet Kukreti',
  'Vivek Singh', 'Wasi Ahmad', 'Yash Garg', 'Yashasvi Patyal', 'Yasheen Akhtar', 'Yogesh Kumar Yadav', 'Yugal goyal'];

// The ACE New Task fields this tab fills, in form order.
export const ACE_FIELDS = [['taskType', 'Task Type'], ['client', 'Client Name'], ['module', 'Module'], ['keyword', 'Keyword'],
  ['description', 'Description'], ['assignTo', 'Assign To'], ['targetDate', 'Target Date'], ['effortDays', 'Effort in Days'],
  ['priority', 'Priority'], ['employeeRemarks', 'Employee Remarks']];  // Status comes from the Statuses table

// The ACE status each sheet status is created with (lower-cased sheet status → ACE status or SKIP).
export const DEFAULT_STATUSES = {open: 'Open', completed: 'Completed', done: 'Completed', 'done/build': 'Completed'};
// What a row whose Module / Assign To / Status cell is empty gets: skip = no ticket for that row (the default);
// otherwise module pick = held until a module is picked, assignTo fallback = the fallback assignee,
// status table = the Statuses table's (empty) row. Mirrored in backend/assign_rules.py.
export const DEFAULT_WHEN_EMPTY = {module: 'skip', assignTo: 'skip', status: 'skip'};
const EMPTY_LABELS = {module: 'Module', assignTo: 'Assign To', status: 'Status'};
export const ACE_STATUSES = ['Open', 'Working', 'Completed', 'Delivered', 'Verified', 'Tested', 'Halt', 'Re-Open'];

// ACE needs some text in the remarks; "." is what the user puts on other tickets.
const REMARK_EMPTY = '.';

// source: fixed = same value every ticket; column = one sheet column; template = {Column} placeholders combined;
// days = the date column when filled, otherwise today + N days.
// The sheet link itself lives in .env (ACE_ASSIGN_SHEET_URL), not here.
export const DEFAULT_SETTINGS = {
  source: 'live',  // live = the OneDrive sheet; test = the local test copy
  sheetTab: 'Bug List',
  statusColumn: 'Status', ticketColumn: 'ASPL Ticket No',
  fallbackAssignee: 'Satender Datt Chamoli',
  whenEmpty: DEFAULT_WHEN_EMPTY,
  fields: {
    taskType: {source: 'fixed', value: 'Bug'},
    client: {source: 'fixed', value: 'Augastam (New Product)'},
    module: {source: 'column', value: 'Module'},
    keyword: {source: 'column', value: 'Page'},
    description: {source: 'template', value: '{Description}\nScreenshot: {Screenshot}\n[Assigned by {Assigned By}]'},
    assignTo: {source: 'column', value: 'Assigned to'},
    targetDate: {source: 'days', value: 7, column: 'TargetDate'},
    effortDays: {source: 'fixed', value: '7'},
    priority: {source: 'fixed', value: 'High'},
    employeeRemarks: {source: 'column', value: 'Employee Remark'},
  },
  modules: {}, // sheet module → ACE module or SKIP; a missing entry uses the automatic match
  people: {},  // lower-cased sheet name → employee; a missing entry uses the automatic match
  statuses: DEFAULT_STATUSES, // lower-cased sheet status → ACE status or SKIP; a missing entry gets no ticket
};

const words = s => String(s ?? '').toLowerCase().replace(/[^a-z]+/g, ' ').trim().split(' ').filter(Boolean);
const clean = s => String(s ?? '').trim();
const pad = n => String(n).padStart(2, '0');

// Merges saved settings over the defaults so a setting added later always has a value.
export function withDefaults(saved) {
  return {...DEFAULT_SETTINGS, ...saved, fields: {...DEFAULT_SETTINGS.fields, ...saved?.fields},
    whenEmpty: {...DEFAULT_WHEN_EMPTY, ...saved?.whenEmpty},
    modules: {...saved?.modules}, people: {...saved?.people}, statuses: {...(saved?.statuses || DEFAULT_STATUSES)}};
}

// The sheet uses short names ("Naveen", "Karan Verma"). One employee containing every word is a match.
export function matchEmployee(name, employees = EMPLOYEES) {
  const raw = clean(name);
  const exact = employees.find(e => e.toLowerCase() === raw.toLowerCase());
  if (exact) return {name: exact, how: 'exact', candidates: []};
  const want = words(raw);
  const candidates = want.length ? employees.filter(e => want.every(w => words(e).includes(w))) : [];
  return candidates.length === 1 ? {name: candidates[0], how: 'auto', candidates} : {name: '', how: 'ask', candidates};
}

// "Augastam" and its misspellings in the sheet ("Augstam billing").
const product = w => w.startsWith('aug');

// "Billing", "Augstam-billing" → "Augastam - Billing"; "Admin" → "Augastam - Administration".
// ACE also has plain "Administration", "Registration"…, so an Augastam module wins over a general one.
// Mirrored in backend/assign_rules.py; both are checked against tests/fixtures/assign_cases.json.
export function matchModule(module, modules = ACE_MODULES) {
  const key = words(module).filter(w => !product(w)).join(' ');
  if (!key) return '';
  const fits = m => {
    const tail = words(m).filter(w => !product(w)).join(' ');
    return tail && (tail.startsWith(key) || key === tail || key.startsWith(`${tail} `));
  };
  return modules.find(m => words(m).some(product) && fits(m)) || modules.find(fits) || '';
}

export function resolveModule(raw, settings, modules = ACE_MODULES) {
  const value = clean(raw);
  return value in settings.modules ? {module: settings.modules[value], how: 'saved'} : {module: matchModule(value, modules), how: 'auto'};
}

export function resolvePerson(raw, settings, employees = EMPLOYEES) {
  const value = clean(raw);
  if (!value) return {name: settings.fallbackAssignee, how: 'default', candidates: []};
  const saved = settings.people[value.toLowerCase()];
  return saved ? {name: saved, how: 'saved', candidates: []} : matchEmployee(value, employees);
}

// Mapping table rows: every value the sheet uses now, plus saved mappings the sheet no longer (or not yet) uses.
export function mappingRows(found, saved, keyOf = v => v) {
  const seen = new Set(found.map(f => keyOf(f.value)));
  const extra = Object.keys(saved).filter(k => !seen.has(k)).map(k => ({value: k, count: 0, inSheet: false}));
  return [...found.map(f => ({...f, inSheet: true})), ...extra].sort((a, b) => a.value.localeCompare(b.value));
}

// A line whose placeholders are all empty is dropped, so a row without a screenshot has no "Screenshot:" line.
export function fillTemplate(template, row) {
  return String(template || '').split('\n').map(line => {
    const keys = [...line.matchAll(/\{([^}]+)\}/g)].map(m => m[1]);
    if (keys.length && keys.every(k => !clean(row[k]))) return null;
    return line.replace(/\{([^}]+)\}/g, (_, k) => clean(row[k]));
  }).filter(line => line !== null).join('\n').trim();
}

export function targetDate(today, days = 7) {
  const d = new Date(`${today}T12:00:00`);
  d.setDate(d.getDate() + Number(days || 0));
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T18:00`;
}

// Sheet dates arrive as Excel day numbers, "2026-11-06" or "06/11/2026" (day first).
export function sheetDate(value) {
  const v = clean(value);
  if (!v) return '';
  if (/^\d{5}(\.\d+)?$/.test(v)) {
    const d = new Date(Date.UTC(1899, 11, 30) + Math.floor(Number(v)) * 86400000);
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T18:00`;
  }
  let m = v.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (m) return `${m[1]}-${pad(m[2])}-${pad(m[3])}T18:00`;
  m = v.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})/);
  return m ? `${m[3]}-${pad(m[2])}-${pad(m[1])}T18:00` : '';
}

export function fieldValue(config, row, today) {
  if (!config) return '';
  if (config.source === 'column') return clean(row[config.value]);
  if (config.source === 'template') return fillTemplate(config.value, row);
  if (config.source === 'days') return (config.column && sheetDate(row[config.column])) || targetDate(today, config.value);
  return clean(config.value);
}

// Columns the settings name that the sheet no longer has (for example after a column is renamed).
export function missingColumns(settings, columns) {
  const used = [settings.statusColumn, settings.ticketColumn];
  for (const config of Object.values(settings.fields)) {
    if (config.source === 'column') used.push(config.value);
    if (config.source === 'template') used.push(...[...String(config.value).matchAll(/\{([^}]+)\}/g)].map(m => m[1]));
    if (config.source === 'days' && config.column) used.push(config.column);
  }
  return [...new Set(used.filter(c => c && !columns.includes(c)))];
}

// The ACE status for this row's sheet status, or SKIP when the Statuses table does not pick it.
export const resolveStatus = (row, settings) => settings.statuses[clean(row[settings.statusColumn]).toLowerCase()] || SKIP;

// A row that gets a ticket: no ticket number yet, and its status is picked in the Statuses table.
export const isOpenRow = (row, settings) => resolveStatus(row, settings) !== SKIP && !clean(row[settings.ticketColumn]);

// A row without a ticket number whose Status cell is empty, while the empty rule says no ticket.
export const emptyStatusSkipped = (row, settings) => settings.whenEmpty.status === 'skip'
  && !clean(row[settings.statusColumn]) && !clean(row[settings.ticketColumn]);

// Every status the sheet uses on rows without a ticket number, with how many rows have it (for the Statuses table).
// Grouped ignoring case, as the table matches it; the first spelling seen is shown.
export function statusValues(rows, settings) {
  const seen = new Map();
  for (const row of rows.filter(r => !clean(r[settings.ticketColumn]))) {
    const value = clean(row[settings.statusColumn]), key = value.toLowerCase();
    const entry = seen.get(key) || {value, count: 0};
    seen.set(key, {...entry, count: entry.count + 1});
  }
  return [...seen.values()].sort((a, b) => a.value.localeCompare(b.value));
}

// Distinct sheet values for a field (modules, people) with how many open rows use each.
export function distinctValues(rows, settings, field) {
  const counts = new Map();
  for (const row of rows.filter(r => isOpenRow(r, settings))) {
    const value = fieldValue(settings.fields[field], row, '2000-01-01');
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts].map(([value, count]) => ({value, count})).sort((a, b) => a.value.localeCompare(b.value));
}

// Open rows without a ticket number → drafts. Rows whose module is set to skip, or whose Module / Assign To / Status
// cell is empty while the empty rule says no ticket, are listed separately with the reason.
export function sheetDrafts(rows, settings, today, modules = ACE_MODULES, employees = EMPLOYEES) {
  const drafts = [];
  const skipped = rows.filter(r => emptyStatusSkipped(r, settings)).map(r => ({row: r._row, reason: 'Status is empty',
    description: fieldValue(settings.fields.description, r, today)}));
  const open = rows.filter(r => isOpenRow(r, settings) && !emptyStatusSkipped(r, settings));
  for (const row of open) {
    const value = field => fieldValue(settings.fields[field], row, today);
    const rawModule = value('module'), sheetName = value('assignTo');
    const empty = [['module', rawModule], ['assignTo', sheetName]].filter(([f, raw]) => !raw && settings.whenEmpty[f] === 'skip')
      .map(([f]) => EMPTY_LABELS[f]);
    if (empty.length) {
      skipped.push({row: row._row, reason: `${empty.join(' and ')} ${empty.length > 1 ? 'are' : 'is'} empty`, description: value('description')});
      continue;
    }
    const mod = resolveModule(rawModule, settings, modules);
    if (mod.module === SKIP) {
      skipped.push({row: row._row, reason: `Module "${rawModule}" is set to skip`, description: value('description')});
      continue;
    }
    const person = resolvePerson(sheetName, settings, employees);
    const warnings = [];
    if (!mod.module) warnings.push(`Module "${rawModule}" has no ACE module yet. Pick one here or in Settings → Modules.`);
    else if (!modules.includes(mod.module)) warnings.push(`ACE has no module "${mod.module}". Pick one from ACE's list.`);
    if (person.name && !employees.includes(person.name)) warnings.push(`ACE has no employee "${person.name}". Pick one from ACE's list.`);
    if (person.how === 'ask') warnings.push(`"${sheetName}" matches ${person.candidates.length ? 'more than one employee' : 'no employee'}. Pick who gets this ticket.`);
    if (person.how === 'default') warnings.push(`No one in "${settings.fields.assignTo.value}", so it goes to ${settings.fallbackAssignee}.`);
    drafts.push({
      row: row._row, pick: true, sheetName, assigneeHow: person.how, candidates: person.candidates, warnings,
      taskType: value('taskType'), client: value('client'), module: mod.module, keyword: value('keyword').slice(0, 25),
      description: value('description'), assignee: person.name, targetDate: value('targetDate'),
      effortDays: value('effortDays'), priority: value('priority'),
      status: resolveStatus(row, settings),
      employeeRemarks: value('employeeRemarks').slice(0, 4000),
    });
  }
  skipped.sort((a, b) => a.row - b.row);
  return {drafts, skipped, closed: rows.length - open.length - rows.filter(r => emptyStatusSkipped(r, settings)).length};
}

// The backend TaskDraft for one reviewed ticket; the client remark (and an empty employee remark) is ".".
export function taskDraft(d) {
  return {taskType: d.taskType, priority: d.priority, client: d.client, module: d.module, frdNature: '', status: d.status,
    targetDate: d.targetDate, effortDays: Number(d.effortDays), keyword: d.keyword, description: d.description,
    clientRemarks: REMARK_EMPTY, employeeRemarks: clean(d.employeeRemarks) || REMARK_EMPTY, assignTo: d.assignee};
}

export function draftIssues(draft) {
  return [['module', 'Module'], ['assignee', 'Assign to'], ['keyword', 'Keyword'], ['description', 'Description'],
    ['taskType', 'Task Type'], ['client', 'Client Name'], ['targetDate', 'Target Date'], ['effortDays', 'Effort in Days'],
    ['priority', 'Priority'], ['status', 'Status']].filter(([f]) => !clean(draft[f])).map(([, label]) => label);
}
