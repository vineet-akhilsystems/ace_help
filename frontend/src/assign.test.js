import {expect, it} from 'vitest';
import {DEFAULT_SETTINGS, SKIP, distinctValues, statusValues, fillTemplate, isOpenRow, mappingRows, matchEmployee, matchModule, missingColumns,
  resolvePerson, sheetDate, sheetDrafts, targetDate, taskDraft, withDefaults} from './assign';

import cases from '../../tests/fixtures/assign_cases.json';

const settings = withDefaults({});

it('agrees with the shared cases the Python rules are also checked against', () => {
  for (const [name, expected, how] of cases.matchEmployee)
    expect(matchEmployee(name, cases.employees), name).toMatchObject({name: expected, how});
  for (const [module, expected] of cases.matchModule) expect(matchModule(module, cases.modules), module).toBe(expected);
  for (const [template, row, expected] of cases.fillTemplate) expect(fillTemplate(template, row)).toBe(expected);
  for (const [value, expected] of cases.sheetDate) expect(sheetDate(value)).toBe(expected);
});
const row = (n, cells) => ({_row: n, Status: 'Open', ...cells});

it('matches short sheet names to one employee, and asks when it cannot tell', () => {
  expect(matchEmployee('Naveen').name).toBe('Naveen Shekhar Mishra');
  expect(matchEmployee('Asad').name).toBe('Mohammad Asad Khan');
  expect(matchEmployee('Karan Verma')).toMatchObject({name: 'Karan Raj Singh Verma', how: 'auto'});
  expect(matchEmployee('gaurav bagouli')).toMatchObject({name: 'Gaurav Bagouli', how: 'exact'});
  expect(matchEmployee('Rahul')).toMatchObject({name: '', how: 'ask', candidates: ['Rahul Kumar', 'Rahul Yadav']});
  expect(matchEmployee('Nobody Here')).toMatchObject({name: '', how: 'ask', candidates: []});
});

it('uses a saved person, and the fallback when the cell is empty', () => {
  const s = withDefaults({people: {rahul: 'Rahul Yadav'}});
  expect(resolvePerson('Rahul', s)).toMatchObject({name: 'Rahul Yadav', how: 'saved'});
  expect(resolvePerson('  ', s)).toMatchObject({name: 'Satender Datt Chamoli', how: 'default'});
});

// Part of ACE's real Module list (101 options, read 2026-10-30): general modules sit beside the Augastam ones.
const ACE_LIST = ['Administration', 'Appointment', 'Augastam - Administration', 'Augastam - ATD', 'Augastam - Billing',
  'Augastam - LIS', 'Augastam - Registration', 'Augastam ai', 'Augastam EMR', 'Book Appointment Portal', 'IP Billing',
  'OP Billing', 'OT', 'Registration', 'Reports - Billing'];

it('maps sheet modules to ACE modules, preferring the Augastam ones', () => {
  // Every Module value in the Bug List sheet on 2026-10-30.
  expect(['Admin', 'Augastam - Admin', 'Augastam-Admin', 'Augastam - Appointment', 'Augastam - Billing', 'Augastam - Registration',
    'Billing', 'Registration'].map(m => matchModule(m, ACE_LIST))).toEqual(['Augastam - Administration', 'Augastam - Administration',
    'Augastam - Administration', 'Appointment', 'Augastam - Billing', 'Augastam - Registration', 'Augastam - Billing',
    'Augastam - Registration']);
  expect(matchModule('Other', ACE_LIST)).toBe('');
  expect(matchModule('', ACE_LIST)).toBe('');
  expect(matchModule('Pharmacy')).toBe('');
});

it('keeps only rows with the open status and no ticket number', () => {
  expect(isOpenRow({Status: ' open '}, settings)).toBe(true);
  expect(isOpenRow({Status: 'Open', 'ASPL Ticket No': 'ASPL-123456'}, settings)).toBe(false);
  expect(isOpenRow({Status: 'On hold'}, settings)).toBe(false);
  expect(isOpenRow({Status: ' done/build '}, settings)).toBe(true);
  expect(isOpenRow({Status: 'Completed', 'ASPL Ticket No': 'ASPL-1'}, settings)).toBe(false);
  expect(isOpenRow({State: 'New'}, withDefaults({statusColumn: 'State', statuses: {new: 'Open'}}))).toBe(true);
  expect(isOpenRow({Status: 'Open'}, withDefaults({statuses: {done: 'Completed'}}))).toBe(false);  // not in the table: no ticket
  expect(statusValues([{Status: 'Open'}, {Status: 'open '}, {Status: ''}, {Status: 'done', 'ASPL Ticket No': 'ASPL-1'}], settings))
    .toEqual([{value: '', count: 1}, {value: 'Open', count: 2}]);
});

it('combines columns in a template and drops lines whose columns are empty', () => {
  const template = DEFAULT_SETTINGS.fields.description.value;
  expect(fillTemplate(template, {Description: 'Tab movement broken ', Screenshot: 'https://prnt.sc/x', 'Assigned By': 'Pooja'}))
    .toBe('Tab movement broken\nScreenshot: https://prnt.sc/x\n[Assigned by Pooja]');
  expect(fillTemplate(template, {Description: 'No link', 'Assigned By': 'Sneha'})).toBe('No link\n[Assigned by Sneha]');
});

it('uses the sheet date when filled, otherwise today + N days', () => {
  expect(targetDate('2026-10-30')).toBe('2026-11-06T18:00');
  expect(sheetDate('06/11/2026')).toBe('2026-11-06T18:00');
  expect(sheetDate('46332')).toBe('2026-11-06T18:00');
  expect(sheetDate('')).toBe('');
});

it('names the columns the settings use that the sheet does not have', () => {
  const columns = ['Module', 'Page', 'Description', 'Screenshot', 'Assigned By', 'Assigned to', 'Status', 'Employee Remark', 'TargetDate', 'ASPL Ticket No'];
  expect(missingColumns(settings, columns)).toEqual([]);
  expect(missingColumns(settings, columns.filter(c => c !== 'Page' && c !== 'Screenshot'))).toEqual(['Page', 'Screenshot']);
});

it('drafts open rows from the settings', () => {
  const rows = [
    row(5, {Module: 'Augastam - Registration', Page: 'Registration', Description: 'Country tagging', 'Assigned By': 'Pooja', 'Assigned to': 'Gaurav Bagouli'}),
    row(7, {Module: 'Augastam - Billing', Page: 'Invoice', Description: 'Held one', Status: 'On hold'}),
    row(41, {Module: 'Augastam - Appointment', Page: 'Appointment', Description: 'Invoice tab blank'}),
    row(39, {Module: 'Admin', Page: 'A very long page name that goes on', Description: 'Doctor visit'}),
  ];
  const fallback = withDefaults({whenEmpty: {assignTo: 'fallback'}});
  const {drafts, skipped, closed} = sheetDrafts(rows, fallback, '2026-10-30');
  expect([drafts.map(d => d.row), skipped, closed]).toEqual([[5, 41, 39], [], 1]);
  expect(drafts[1].module).toBe('Appointment');
  const missing = sheetDrafts(rows, withDefaults({...fallback, modules: {'Augastam - Appointment': 'Augastam - Appointment'}}), '2026-10-30');
  expect(missing.drafts[1].warnings).toContain('ACE has no module "Augastam - Appointment". Pick one from ACE\'s list.');
  expect(drafts[0]).toMatchObject({taskType: 'Bug', client: 'Augastam (New Product)', module: 'Augastam - Registration',
    priority: 'High', status: 'Open', effortDays: '7', targetDate: '2026-11-06T18:00', assignee: 'Gaurav Bagouli',
    description: 'Country tagging\n[Assigned by Pooja]'});
  expect(drafts[2]).toMatchObject({module: 'Augastam - Administration', assignee: 'Satender Datt Chamoli', keyword: 'A very long page name tha'});

  const changed = withDefaults({...fallback, modules: {'Augastam - Appointment': 'Augastam - Registration', Admin: SKIP},
    fields: {priority: {source: 'fixed', value: 'Medium'}}});
  const again = sheetDrafts(rows, changed, '2026-10-30');
  expect([again.drafts.map(d => [d.row, d.module, d.priority]), again.skipped.map(s => s.row)])
    .toEqual([[[5, 'Augastam - Registration', 'Medium'], [41, 'Augastam - Registration', 'Medium']], [39]]);
});

it('keeps saved mappings in the table when the sheet does not use them', () => {
  expect(mappingRows([{value: 'Naveen', count: 2}], {naveen: 'Naveen Shekhar Mishra', 'new person': 'Udit'}, v => v.toLowerCase()))
    .toEqual([{value: 'Naveen', count: 2, inSheet: true}, {value: 'new person', count: 0, inSheet: false}]);
});

it('warns when a saved person is not in ACE', () => {
  const rows = [row(1, {Module: 'Billing', Page: 'Invoice', Description: 'x', 'Assigned to': 'Naveen'})];
  const {drafts} = sheetDrafts(rows, settings, '2026-10-30', undefined, ['Vivek Singh']);
  expect(drafts[0].warnings.join(' ')).toContain('no employee');
});

it('turns a reviewed ticket into the backend draft', () => {
  const rows = [row(2, {Module: 'Augastam - Registration', Page: 'Registration', Description: 'Test', 'Assigned to': 'Vineet Kukreti'})];
  const [d] = sheetDrafts(rows, settings, '2026-10-30').drafts;
  expect(taskDraft(d)).toEqual({taskType: 'Bug', priority: 'High', client: 'Augastam (New Product)', module: 'Augastam - Registration',
    frdNature: '', status: 'Open', targetDate: '2026-11-06T18:00', effortDays: 7, keyword: 'Registration', description: 'Test',
    clientRemarks: '.', employeeRemarks: '.', assignTo: 'Vineet Kukreti'});
  const remarked = [row(3, {Module: 'Billing', Page: 'Invoice', Description: 'x', 'Assigned to': 'Naveen', 'Employee Remark': 'Needs the new grid first'})];
  expect(taskDraft(sheetDrafts(remarked, settings, '2026-10-30').drafts[0]).employeeRemarks).toBe('Needs the new grid first');
  const finished = [row(4, {Module: 'Billing', Page: 'Invoice', Description: 'y', 'Assigned to': 'Naveen', Status: 'done'})];
  expect(taskDraft(sheetDrafts(finished, settings, '2026-10-30').drafts[0]).status).toBe('Completed');
});

it('lists the distinct values of a field across open rows', () => {
  const rows = [row(1, {Module: 'Billing'}), row(2, {Module: 'Billing'}), row(3, {Module: 'Admin'}), row(4, {Module: 'X', Status: 'On hold'})];
  expect(distinctValues(rows, settings, 'module')).toEqual([{value: 'Admin', count: 1}, {value: 'Billing', count: 2}]);
});

it('gives no ticket to a row whose module, assignee or status is empty, unless the empty-cell rule says otherwise', () => {
  const rows = [row(2, {Module: 'Billing', Page: 'Invoice', Description: 'ok', 'Assigned to': 'Naveen'}),
    row(3, {Module: '', Page: 'Invoice', Description: 'No module', 'Assigned to': 'Naveen'}),
    row(4, {Module: 'Billing', Page: 'Invoice', Description: 'No one'}),
    row(5, {Module: 'Billing', Page: 'Invoice', Description: 'No status', 'Assigned to': 'Naveen', Status: ''}),
    row(6, {Page: 'Invoice', Description: 'Neither'}),
    row(7, {Module: 'Billing', Description: 'Done', Status: '', 'ASPL Ticket No': 'ASPL-1'})];
  const out = sheetDrafts(rows, settings, '2026-10-30');
  expect([out.drafts.map(d => d.row), out.skipped.map(s => [s.row, s.reason]), out.closed]).toEqual([[2],
    [[3, 'Module is empty'], [4, 'Assign To is empty'], [5, 'Status is empty'], [6, 'Module and Assign To are empty']], 1]);
  const other = withDefaults({whenEmpty: {module: 'pick', assignTo: 'fallback', status: 'table'}, statuses: {open: 'Open', '': 'Open'}});
  const drafts = sheetDrafts(rows, other, '2026-10-30').drafts;
  expect(drafts.map(d => [d.row, d.module, d.assignee])).toEqual([[2, 'Augastam - Billing', 'Naveen Shekhar Mishra'],
    [3, '', 'Naveen Shekhar Mishra'], [4, 'Augastam - Billing', 'Satender Datt Chamoli'],
    [5, 'Augastam - Billing', 'Naveen Shekhar Mishra'], [6, '', 'Satender Datt Chamoli']]);
  expect(withDefaults({whenEmpty: {module: 'pick'}}).whenEmpty).toEqual({module: 'pick', assignTo: 'skip', status: 'skip'});
});
