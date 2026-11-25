"""
peak_file.py - The "Save Peak Info" Excel file: the columns a saved row can
have, reading and writing the .xlsx files, and the list of the files saved
to lately.

A peak file has one sheet named "Peaks". Row 1 holds the column headers, and
each row below it is one saved peak. Columns are found by their header, so
their order doesn't matter, and a header the app doesn't know is a text
column. The header text is part of the file format: once files exist, never
rename one, or old files lose that column. Adding items is fine, and so is
changing a header's case, since headers are compared ignoring case.

Numbers are saved as measured, not rounded. A column's decimals set only how
many places the dialog and the cell's number format show, and the dialog
rounds the way Excel does (see number_text), so both show the same text.

Rows are never overwritten. A file keeps one latest row per peak (see
find_same): a Save adds its rows like any other and marks the earlier rows
of the same peaks old, in their Status cells, so a sample's history stays in
the file. Or it deletes them, when the dialog says so (save's earlier).

No Dash here. plot.py and peak_dialog.py pass in plain values.
"""
import datetime as dt
import math
import os
import unicodedata
from copy import copy
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import NamedTuple, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

SHEET = 'Peaks'
# Two rows are the same peak when they have the same Label/SN and a λ this
# close (nm), whatever their date, source or detector. Each Save marks the
# earlier rows of its peaks old, or deletes them (see save's earlier), so a
# peak's latest row is always the one saved last.
SAME_PEAK_NM = 0.01
# The Status column's values: LATEST for a peak's row saved last, OLD for
# its earlier ones. Any text not in OLD_STATUSES counts as latest, so older
# files' "current" rows do too, and their "replaced" rows count as old.
LATEST, OLD = 'latest', 'old'
OLD_STATUSES = (OLD, 'replaced')    # "replaced": the word before "old"
OLD_STATUS_COLOR = 'FFC00000'       # an old row's Status: Excel's dark red; the rest stays as it is
# What a Save does with the earlier rows of the peaks it saves (save's
# earlier): MARK them old, or DELETE them.
MARK, DELETE = 'mark', 'delete'
MAX_DECIMALS = 10           # the same limit as the tables' Customize dialog
DATE_FORMAT = 'mm/dd/yyyy'  # Excel's format for the Date column
TIME_FORMAT = 'hh:mm:ss'    # Excel's format for the Time column
TEXT = 'text'               # the column dropdown's value for "Text Column…"
# Every cell a Save writes, the header's too, is centered and has a line
# under it, so each row has one (#165). Hair is Excel's thinnest line, a step
# thinner than its usual thin one.
CENTER = Alignment(horizontal='center')
ROW_LINE = Border(bottom=Side(style='hair'))
# Columns are as narrow as they can be, so all of them print on one page
# (see fit_widths): the header wraps, the rows below it don't.
HEADER = Alignment(horizontal='center', wrap_text=True)
MIN_WIDTH = 5   # characters: a column of 1-digit numbers still shows "Tube" whole
# A new file prints with Excel's "Narrow" margins (inches), scaled to "Fit All
# Columns on One Page", with its file name at the top of every page (PAGE_HEADER:
# Excel's code for the file's name, so a renamed file prints its new name).
# Set only when the file is made: later Saves keep whatever print settings it
# has, changes made in Excel included.
NARROW_MARGINS = dict(left=0.25, right=0.25, top=0.75, bottom=0.75, header=0.3, footer=0.3)
PAGE_HEADER = '&F'
PAGE_HEADER_PT = 14   # its size: regular, not bold (user)


class PeakFileError(Exception):
    """A problem with a peak file, worded for the dialog."""


class Item(NamedTuple):
    key: str                        # stable id, used by the dialog and its session memory
    header: str                     # the column header, in the file and in the dropdown
    group: str                      # its group in the column dropdowns (see column_options)
    decimals: Optional[int] = None  # starting decimals; None = no decimals control


# The headers are in title case. Headers are compared ignoring case (see
# norm), so files saved before that, with "Depth, max (dB)" and the like,
# still work. Every item can be picked, removed or changed (#166); a new file
# starts with DEFAULT_COLUMNS, and Save needs the REQUIRED ones.
ITEMS = [
    Item('status',       'Status',             'Required'),
    Item('label',        'Label/SN',           'Required'),
    Item('wl',           'λ (nm)',             'Required', 1),
    Item('depth_max',    'Depth, Max (dB)',    'Peak', 3),
    Item('depth_avg',    'Depth, Avg (dB)',    'Peak', 3),
    Item('depth_min',    'Depth, Min (dB)',    'Peak', 3),
    Item('depth_custom', 'Depth, Custom (dB)', 'Peak', 3),
    Item('width_max',    'Width, Max (pm)',    'Peak', 1),
    Item('width_avg',    'Width, Avg (pm)',    'Peak', 1),
    Item('width_min',    'Width, Min (pm)',    'Peak', 1),
    Item('width_custom', 'Width, Custom (pm)', 'Peak', 1),
    Item('il',           'IL (dB)',            'Peak', 1),
    Item('il_custom',    'IL, Custom (dB)',    'Peak', 1),
    Item('wl_start',     'λ Start (nm)',       'Sweep'),
    Item('wl_stop',      'λ Stop (nm)',        'Sweep'),
    Item('speed',        'Sweep Speed (nm/s)', 'Sweep'),
    Item('step',         'Step Size (pm)',     'Sweep'),
    Item('tls_power',    'TLS Power (dBm)',    'Sweep'),
    Item('avg_time',     'Averaging Time (µs)', 'Sweep'),
    Item('pm_range',     'Power Range (dBm)',  'Sweep'),
    Item('dyn_scans',    'Scans',              'Sweep'),
    Item('decrement',    'Decrement (dB)',     'Sweep'),
    Item('date',         'Date',               'Run'),
    Item('time',         'Time',               'Run'),
    Item('source',       'Source',             'Run'),
    Item('detector',     'Detector',           'Run'),
    Item('temperature',  'Temp. (°C)',         'Run', 1),
    Item('ripple',       'Ripple (dB)',        'Other'),
    Item('item_name',    'Item',               'Other'),
]
ITEM = {i.key: i for i in ITEMS}
# The items you type into each row of the dialog's table, like a text
# column, and that are saved as text.
TYPED = ['ripple', 'item_name']
# The columns a new file starts with, in order (#166). Every file needs the
# REQUIRED ones, which the app relies on: Label/SN and λ, to find a peak's
# earlier rows (see find_same), and Status, to mark them.
DEFAULT_COLUMNS = ['status', 'date', 'source', 'detector', 'label', 'wl']
REQUIRED = ['status', 'label', 'wl']
RECENT_ROWS = 5    # the saved rows the dialog shows from an existing file
RECENT_FILES = 10  # the files the recent list keeps (see remember)
DEFAULT_DECIMALS = {i.key: i.decimals for i in ITEMS if i.decimals is not None}


def norm(header):
    """A header as compared: Unicode-normalized (so µ and μ match), with case
    and extra spaces ignored."""
    return ' '.join(unicodedata.normalize('NFKC', str(header)).casefold().split())


# Headers an item had before it was renamed, so files saved with them keep
# working. Their header in the file stays as it is.
OLD_HEADERS = {'Label (SN)': 'label',               # renamed after 3.0.1
               'Temperature (°C)': 'temperature'}   # shortened after 3.0.2, for narrow columns

_KEY_BY_HEADER = {norm(i.header): i.key for i in ITEMS}
_KEY_BY_HEADER.update({norm(h): key for h, key in OLD_HEADERS.items()})


def column_options():
    """The column dropdown's list: every item, under greyed group headings
    that can't be picked, with "Text Column…" last."""
    opts = []
    for group in ('Required', 'Peak', 'Sweep', 'Run', 'Other'):
        opts.append({'label': f'——— {group} ———', 'value': f'__{group}', 'disabled': True})
        opts += [{'label': i.header, 'value': i.key} for i in ITEMS if i.group == group]
    opts.append({'label': 'Text Column…', 'value': TEXT})
    return opts


def is_builtin(header):
    """Whether header is a built-in column's, in any case (see norm), so a
    file would read that column back as the item, not as text."""
    return norm(header) in _KEY_BY_HEADER


def column_problem(columns):
    """Why a new file's columns can't be saved, or None. columns: (item key,
    or None for a text column; header) pairs in order."""
    keys = {key for key, _ in columns}
    missing = [ITEM[k].header for k in REQUIRED if k not in keys]
    if missing:
        return f'Add a "{missing[0]}" column. A file needs Status, Label/SN and λ (nm).'
    seen = set()
    for key, header in columns:
        name = header.strip()
        if key is None:
            if not name:
                return 'Type a name for each text column.'
            if is_builtin(name):
                return f'"{name}" is a built-in column. Give the text column another name.'
        if norm(name) in seen:
            return f'"{name}" is in the table twice. Remove one.'
        seen.add(norm(name))
    return None


# ---- values ---------------------------------------------------------------------
def parse_date(text):
    """A sweep's date (Params.date) as a date: MM/DD/YYYY since v1.1.6,
    YYYY-MM-DD before that. None if it's neither."""
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except (TypeError, ValueError):
            pass
    return None


def parse_time(text):
    """A sweep's time of day from Params.time, which Run stamps as
    YYYY-MM-DD_HH-MM-SS (config_helper.TIME_FORMAT), and stamped as
    MM/DD/YYYY_HH-MM-SS from v1.1.6 until 2026-09. None if it's neither."""
    for fmt in ('%Y-%m-%d_%H-%M-%S', '%m/%d/%Y_%H-%M-%S'):
        try:
            return dt.datetime.strptime(text, fmt).time()
        except (TypeError, ValueError):
            pass
    return None


def sweep_values(params, il, r):
    """The values every row of one sweep's range r shares, by item key. il:
    the range's insertion loss, or None without a reference."""
    return {
        'date': parse_date(params.date),
        'time': parse_time(params.time),
        'il': il,
        'wl_start': params.wl_start[r],
        'wl_stop': params.wl_stop[r],
        'speed': params.speed,
        'step': params.step_pm,
        'tls_power': params.tls_dbm,
        'avg_time': params.at_us,
        'pm_range': params.pm_range,
        'dyn_scans': params.dyn_scans,
        'decrement': params.decrement,
        'source': params.source,
        'detector': params.detector,
    }


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def decimals_of(key, decimals):
    """The decimals an item uses, or None for an item without a decimals control."""
    if key not in DEFAULT_DECIMALS:
        return None
    return decimals.get(key, DEFAULT_DECIMALS[key])


def number_text(value, decimals):
    """A number's text with this many decimals, rounded the way Excel's
    number format rounds it: from the 15 significant digits Excel keeps,
    with halves away from zero. So 23.25 reads 23.3 in the dialog, as in
    Excel, where Python's own rounding would give 23.2."""
    if not math.isfinite(value):
        return str(value)
    with localcontext() as ctx:
        ctx.prec = 50   # room for 10 decimals on any number this file holds
        q = Decimal(f'{value:.15g}').quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    return f'{q:f}'


def display(key, value, decimals):
    """A value's text in the dialog's table, as the file will show it. "—"
    when there's none."""
    if value is None or value == '':
        return '—'
    if isinstance(value, dt.date):
        return value.strftime('%m/%d/%Y')
    if isinstance(value, dt.time):
        return value.strftime('%H:%M:%S')
    d = decimals_of(key, decimals)
    if d is not None and _is_number(value):
        return number_text(value, d)
    if isinstance(value, float):
        return f'{value:.10g}'
    return str(value)


def number_format(decimals):
    """Excel's number format for a number with this many decimals."""
    return '0' if decimals == 0 else '0.' + '0' * decimals


def format_decimals(fmt):
    """The decimals an Excel number format shows, like 3 for '0.000' or
    '#,##0.000'. None for General, text, dates and other formats."""
    if not fmt or fmt in ('General', '@'):
        return None
    section = fmt.split(';')[0]
    if '.' not in section:
        return 0 if ('0' in section or '#' in section) and '/' not in section else None
    n = 0
    for ch in section.split('.', 1)[1]:
        if ch not in '0#':
            break
        n += 1
    return n


# ---- the recent files and the files themselves -----------------------------------
def same_file(a, b):
    """Whether two paths name the same file. Case doesn't count where the
    system ignores it (Windows)."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def recent_files(list_path):
    """The peak files saved to lately, newest first: the lines of the text
    file at list_path, one path per line. [] when it doesn't exist yet or
    can't be read."""
    try:
        with open(list_path, encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except (OSError, ValueError):   # ValueError: not UTF-8
        return []


def remember(list_path, path):
    """Put path at the top of the recent list at list_path, which keeps the
    newest RECENT_FILES. A file that's gone stays on the list, in case its
    drive comes back, until newer files push it off. Raises OSError when the
    list can't be written."""
    path = os.path.abspath(path)
    paths = [path] + [p for p in recent_files(list_path) if not same_file(p, path)]
    tmp = f'{list_path}.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(p + '\n' for p in paths[:RECENT_FILES])
        os.replace(tmp, list_path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def in_use(path):
    """True when another program has the file open for writing. On Windows,
    Excel locks a workbook it has open, so this is how a save would fail."""
    try:
        with open(path, 'r+b'):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def _sheet(wb):
    return wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]


def _load(path):
    name = os.path.basename(path)
    try:
        return openpyxl.load_workbook(path)
    except PermissionError:
        raise PeakFileError(f"Can't open {name}. If another program is using it, close it.")
    except FileNotFoundError:
        raise PeakFileError(f"{name} isn't there anymore. It may have been moved or deleted.")
    except Exception as e:
        raise PeakFileError(f"Can't read {name}: it isn't a valid .xlsx file ({e}).")


def _last_row(ws):
    """The last row with a value in it; 1 when there's only the header."""
    for r in range(ws.max_row, 1, -1):
        if any(c.value not in (None, '') for c in ws[r]):
            return r
    return 1


def _layout(ws, name):
    """A sheet's columns as (column number, item key or None, header), and the
    decimals its numbers show (item key -> decimals, from the last row that
    has a number in that column)."""
    headers = [c.value for c in ws[1]]
    while headers and (headers[-1] is None or str(headers[-1]).strip() == ''):
        headers.pop()
    if not headers:
        raise PeakFileError(f'{name} has no column headers in row 1.')
    cols, seen = [], set()
    for idx, h in enumerate(headers, start=1):
        text = '' if h is None else str(h).strip()
        if not text:
            raise PeakFileError(f'Column {get_column_letter(idx)} of {name} has no header.')
        if norm(text) in seen:
            raise PeakFileError(f'{name} has two "{text}" columns.')
        seen.add(norm(text))
        cols.append((idx, _KEY_BY_HEADER.get(norm(text)), text))
    keys = {key for _, key, _ in cols}
    missing = [ITEM[k].header for k in REQUIRED if k not in keys]
    if missing:
        raise PeakFileError(f'{name} has no {" or ".join(missing)} column, so it '
                            "can't be used for peaks.")
    last = _last_row(ws)
    decimals = {}
    for idx, key, _ in cols:
        if key in DEFAULT_DECIMALS:
            for r in range(last, 1, -1):
                cell = ws.cell(r, idx)
                if _is_number(cell.value):
                    d = format_decimals(cell.number_format)
                    if d is not None:
                        decimals[key] = min(d, MAX_DECIMALS)
                    break
    return cols, decimals


def _label_text(value):
    """A label as the same-peak rule compares it: its text without the
    outer spaces, or None when it's empty."""
    text = '' if value is None else str(value).strip()
    return text or None


def _is_old(status):
    """Whether a Status cell marks its row old (OLD_STATUSES, in any case)."""
    return str(status or '').strip().casefold() in OLD_STATUSES


def _saved(ws, cols):
    """The rows a new row can be the same peak as: {'row': Excel row,
    'label': its label (see _label_text), 'wl': λ, 'old': whether its Status
    marks it old} for each row with a label and a λ. Plain data, since the
    dialog keeps them in a dcc.Store."""
    col = {key: idx for idx, key, _ in cols if key}
    out = []
    for r in range(2, _last_row(ws) + 1):
        label, wl = _label_text(ws.cell(r, col['label']).value), ws.cell(r, col['wl']).value
        if label and _is_number(wl):
            out.append({'row': r, 'label': label, 'wl': float(wl),
                        'old': _is_old(ws.cell(r, col['status']).value)})
    return out


def _cell_text(cell):
    """A saved cell as the file shows it: a number with its cell's decimals
    (see number_text), a date as MM/DD/YYYY, a time as HH:MM:SS. "—" when
    it's empty."""
    v = cell.value
    if v is None or v == '':
        return '—'
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime('%m/%d/%Y')
    if isinstance(v, dt.time):
        return v.strftime('%H:%M:%S')
    if _is_number(v):
        d = format_decimals(cell.number_format)
        if d is not None:
            return number_text(v, d)
        return f'{v:.10g}' if isinstance(v, float) else str(v)
    return str(v)


def _recent(ws, cols):
    """The last RECENT_ROWS saved rows, top to bottom: {'row': Excel row,
    'cells': [text per column]}."""
    out = []
    for r in range(_last_row(ws), 1, -1):
        cells = [ws.cell(r, idx) for idx, _, _ in cols]
        if any(c.value not in (None, '') for c in cells):
            out.append({'row': r, 'cells': [_cell_text(c) for c in cells]})
            if len(out) == RECENT_ROWS:
                break
    return out[::-1]


def read(path):
    """What the dialog needs from a peak file: its columns in order ({'item':
    key} or {'text': header}), the decimals its numbers show, the last few
    rows as text (see _recent), and the rows the new peaks could be the same
    peak as (see _saved), each with its 'cells' as text too.
    Raises PeakFileError."""
    wb = _load(path)
    try:
        ws = _sheet(wb)
        cols, decimals = _layout(ws, os.path.basename(path))
        saved = _saved(ws, cols)
        for s in saved:
            s['cells'] = [_cell_text(ws.cell(s['row'], idx)) for idx, _, _ in cols]
        return {'columns': [{'item': key} if key else {'text': header} for _, key, header in cols],
                'decimals': decimals,
                'saved': saved,
                'recent': _recent(ws, cols)}
    finally:
        wb.close()


def same_wl(a, b):
    """Whether two λ (nm) can be the same peak's: within SAME_PEAK_NM. The
    1e-9 keeps a gap of exactly 10 pm (two 5 pm steps, say) inside, which
    float error could push just past it."""
    return abs(a - b) <= SAME_PEAK_NM + 1e-9


def find_same(saved, values, earlier=MARK):
    """The Excel rows a new row with these values (item key -> value) makes
    earlier: the saved rows (see _saved) of the same peak, which is the same
    label and a λ within SAME_PEAK_NM (see same_wl). To MARK, only the ones
    not old yet; to DELETE, every one, old ones too. [] when the new row has
    no label or no λ."""
    label, wl = _label_text(values.get('label')), values.get('wl')
    if not label or not _is_number(wl):
        return []
    return [s['row'] for s in saved if s['label'] == label and same_wl(s['wl'], wl)
            and (earlier == DELETE or not s['old'])]


# ---- writing ------------------------------------------------------------------------
def _write(cell, key, value, decimals):
    """One cell. A number is saved as it is, and an item with decimals gets
    the number format that shows them, as the dialog did. key None = a text
    column. A typed item (TYPED) is text too."""
    if value is None or value == '':
        cell.value = None
    elif key is None or key == 'label' or key in TYPED:
        cell.value = str(value)
        cell.number_format = '@'   # so Excel keeps a typed 0160060 as text too
    elif key == 'date':
        cell.value = value
        cell.number_format = DATE_FORMAT
    elif key == 'time':
        cell.value = value
        cell.number_format = TIME_FORMAT
    else:
        cell.value = value
        d = decimals_of(key, decimals)
        if d is not None and _is_number(value):
            cell.number_format = number_format(d)


def _mark_old(ws, row, cols):
    """Mark a saved row old: OLD in its Status cell, in red (#177). The rest
    of the row stays as it is: black, or grey for a row marked before that."""
    for idx, key, _ in cols:
        if key == 'status':
            cell = ws.cell(row, idx)
            font = copy(cell.font)
            font.color = OLD_STATUS_COLOR
            cell.value, cell.font = OLD, font


def _width(text, bold=False):
    """About how many of Excel's width units text takes. The unit is a
    digit's width in the sheet's font; capitals are wider, and bold text is
    wider still."""
    width = sum(1.3 if ch.isupper() else 1.0 for ch in text)
    return width * 1.1 if bold else width


def fit_widths(ws, cols):
    """Make every column as narrow as it can be, so all of them print on one
    page: as wide as its widest cell below the header, as Excel shows it (see
    _cell_text), and as its header's longest word, so a wrapped header never
    breaks a word in two; MIN_WIDTH at least. The header wraps to that width
    (HEADER), in a file saved before this too, so its header isn't cut off.
    Done on every Save, over every row: a width set by hand in Excel is reset."""
    last = _last_row(ws)
    for idx, _, header in cols:
        ws.cell(1, idx).alignment = HEADER
        cells = (_cell_text(ws.cell(r, idx)) for r in range(2, last + 1))
        widest = max([_width(t) for t in cells if t != '—']
                     + [_width(w, bold=True) for w in str(header).split()] + [MIN_WIDTH])
        ws.column_dimensions[get_column_letter(idx)].width = round(widest + 2, 1)


def _save_atomic(wb, path):
    """Save to a temporary file, then put it in place, so a crash can't leave
    half a file. On Windows, replacing a file Excel has open fails."""
    name = os.path.basename(path)
    tmp = path + '.tmp'
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if isinstance(e, PermissionError):
            raise PeakFileError(f"Can't save {name}. If it's open in Excel, "
                                'close it, then press Save again.')
        raise PeakFileError(f"Can't save {name}: {e.strerror or e}.")


def save(path, rows, *, columns=None, decimals=None, earlier=MARK):
    """Add rows to the peak file at path, after its last row, and return
    (added, earlier_rows): the Excel rows written, and the rows they marked
    old or deleted (Excel rows as they were before this Save).

    rows: one per peak, item key -> value, plus 'texts': {header: text} for
    the text columns. Numbers are saved as they are; the decimals set only
    their number format. Their Status is LATEST.
    columns: for a new file, its columns as (item key or None, header) pairs
    in order. Without it, the file at path must exist, and its header sets
    the columns and its numbers set the decimals.
    decimals: item key -> decimals for a new file, and the fallback for an
    existing file's column that has no number yet.
    earlier: what happens to the saved rows of the same peak (find_same: the
    same label and a λ within SAME_PEAK_NM). MARK marks each row that isn't
    old yet OLD (see _mark_old), even an earlier row of this Save; nothing
    else in it changes. DELETE deletes every one, old ones too (#177). So a
    peak's latest row is the one saved last. Raises PeakFileError.
    """
    name = os.path.basename(path)
    decimals = {**DEFAULT_DECIMALS, **(decimals or {})}
    if columns is not None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = SHEET
        cols = [(i, key, header) for i, (key, header) in enumerate(columns, start=1)]
        bold = Font(bold=True)
        for idx, _, header in cols:
            cell = ws.cell(1, idx, header)
            cell.font, cell.border = bold, ROW_LINE
        ws.freeze_panes = 'A2'
        ws.page_margins = PageMargins(**NARROW_MARGINS)
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0   # 0: as many pages tall as it takes
        ws.oddHeader.center.text = PAGE_HEADER   # every page: no first-page or even-page header of its own
        ws.oddHeader.center.size = PAGE_HEADER_PT
        saved, next_row = [], 2
    else:
        wb = _load(path)
        ws = _sheet(wb)
        cols, file_decimals = _layout(ws, name)
        decimals.update(file_decimals)
        saved, next_row = _saved(ws, cols), _last_row(ws) + 1

    added, done = [], []
    if earlier == DELETE:
        # From the bottom up, so the rows still to delete keep their numbers.
        done = sorted({old for v in rows for old in find_same(saved, v, DELETE)})
        for old in reversed(done):
            ws.delete_rows(old)
        saved, next_row = [], _last_row(ws) + 1
    for values in ({**v, 'status': LATEST} for v in rows):
        texts = {norm(h): t for h, t in values.get('texts', {}).items()}
        if earlier == MARK:
            for old in find_same(saved, values):
                _mark_old(ws, old, cols)
                done.append(old)
            for s in saved:
                s['old'] = s['old'] or s['row'] in done
        for idx, key, header in cols:
            value = values.get(key) if key else texts.get(norm(header))
            cell = ws.cell(next_row, idx)
            _write(cell, key, value, decimals)
            cell.alignment, cell.border = CENTER, ROW_LINE   # empty cells too: a line across the row
        label, wl = _label_text(values.get('label')), values.get('wl')
        if label and _is_number(wl) and earlier == MARK:   # now the latest itself
            saved.append({'row': next_row, 'label': label, 'wl': float(wl), 'old': False})
        added.append(next_row)
        next_row += 1
    # Excel's filter buttons on the header row, stretched over every column
    # and row, new ones included. A filter set in Excel keeps its first cell,
    # so its settings stay on their columns.
    first = ws.auto_filter.ref.split(':')[0] if ws.auto_filter.ref else 'A1'
    ws.auto_filter.ref = f'{first}:{get_column_letter(cols[-1][0])}{_last_row(ws)}'
    fit_widths(ws, cols)
    _save_atomic(wb, path)
    return added, done
