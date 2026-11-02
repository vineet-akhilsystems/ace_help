"""Reads one worksheet of an .xlsx file with the standard library only (no openpyxl)."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET

M = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
P = '{http://schemas.openxmlformats.org/package/2006/relationships}'


def column_index(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref)[0]:
        n = n * 26 + ord(ch) - 64
    return n - 1


def column_letter(index):
    letters, n = '', index + 1
    while n:
        n, rest = divmod(n - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _text(node):
    return ''.join(t.text or '' for t in node.iter(M + 't'))


def read_sheet(data: bytes, name: str):
    """(columns, rows): columns = [(letter, header)] for named header cells in row 1; rows = dicts keyed by header,
    with _row = the sheet row number. Rows with no value at all are left out."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [_text(si) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si')]
        book = ET.fromstring(z.read('xl/workbook.xml'))
        sheets = {s.get('name'): s.get(R + 'id') for s in book.iter(M + 'sheet')}
        if name not in sheets:
            raise ValueError(f'The workbook has no "{name}" tab. Tabs: {", ".join(sheets)}.')
        rels = ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        target = next(r.get('Target') for r in rels.iter(P + 'Relationship') if r.get('Id') == sheets[name])
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        table = {}
        for row in ET.fromstring(z.read(target)).iter(M + 'row'):
            cells = {}
            for c in row.findall(M + 'c'):
                kind, v = c.get('t'), c.find(M + 'v')
                if kind == 's' and v is not None:
                    value = shared[int(v.text)]
                elif kind == 'inlineStr':
                    value = _text(c)
                else:
                    value = v.text if v is not None and v.text is not None else ''
                cells[column_index(c.get('r'))] = value
            table[int(row.get('r'))] = cells
    header = table.get(1, {})
    columns = [(column_letter(i), str(header[i]).strip()) for i in sorted(header) if str(header[i]).strip()]
    rows = []
    for number in sorted(n for n in table if n > 1):
        cells = table[number]
        if not any(str(v).strip() for v in cells.values()):
            continue
        rows.append({'_row': number, **{h: str(cells.get(column_index(letter), '')).strip() for letter, h in columns}})
    return columns, rows
