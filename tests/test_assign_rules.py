import io
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
import pytest
from backend.assign_rules import (SKIP, AssignSettings, check_columns, fill_template, fingerprint, held_reasons,
                                  match_employee, match_module, sheet_date, sheet_drafts, task_fields)
from backend.services import xlsx

CASES = json.loads((Path(__file__).parent / 'fixtures' / 'assign_cases.json').read_text(encoding='utf-8'))
COLUMNS = ['S.No', 'Module', 'Page', 'Description', 'Screenshot', 'Assigned By', 'Assigned to', 'Status',
           'Employee Remark', 'TargetDate', 'ASPL Ticket No']


def make_xlsx(rows, sheet='Bug List'):
    """A minimal workbook: a first tab, then `sheet` holding rows (row 1 = header); text as shared strings."""
    shared = []

    def cell(ref, value):
        if value == '':
            return ''
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        shared.append(value)
        return f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>'
    body = ''.join(f'<row r="{n}">' + ''.join(cell(f'{xlsx.column_letter(i)}{n}', v) for i, v in enumerate(r)) + '</row>'
                   for n, r in rows)
    m = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{m}" xmlns:r="{r}"><sheets><sheet name="Other" sheetId="1" '
                   f'r:id="rId1"/><sheet name="{sheet}" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{m}"><sheetData/></worksheet>')
        z.writestr('xl/worksheets/sheet2.xml', f'<worksheet xmlns="{m}"><sheetData>{body}</sheetData></worksheet>')
        z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{m}">' + ''.join(f'<si><t>{escape(s)}</t></si>' for s in shared) + '</sst>')
    return out.getvalue()


def bug(**cells):
    base = dict(zip(COLUMNS, ['1', 'Augastam - Registration', 'Registration', 'Merge Registration is pending', '',
                              'Pooja Joshi', 'Gaurav Bagouli', 'Open', '', '', '']))
    return [base[c] if c not in cells else cells[c] for c in COLUMNS]


def test_matching_agrees_with_the_shared_cases():
    for name, expected, how in CASES['matchEmployee']:
        assert match_employee(name, CASES['employees']) | {'candidates': None} == {'name': expected, 'how': how, 'candidates': None}, name
    for module, expected in CASES['matchModule']:
        assert match_module(module, CASES['modules']) == expected, module
    for template, row, expected in CASES['fillTemplate']:
        assert fill_template(template, row) == expected
    for value, expected in CASES['sheetDate']:
        assert sheet_date(value) == expected


def test_reads_the_named_tab_with_real_row_numbers():
    data = make_xlsx([(1, ['', 'Module', 'Page', 'Description', 'Status', 'ASPL Ticket No']),
                      (2, ['1', 'Billing', 'Invoice', 'Fees & taxes wrong', 'Open', '']),
                      (5, ['', '', '', '', '', '']),
                      (7, [2, 'Admin', 'Payer', 'Line one\nline two', 'Open', 'ASPL-1'])])
    columns, rows = xlsx.read_sheet(data, 'Bug List')
    assert columns == [('B', 'Module'), ('C', 'Page'), ('D', 'Description'), ('E', 'Status'), ('F', 'ASPL Ticket No')]
    assert [(r['_row'], r['Description'], r['ASPL Ticket No']) for r in rows] == [
        (2, 'Fees & taxes wrong', ''), (7, 'Line one\nline two', 'ASPL-1')]
    with pytest.raises(ValueError, match='no "Bugs" tab'):
        xlsx.read_sheet(data, 'Bugs')
    assert [xlsx.column_letter(i) for i in (0, 10, 25, 26, 27)] == ['A', 'K', 'Z', 'AA', 'AB']


def test_a_row_keeps_its_fingerprint_when_it_moves_or_its_status_changes():
    settings = AssignSettings()
    row = dict(zip(COLUMNS, bug()), _row=14)
    moved = {**row, '_row': 30, 'Status': 'Completed', 'Assigned to': 'Naveen'}
    assert fingerprint(row, settings) == fingerprint(moved, settings)
    assert fingerprint(row, settings) != fingerprint({**row, 'Description': 'Another bug'}, settings)
    assert check_columns(settings, COLUMNS) == ['Description', 'Assigned to', 'Status']


def test_drafts_are_held_when_the_module_or_person_is_unclear():
    settings = AssignSettings()
    rows = [dict(zip(COLUMNS, bug()), _row=2),
            dict(zip(COLUMNS, bug(Module='Pharmacy', **{'Assigned to': 'Satendra sir'})), _row=3),
            dict(zip(COLUMNS, bug(Module='Augstam billing', **{'Assigned to': ''})), _row=4),
            dict(zip(COLUMNS, bug(Status='On hold')), _row=5)]
    out = sheet_drafts(rows, AssignSettings(whenEmpty={'assignTo': 'fallback'}), '2026-10-30', CASES['modules'],
                       CASES['employees'])
    assert out['closed'] == 1
    first, unclear, empty = out['drafts']
    assert held_reasons(first, CASES['modules'], CASES['employees']) == []
    assert task_fields(first) | {'description': None} == {
        'taskType': 'Bug', 'priority': 'High', 'client': 'Augastam (New Product)', 'module': 'Augastam - Registration',
        'frdNature': '', 'status': 'Open', 'targetDate': '2026-11-06T18:00', 'effortDays': 7.0, 'keyword': 'Registration',
        'description': None, 'clientRemarks': '.', 'employeeRemarks': '.', 'assignTo': 'Gaurav Bagouli'}
    assert held_reasons(unclear, CASES['modules'], CASES['employees']) == ['Module is missing', 'Assign to is missing']
    assert (empty['module'], empty['assignee']) == ('Augastam - Billing', 'Satender Datt Chamoli')
    remarked = dict(zip(COLUMNS, bug(**{'Employee Remark': 'Needs the new grid first'})), _row=6)
    [with_remark] = sheet_drafts([remarked], settings, '2026-10-30', CASES['modules'], CASES['employees'])['drafts']
    assert task_fields(with_remark)['employeeRemarks'] == 'Needs the new grid first'
    finished = [dict(zip(COLUMNS, bug(Status=s, Description=s)), _row=n) for n, s in ((7, 'Completed'), (8, 'done/build'))]
    done = sheet_drafts(finished, settings, '2026-10-30', CASES['modules'], CASES['employees'])['drafts']
    assert [task_fields(d)['status'] for d in done] == ['Completed', 'Completed']
    # The Statuses table decides: a status it does not list gets no ticket, and each listed one its own ACE status.
    custom = AssignSettings(statuses={'open': 'Working', 'done/build': SKIP})
    assert [(d['row'], d['status']) for d in sheet_drafts(finished + [rows[0]], custom, '2026-10-30', CASES['modules'],
                                                          CASES['employees'])['drafts']] == [(2, 'Working')]
    assert held_reasons({**done[0], 'status': 'Finished'}, CASES['modules'], CASES['employees'], ['Open', 'Completed']) == \
        ['status "Finished" is not in ACE']
    skipping = AssignSettings(modules={'Augastam - Registration': SKIP})
    assert [s['row'] for s in sheet_drafts(rows, skipping, '2026-10-30', CASES['modules'], CASES['employees'])['skipped']] == [2, 4]  # 4: Assign To empty


def test_saved_settings_keep_defaults_for_fields_they_lack():
    settings = AssignSettings.model_validate({'sheetUrl': 'old browser key', 'fields': {'priority': {'source': 'fixed', 'value': 'Medium'}}})
    assert settings.fields['priority'].value == 'Medium'
    assert settings.fields['taskType'].value == 'Bug'


def test_rows_with_an_empty_module_assignee_or_status_get_no_ticket_by_default():
    rows = [dict(zip(COLUMNS, bug()), _row=2),
            dict(zip(COLUMNS, bug(Module='', Description='No module')), _row=3),
            dict(zip(COLUMNS, bug(**{'Assigned to': '', 'Description': 'No one'})), _row=4),
            dict(zip(COLUMNS, bug(Status='', Description='No status')), _row=5),
            dict(zip(COLUMNS, bug(Module='', Description='Neither', **{'Assigned to': ''})), _row=6),
            dict(zip(COLUMNS, bug(Status='', Description='Done', **{'ASPL Ticket No': 'ASPL-1'})), _row=7)]
    args = ('2026-10-30', CASES['modules'], CASES['employees'])
    out = sheet_drafts(rows, AssignSettings(), *args)
    assert [d['row'] for d in out['drafts']] == [2]
    assert [(s['row'], s['reason']) for s in out['skipped']] == [
        (3, 'Module is empty'), (4, 'Assign To is empty'), (5, 'Status is empty'), (6, 'Module and Assign To are empty')]
    assert out['closed'] == 1
    # The other choices: hold for a module pick, the fallback assignee, the Statuses table's (empty) row.
    other = AssignSettings(whenEmpty={'module': 'pick', 'assignTo': 'fallback', 'status': 'table'}, statuses={'open': 'Open', '': 'Open'})
    drafts = {d['row']: d for d in sheet_drafts(rows, other, *args)['drafts']}
    assert sorted(drafts) == [2, 3, 4, 5, 6]
    assert held_reasons(drafts[3], CASES['modules'], CASES['employees']) == ['Module is missing']
    assert drafts[4]['assignee'] == 'Satender Datt Chamoli'
    assert AssignSettings.model_validate({'whenEmpty': {'module': 'pick'}}).whenEmpty == {
        'module': 'pick', 'assignTo': 'skip', 'status': 'skip'}
