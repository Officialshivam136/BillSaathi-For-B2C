"""Minimal .xlsx writer (standard library only): several sheets, bold header row, frozen header, 2-decimal money cells.

    data = workbook([("Sales", [["Invoice", "Total"], ["BS/1", Decimal("100.00")], ["TOTAL", Decimal("100.00")]])])
Strings are written as inline strings, Decimal/int/float as numbers. A row whose first cell is "TOTAL" is bold.
"""
import io
import re
import zipfile
from decimal import Decimal
from xml.sax.saxutils import escape

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
# cell styles (index into cellXfs): 0 normal, 1 bold, 2 money, 3 bold money
NORMAL, BOLD, MONEY, BOLD_MONEY = 0, 1, 2, 3


def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean_name(name, used):
    base = re.sub(r"[\[\]:*?/\\]", " ", str(name)).strip()[:31] or "Sheet"
    n, out = 1, base
    while out.lower() in used:
        n += 1
        out = f"{base[:28]} {n}"
    used.add(out.lower())
    return out


def _sheet_xml(rows):
    widths = {}
    out = []
    for r, row in enumerate(rows, 1):
        total = bool(row) and isinstance(row[0], str) and row[0].upper() == "TOTAL"
        cells = []
        for c, v in enumerate(row):
            if v is None or v == "":
                continue
            ref = f"{_col(c)}{r}"
            header = r == 1
            if isinstance(v, bool):
                cells.append(f"<c r='{ref}' t='b' s='{BOLD if header or total else NORMAL}'><v>{int(v)}</v></c>")
                continue
            if isinstance(v, (Decimal, int, float)):
                money = isinstance(v, (Decimal, float))
                style = (BOLD_MONEY if money else BOLD) if (header or total) else (MONEY if money else NORMAL)
                cells.append(f"<c r='{ref}' s='{style}'><v>{v}</v></c>")
                text_len = len(f"{v:,.2f}") if money else len(str(v))
            else:
                text = _BAD_XML.sub("", str(v))
                style = BOLD if header or total else NORMAL
                cells.append(f"<c r='{ref}' t='inlineStr' s='{style}'><is><t xml:space='preserve'>{escape(text)}</t></is></c>")
                text_len = max((len(x) for x in text.split("\n")), default=0)
            widths[c] = max(widths.get(c, 0), text_len)
        out.append(f"<row r='{r}'>{''.join(cells)}</row>")
    cols = "".join(f"<col min='{c + 1}' max='{c + 1}' width='{min(max(w + 2, 10), 55)}' customWidth='1'/>" for c, w in sorted(widths.items()))
    pane = "<pane ySplit='1' topLeftCell='A2' activePane='bottomLeft' state='frozen'/>" if len(rows) > 1 else ""
    return (f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?><worksheet xmlns='{MAIN}'><sheetViews>"
            f"<sheetView workbookViewId='0'>{pane}</sheetView></sheetViews><sheetFormatPr defaultRowHeight='15'/>"
            f"{'<cols>' + cols + '</cols>' if cols else ''}<sheetData>{''.join(out)}</sheetData></worksheet>")


_STYLES = (f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?><styleSheet xmlns='{MAIN}'>"
           "<fonts count='2'><font><sz val='11'/><name val='Calibri'/></font><font><b/><sz val='11'/><name val='Calibri'/></font></fonts>"
           "<fills count='2'><fill><patternFill patternType='none'/></fill><fill><patternFill patternType='gray125'/></fill></fills>"
           "<borders count='1'><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
           "<cellStyleXfs count='1'><xf numFmtId='0' fontId='0' fillId='0' borderId='0'/></cellStyleXfs>"
           "<cellXfs count='4'><xf numFmtId='0' fontId='0' fillId='0' borderId='0' xfId='0'/>"
           "<xf numFmtId='0' fontId='1' fillId='0' borderId='0' xfId='0' applyFont='1'/>"
           "<xf numFmtId='4' fontId='0' fillId='0' borderId='0' xfId='0' applyNumberFormat='1'/>"
           "<xf numFmtId='4' fontId='1' fillId='0' borderId='0' xfId='0' applyFont='1' applyNumberFormat='1'/></cellXfs>"
           "<cellStyles count='1'><cellStyle name='Normal' xfId='0' builtinId='0'/></cellStyles></styleSheet>")


def workbook(sheets):
    """sheets: list of (name, rows). Returns the .xlsx file as bytes."""
    if not sheets:
        sheets = [("Sheet1", [])]
    used, names = set(), []
    for name, _ in sheets:
        names.append(_clean_name(name, used))
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        overrides = "".join(
            f"<Override PartName='/xl/worksheets/sheet{i}.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/>"
            for i in range(1, len(sheets) + 1))
        z.writestr("[Content_Types].xml",
                   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
                   "<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
                   "<Default Extension='xml' ContentType='application/xml'/>"
                   "<Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/>"
                   f"{overrides}<Override PartName='/xl/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'/></Types>")
        z.writestr("_rels/.rels",
                   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   f"<Relationship Id='rId1' Type='{REL}/officeDocument' Target='xl/workbook.xml'/></Relationships>")
        z.writestr("xl/workbook.xml",
                   f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?><workbook xmlns='{MAIN}' xmlns:r='{REL}'><sheets>"
                   + "".join(f"<sheet name='{escape(n, {chr(39): '&apos;'})}' sheetId='{i}' r:id='rId{i}'/>" for i, n in enumerate(names, 1))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   + "".join(f"<Relationship Id='rId{i}' Type='{REL}/worksheet' Target='worksheets/sheet{i}.xml'/>" for i in range(1, len(sheets) + 1))
                   + f"<Relationship Id='rId{len(sheets) + 1}' Type='{REL}/styles' Target='styles.xml'/></Relationships>")
        z.writestr("xl/styles.xml", _STYLES)
        for i, (_, rows) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))
    return mem.getvalue()
