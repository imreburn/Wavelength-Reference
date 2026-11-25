"""
peak_dialog.py - The "Save Peak Info" dialog: its layout, the table that
previews the rows it saves, and how the table's controls change the dialog's
state. plot.py owns the callbacks, the peak values, and what's remembered
across plot windows. peak_file.py reads and writes the files.

The state lives in a dcc.Store ('pf-state') as a plain dict:
  mode   'new' for a new file, where you pick the columns, or 'file' for an
         existing file, whose header sets them
  path   for a file: its full path. '' for a new file, which gets its name
         when Save asks for it
  cols   the columns. For a new file, the ones after the fixed columns
         (Date, Time, Source, Detector, Label/SN, λ (nm), Status); for a
         file, all of them in its order. Each is {'id': n, 'item': key},
         {'id': n, 'text': header} for a text column, or {'id': n, 'sub':
         True} for the sublabel's column. In a file, that's the column named
         like the sublabel, so it keeps its 'text' too.
  sub    the sweep's sublabel column name (Params.sublabel), or None. A new
         file's remembered sublabel column is left out while it's None.
  dec    item key -> decimals
  rows   one per peak: {'id': n, 'peak': 'peak:2' or 'custom', 'texts':
         {column id as str: text}} for the text columns and the typed items
         (peak_file.TYPED)
  start  item key -> the text a new box of that item starts with: for the
         items in CARRIED, the one saved last in this run (see carried)
  saved  for a file: its current rows, which the new peaks could replace,
         with their cells as text (see peak_file.read)
  recent for a file: its last few rows as the file shows them, which the
         table lists above the new rows (see peak_file._recent)
  msg    for a file: why it can't be used, or a warning; '' if neither
  bad    True when msg says why the file can't be used
  next   the next free id for a column or a row
"""
import copy
import os

from dash import dcc, html

import peak_file as pf
from constants import PEAK_TEMPERATURE_RANGE
from plot_tables import DATA_CSS_FONT, WINDOW_CSS_FONT, SMALL_BTN_STYLE

# A new file's fixed columns get ids of their own (the others are numbers).
FIXED_IDS = {'date': 'f-date', 'time': 'f-time', 'source': 'f-source',
             'detector': 'f-detector', 'label': 'f-label', 'wl': 'f-wl', 'status': 'f-status'}
# The File menu's values for its two commands. Its files' values are their paths.
NEW_FILE = '__new'
OPEN_FILE = '__open'
FOLDER_CHARS = 60   # a longer folder is shortened in the File menu
# The headers the table shows on two lines, to keep columns narrow: the
# header is the first line, a space, and the second line, so a comma stays at
# the end of the first line. Any other header is one line.
TWO_LINES = {
    **{f'{q}_{b}': (f'{q.capitalize()},', f'{b.capitalize()} ({u})')
       for q, u in (('depth', 'dB'), ('width', 'pm'))
       for b in ('max', 'avg', 'min', 'custom')},
    'il_custom':   ('IL,', 'Custom (dB)'),
    'wl_start':    ('λ Start', '(nm)'),
    'wl_stop':     ('λ Stop', '(nm)'),
    'speed':       ('Sweep', 'Speed (nm/s)'),
    'step':        ('Step Size', '(pm)'),
    'tls_power':   ('TLS Power', '(dBm)'),
    'avg_time':    ('Averaging', 'Time (µs)'),
    'pm_range':    ('Power', 'Range (dBm)'),
    'decrement':   ('Decrement', '(dB)'),
    'temperature': ('Temperature', '(°C)'),
    'ripple':      ('Ripple', '(dB)'),
}
# The sublabel's column (Params.sublabel): its value in the column dropdowns,
# and the tag above its header, in the decimals row. Everywhere else, in the
# lists, the header and its box's title, it's just its column name ("Tube"),
# the header the file gets.
SUB = 'sublabel'
SUB_TAG = 'Sublabel'
# The typed items whose boxes start with the value saved last in this run,
# the way the Temperature box does (plot.py keeps it; see carried). Item is
# usually the same for every peak and every sweep of a batch. Ripple isn't
# here: it's measured for each peak.
CARRIED = ('item_name',)

ERROR_COLOR = '#C0392B'
WARN_COLOR = '#b35900'
SAVED_COLOR = '#888'   # a file's saved rows, listed above the new ones
LABEL_STYLE = {'fontWeight': 'bold', 'display': 'block', 'marginBottom': '4px'}
FIELD_STYLE = {'width': '180px', 'boxSizing': 'border-box', 'fontSize': '14px', 'padding': '2px 5px'}
# Values and decimals controls are centered; the column headers and the row
# headers (the first column: peaks, a file's row numbers) are left-aligned.
# That's the dialog only: in the file, Save centers every cell it writes,
# headers too (peak_file.CENTER).
CELL = {'padding': '3px 6px', 'whiteSpace': 'nowrap', 'verticalAlign': 'middle',
        'textAlign': 'center'}
ROW_HEAD = {**CELL, 'textAlign': 'left'}
# Headers sit at the top of their row, right under the decimals controls (or
# a text column's name box). Not bold: a dropdown's open list inherits its
# cell's font.
HEAD = {**ROW_HEAD, 'fontSize': '13px', 'fontWeight': 'normal', 'verticalAlign': 'top'}
# A plain header (a new file's fixed columns, or any of a file's) is a box as
# tall as a dropdown, with its lines placed in it like a dropdown's text.
PLAIN_HEAD = {'height': '34px', 'display': 'flex', 'flexDirection': 'column',
              'justifyContent': 'center', 'alignItems': 'flex-start', 'lineHeight': 1.15}
VALUE = {**CELL, 'fontFamily': DATA_CSS_FONT, 'fontSize': '13px',
         'fontVariantNumeric': 'tabular-nums', 'borderTop': '1px solid #e8e8e8'}
# A dropdown is never narrower than its own text (two lines at most, see
# _label) and fills its column, so the dropdowns in a column all match the
# widest. A column is as wide as its widest content: a field, a value, or a
# decimals control. The lists open as wide as their longest option.
DROPDOWN = {'width': '100%', 'minWidth': 'max-content', 'fontSize': '13px'}
TEXT_BOX = {'width': '100%', 'minWidth': '110px', 'boxSizing': 'border-box', 'fontSize': '13px',
            'padding': '2px 5px', 'textAlign': 'center'}


def _lines(key, header):
    """A header as the table shows it: (first line, second line or '')."""
    return TWO_LINES.get(key, (header, ''))


def _label(text, first, second=''):
    """A dropdown option's label: `text` (`first`, a space, `second`) with a
    line break in place of that space. The open list shows it on one line:
    Dash's list doesn't wrap, so the break shows as a space. Dropdowns with
    className "pf-dd" show it on two lines, narrower (plot.py's page
    template). Plain text, not components: Dash 4.5 can draw an empty field
    for a component label after the table is redrawn (#167)."""
    if second and text == f'{first} {second}':
        return f'{first}\n{second}'
    return text


def _column_option(option):
    if option.get('disabled'):                  # a group heading
        return option
    return {'label': _label(option['label'], *_lines(option['value'], option['label'])),
            'value': option['value'], 'search': option['label']}


def _peak_option(option):
    """A peak, named by its wavelength (plot.py): "1568.0 (tested) (deepest)"
    in the list, and "1568.0" over "(tested) (deepest)" in the field. With
    two or more ranges, the list shows a heading over each range's peaks (a
    disabled option, kept as it is)."""
    if option.get('disabled'):
        return option
    text = option['label']
    name, _, notes = text.partition(' ')
    return {'label': _label(text, name, notes), 'value': option['value'], 'search': text}


COLUMN_OPTIONS = [_column_option(o) for o in pf.column_options()]


def _sub_shown(state):
    """Whether the table has the sublabel's column."""
    return bool(state.get('sub')) and any(c.get('sub') for c in state['cols'])


def column_options(state, adding=False):
    """A column dropdown's list: COLUMN_OPTIONS, plus the sublabel's column
    name, like "Tube", after the Run items while the sweep has a sublabel.
    The Add Column list (adding) leaves it out once the table has the
    sublabel's column, so it can't be added twice."""
    sub = state.get('sub')
    if not sub or (adding and _sub_shown(state)):
        return COLUMN_OPTIONS
    entry = {'label': sub, 'value': SUB, 'search': sub}
    at = next(i for i, o in enumerate(COLUMN_OPTIONS) if o['value'] == '__Other')
    return COLUMN_OPTIONS[:at] + [entry] + COLUMN_OPTIONS[at:]


def _short_folder(folder):
    """A folder as the File menu shows it: whole, or when it's longer than
    FOLDER_CHARS, its first part, "…", and the last parts that fit. The
    list opens as wide as its longest line, so a long folder would push it
    past the window."""
    parts = folder.split(os.sep)
    if len(folder) <= FOLDER_CHARS or len(parts) < 3:   # < 3: nothing in the middle
        return folder
    tail = parts[-1]
    for part in reversed(parts[1:-1]):
        if len(parts[0]) + len(part) + len(tail) + 4 > FOLDER_CHARS:
            break
        tail = part + os.sep + tail
    return os.sep.join([parts[0], '…', tail])


def file_options(paths):
    """The File menu: New File, Open File…, then the files in paths (newest
    first) under a "Recent Files" heading, each with its folder (the whole
    folder on hover). Plain text: in Dash 4.1, a dropdown whose options are
    components can go back to old options and value when its list opens
    after a callback has changed them."""
    opts = [{'label': 'New File', 'value': NEW_FILE},
            {'label': 'Open File…', 'value': OPEN_FILE}]
    if paths:
        opts.append({'label': '——— Recent Files ———', 'value': '__recent', 'disabled': True})
    for path in paths:
        name, folder = os.path.basename(path), os.path.dirname(path)
        opts.append({'label': f'{name} — {_short_folder(folder)}', 'value': path, 'title': path})
    return opts


def modal(hidden_style, sublabel=None):
    """The dialog, hidden until "Save Peak Info" opens it. The File menu
    comes first, then the boxes that every row shares: Label/SN, the
    sublabel (only when the sweep has one; sublabel is its column name), and
    Temperature. Then the table. The sublabel and Temperature are saved only
    when their columns are in the table, but their boxes are always there.
    Temperature's -/+ buttons step by 0.1, so the browser won't take a second
    decimal place either. Dash sends what the browser won't take as None,
    the same as an empty box, so Save first asks the page which it is
    (plot.py), and problem() checks both."""
    return html.Div(id='peak-modal', style=hidden_style, children=html.Div([
        html.H4('Save Peak Info', style={'marginTop': 0}),
        html.Div([
            # The File menu: a pick acts, and then the value goes back to
            # None, so the field always shows its placeholder, "File Menu"
            # (plot.py's pick_peak_file). The line below names the file. No
            # search box. Tall enough for the whole list: 2 commands, a
            # heading and pf.RECENT_FILES files.
            html.Div(dcc.Dropdown(id='peak-file-select', options=[], value=None,
                                  placeholder='File Menu', clearable=False, searchable=False,
                                  maxHeight=480, className='pf-file-dd',
                                  style={'width': '280px'})),
            html.Div([html.Label('Label/SN', style=LABEL_STYLE),
                      dcc.Input(id='peak-label', type='text', placeholder='Required',
                                debounce=False, style=FIELD_STYLE)]),
            # Titled with its column's header, like "Tube", as Label/SN and
            # Temperature are. Without a sublabel, it's hidden but there, for
            # the callbacks.
            html.Div([html.Label(sublabel or '', style=LABEL_STYLE),
                      dcc.Input(id='peak-sublabel', type='text', placeholder='Optional',
                                debounce=False, style=FIELD_STYLE)],
                     id='peak-sublabel-box', style=None if sublabel else {'display': 'none'}),
            html.Div([
                html.Label('Temperature (°C)', style=LABEL_STYLE),
                # Wide enough for "Optional" between Dash 4's -/+ buttons.
                dcc.Input(id='peak-temperature', type='number', placeholder='Optional', step=0.1,
                          debounce=False, style={**FIELD_STYLE, 'width': '170px'})]),
        ], style={'display': 'flex', 'gap': '16px', 'alignItems': 'flex-end', 'flexWrap': 'wrap'}),
        # Under the File menu: the file Save writes to (see file_line), then a
        # reminder to press Save (see save_hint).
        html.Div(id='pf-file-path', style={'fontSize': '12px', 'marginTop': '4px',
                                           'overflowWrap': 'anywhere'}),
        html.Div(id='pf-save-hint', style={'fontSize': '12px', 'color': SAVED_COLOR,
                                           'marginTop': '2px'}),
        html.Div(id='pf-file-msg', style={'fontSize': '12px', 'minHeight': '16px', 'marginTop': '6px'}),
        # Scrolls sideways when there are more columns than fit. Dash 4's
        # dropdown menus are position: fixed, so this doesn't clip them.
        html.Div(id='pf-table', style={'overflowX': 'auto', 'paddingBottom': '4px'}),
        html.Div(id='peak-modal-error', style={'color': ERROR_COLOR, 'fontSize': '12px',
                                               'minHeight': '16px', 'margin': '8px 0'}),
        html.Div([
            html.Button('Cancel (Esc)', id='peak-cancel', n_clicks=0),
            html.Button('Save', id='peak-save-confirm', n_clicks=0, style={'marginLeft': '8px'}),
        ], style={'textAlign': 'right'}),
        dcc.Store(id='pf-state', data=None),
        # Save's click with the browser's verdict on the Temperature box (see
        # plot.py's close_or_save_peak).
        dcc.Store(id='pf-save-request', data=None),
    ], style={'backgroundColor': 'white', 'padding': '20px 24px', 'borderRadius': '8px',
              'width': 'fit-content', 'minWidth': '560px', 'maxWidth': '95vw',
              'maxHeight': '90vh', 'overflowY': 'auto', 'boxSizing': 'border-box',
              'fontFamily': WINDOW_CSS_FONT, 'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}))


# ---- the state ---------------------------------------------------------------------
def _starts(start):
    """The start texts a state keeps: CARRIED items only, and not empty ones."""
    return {k: v for k, v in (start or {}).items() if k in CARRIED and v}


def new_file_state(columns, decimals, sub=None, start=None):
    """A new file's state, from the remembered columns ([{'item': key},
    {'text': name} or {'sub': True}]) and decimals. sub: the sweep's
    sublabel column name, or None. start: item key -> what its boxes start
    with (see carried)."""
    cols = [{'id': i, **c} for i, c in enumerate(columns, start=1)]
    return {'mode': 'new', 'path': '', 'cols': cols, 'dec': {**pf.DEFAULT_DECIMALS, **decimals},
            'sub': sub, 'start': _starts(start), 'rows': [], 'saved': [], 'recent': [],
            'msg': '', 'bad': False, 'next': len(cols) + 1}


def file_state(path, decimals, sub=None, start=None):
    """An existing file's state, read from disk. decimals: the fallback for a
    column with no number in it yet. sub: the sweep's sublabel column name,
    or None; the file's column with that name, in any case, is the
    sublabel's. start: as for new_file_state. A file that can't be used
    gives a state with bad=True and the reason in msg."""
    try:
        info = pf.read(path)
    except pf.PeakFileError as e:
        return {'mode': 'file', 'path': path, 'cols': [], 'dec': dict(pf.DEFAULT_DECIMALS),
                'sub': sub, 'start': _starts(start), 'rows': [], 'saved': [], 'recent': [],
                'msg': str(e), 'bad': True, 'next': 1}
    cols = [{'id': i, **c} for i, c in enumerate(info['columns'], start=1)]
    for c in cols:
        if sub and 'text' in c and pf.norm(c['text']) == pf.norm(sub):
            c['sub'] = True
    msg = ''
    if pf.in_use(path):
        msg = (f'{os.path.basename(path)} is open in another program, probably Excel. '
               'Close it before you press Save.')
    return {'mode': 'file', 'path': path, 'cols': cols,
            'dec': {**pf.DEFAULT_DECIMALS, **decimals, **info['decimals']},
            'sub': sub, 'start': _starts(start), 'rows': [], 'saved': info['saved'],
            'recent': info['recent'], 'msg': msg, 'bad': False, 'next': len(cols) + 1}


def add_row(state, peak):
    """Add a row for peak (in place). Its boxes of the CARRIED items start
    with the state's start texts."""
    start = state.get('start', {})
    texts = {str(cid): start[key] for cid, key, _ in _columns(state) if key in start}
    state['rows'].append({'id': state['next'], 'peak': peak, 'texts': texts})
    state['next'] += 1


def carried(rows):
    """What the CARRIED items' boxes start with after a Save of these rows
    (the dicts it gave pf.save), for each item it had a column for: the
    last row's text that isn't empty, or '' when every row left it empty.
    plot.py keeps it for the rest of the run, as it does Temperature."""
    out = {}
    for key in CARRIED:
        texts = [r[key] for r in rows if key in r]
        if texts:
            filled = [t for t in texts if t]
            out[key] = filled[-1] if filled else ''
    return out


def session_columns(state):
    """A new file's columns as the session remembers them (no ids, no cell text)."""
    return [{k: v for k, v in c.items() if k != 'id'} for c in state['cols']]


def _columns(state):
    """(column id, key, header) per column, in order. key: an item key, SUB
    for the sublabel's column, or None for a text column. A new file's
    sublabel column is left out while the sweep has no sublabel."""
    cols = []
    for c in state['cols']:
        if c.get('sub'):
            if state.get('sub'):
                cols.append((c['id'], SUB, c.get('text') or state['sub']))
        elif 'item' in c:
            cols.append((c['id'], c['item'], pf.ITEM[c['item']].header))
        else:
            cols.append((c['id'], None, c['text']))
    if state['mode'] == 'new':
        cols = [(FIXED_IDS[k], k, pf.ITEM[k].header) for k in pf.FIXED] + cols
    return cols


def file_columns(state):
    """A new file's columns as (item key or None, header) pairs, fixed ones
    first. The file has no sublabel item: its column is a text column."""
    return [(None if key == SUB else key, header.strip()) for _, key, header in _columns(state)]


def row_texts(state, row):
    """A row's text cells by column header."""
    return {header.strip(): row['texts'].get(str(cid), '')
            for cid, key, header in _columns(state) if key is None}


def entered(state, row, sublabel):
    """What Save takes for a row from the dialog's boxes, not from the sweep:
    'texts', header -> text for the text columns and the sublabel's column
    (sublabel: the sublabel box's text), and item key -> text for the typed
    items (pf.TYPED)."""
    out = {'texts': row_texts(state, row)}
    for cid, key, header in _columns(state):
        if key == SUB:
            out['texts'][header.strip()] = (sublabel or '').strip()
        elif key in pf.TYPED:
            out[key] = row['texts'].get(str(cid), '').strip()
    return out


def _dec_key(state, cid):
    """The item key a decimals control's column shows."""
    for key, fixed_id in FIXED_IDS.items():
        if cid == fixed_id:
            return key
    return next((c.get('item') for c in state['cols'] if c['id'] == cid), None)


def _column_choice(value, state):
    """Whether a column dropdown's value is one of its options: an item that
    isn't fixed, "Text Column…", or the sublabel's entry while the sweep has
    a sublabel (not a group heading or anything else)."""
    return (value == pf.TEXT or (value in pf.ITEM and value not in pf.FIXED)
            or (value == SUB and bool(state.get('sub'))))


def _kind(col):
    """A column's value in its dropdown: its item key, SUB or pf.TEXT."""
    return col.get('item') or (SUB if col.get('sub') else pf.TEXT)


def _make(col_id, value):
    """A new file's column for a column dropdown's value."""
    if value == pf.TEXT:
        return {'id': col_id, 'text': ''}
    if value == SUB:
        return {'id': col_id, 'sub': True}
    return {'id': col_id, 'item': value}


def update(state, changes, current):
    """The state after a change in the table, or None when nothing changed.

    changes: (component id, value) for each control that fired the callback.
    current: component type -> [(component id, value)] for every control of
    that type in the table now. Edits are read from `current`, so a redrawn
    control, which reports its value again, changes nothing. Adding a column
    or a row and the decimals buttons act only when they're in `changes`.
    """
    s = copy.deepcopy(state)
    cols = {c['id']: c for c in s['cols']}
    rows = {r['id']: r for r in s['rows']}
    gone_cols, gone_rows = set(), set()
    if s['mode'] == 'new':
        for cid, value in ((i['col'], v) for i, v in current.get('pf-col', [])):
            c = cols.get(cid)
            if c is None:
                continue
            if value is None:                           # cleared: remove the column
                gone_cols.add(cid)
            elif value != _kind(c) and _column_choice(value, s):
                # Another kind of column. One that turns into a text column
                # starts with no name.
                c.clear()
                c.update(_make(cid, value))
        for i, value in current.get('pf-name', []):
            c = cols.get(i['col'])
            if c is not None and 'text' in c:
                c['text'] = value or ''
    for i, value in current.get('pf-row', []):
        r = rows.get(i['row'])
        if r is None:
            continue
        if value is None:                               # cleared: remove the row
            gone_rows.add(r['id'])
        else:
            r['peak'] = value
    for i, value in current.get('pf-text', []):
        r = rows.get(i['row'])
        if r is not None:
            if value:
                r['texts'][str(i['col'])] = value
            else:
                r['texts'].pop(str(i['col']), None)
    for i, value in changes:
        kind = i.get('type') if isinstance(i, dict) else None
        if kind == 'pf-dec' and value:
            key = _dec_key(s, i['col'])
            if key in pf.DEFAULT_DECIMALS:
                d = pf.decimals_of(key, s['dec']) + i['step']
                s['dec'][key] = min(max(d, 0), pf.MAX_DECIMALS)
        elif kind == 'pf-add' and value is not None:
            if (i['what'] == 'col' and s['mode'] == 'new' and _column_choice(value, s)
                    and not (value == SUB and _sub_shown(s))):
                s['cols'].append(_make(s['next'], value))
                s['next'] += 1
            elif i['what'] == 'row':
                add_row(s, value)
    s['cols'] = [c for c in s['cols'] if c['id'] not in gone_cols]
    s['rows'] = [r for r in s['rows'] if r['id'] not in gone_rows]
    # A CARRIED item's column that was just added, or just picked in place
    # of another kind, starts each row's box with the start text, as a new
    # row does (add_row). A box someone emptied stays empty.
    start, was = s.get('start', {}), {c['id']: _kind(c) for c in state['cols']}
    for c in s['cols']:
        key = c.get('item')
        if key in start and was.get(c['id']) != key:
            for r in s['rows']:
                r['texts'].setdefault(str(c['id']), start[key])
    # The columns with a box in each row: text columns and typed items.
    text_ids = {str(c['id']) for c in s['cols']
                if ('text' in c and not c.get('sub')) or c.get('item') in pf.TYPED}
    for r in s['rows']:
        r['texts'] = {k: t for k, t in r['texts'].items() if k in text_ids}
    return None if s == state else s


def problem(state, label, values_of, name_of, temperature=None, entry=''):
    """Why Save can't go ahead, worded for the dialog, or None.
    values_of(peak) -> item key -> value for that peak's row, as for table();
    name_of(peak) -> its name, like "1568.0 nm". temperature: the
    Temperature box's number, or None. entry: the browser's verdict on the
    box: '' when it took the text (or the box is empty), 'number' when the
    text isn't a number, 'step' when it has more than one decimal place,
    'range' for any other reason."""
    if state.get('bad'):
        return state['msg']
    if not label:
        return 'Enter a Label/SN.'
    if entry == 'number':
        return 'Temperature must be a number, like 23.5.'
    if entry == 'step':
        return 'Temperature can have only one decimal place.'
    low, high = PEAK_TEMPERATURE_RANGE
    if entry or (temperature is not None and not low <= temperature <= high):
        return f'Temperature must be between {low} and {high} °C.'
    rows = state['rows']
    if not rows:
        return 'Add a peak to save.'
    if state['mode'] == 'new':
        # A text column can't take the sublabel's name either: the file would
        # read it back as the sublabel's column.
        sub = state.get('sub')
        for c in state['cols']:
            if sub and 'text' in c and pf.norm(c['text']) == pf.norm(sub):
                return (f'"{c["text"].strip()}" is the sublabel\'s column. '
                        'Give the text column another name.')
        trouble = pf.column_problem(file_columns(state))
        if trouble:
            return trouble
    for a, ra in enumerate(rows):
        for rb in rows[a + 1:]:
            pa, pb = ra['peak'], rb['peak']
            if pa == pb:
                return f'{name_of(pa)} is in the table twice. Remove one.'
            wa, wb = values_of(pa).get('wl'), values_of(pb).get('wl')
            if wa is not None and wb is not None and pf.same_wl(wa, wb):
                return (f'{name_of(pa)} and {name_of(pb)} are within {pf.SAME_PEAK_NM} nm, '
                        "so they'd be the same row in the file. Remove one.")
    if state['mode'] == 'file':
        taken = {}
        for r in rows:
            for target in pf.find_same(state['saved'], {**values_of(r['peak']), 'label': label}):
                if target in taken:
                    return (f'{taken[target]} and {name_of(r["peak"])} would both replace '
                            'the same saved peak. Remove one.')
                taken[target] = name_of(r['peak'])
    return None


# ---- the table ---------------------------------------------------------------------
def _dec_cell(state, cid, key, header):
    """The cell above a column's header: its decimals control ("− n +"),
    greyed out for a file. A new file's text column, which has no decimals,
    has its name box here instead, so every header stays one dropdown tall.
    The sublabel's column has the tag "Sublabel" here, in a file too."""
    if key is None and state['mode'] == 'new':
        return html.Th(dcc.Input(id={'type': 'pf-name', 'col': cid}, type='text', value=header,
                                 placeholder='Column Name', debounce=True,
                                 style={**TEXT_BOX, 'textAlign': 'left'}),
                       style=CELL)
    if key == SUB:
        return html.Th(html.Span(SUB_TAG, style={'fontSize': '12px', 'fontWeight': 'normal',
                                                 'color': '#555'}), style=CELL)
    d = pf.decimals_of(key, state['dec']) if key else None
    if d is None:
        return html.Th(style=CELL)
    locked = state['mode'] == 'file'
    return html.Th(html.Span([
        html.Button('−', id={'type': 'pf-dec', 'col': cid, 'step': -1}, n_clicks=0,
                    disabled=locked or d <= 0, title='Fewer decimal places', style=SMALL_BTN_STYLE),
        html.Span(str(d), style={'width': '22px', 'textAlign': 'center',
                                 'fontVariantNumeric': 'tabular-nums'}),
        html.Button('+', id={'type': 'pf-dec', 'col': cid, 'step': 1}, n_clicks=0,
                    disabled=locked or d >= pf.MAX_DECIMALS, title='More decimal places',
                    style=SMALL_BTN_STYLE),
    ], style={'display': 'inline-flex', 'alignItems': 'center', 'gap': '2px',
              'fontWeight': 'normal', 'fontSize': '13px'}), style=CELL)


def _plain_head(key, header, grey):
    """A header that isn't a dropdown, on the lines a dropdown would show."""
    first, second = _lines(key, header)
    box = {**PLAIN_HEAD, 'color': '#555'} if grey else PLAIN_HEAD
    return html.Th(html.Div([html.Div(first)] + ([html.Div(second)] if second else []), style=box),
                   style=HEAD)


def _head_cell(state, cid, key, header):
    """A column's header: plain text for a file's columns (grey: they can't
    be changed) and a new file's fixed ones, otherwise a dropdown."""
    if state['mode'] == 'file':
        return _plain_head(key, header, grey=True)
    if cid in FIXED_IDS.values():
        return _plain_head(key, header, grey=False)
    return html.Th(dcc.Dropdown(id={'type': 'pf-col', 'col': cid}, options=column_options(state),
                                value=key or pf.TEXT, clearable=True, maxHeight=320,
                                className='pf-dd', style=DROPDOWN), style=HEAD)


def _status(targets, cols):
    """For a file: whether the row is new or replaces saved rows (targets,
    from state['saved']), on two lines, so the column stays narrow. One row
    is named by its label, then its λ and date; more than one (a file that
    already had two current rows of the peak) by the label, then their row
    numbers, which the rows above show. Shown below the row's peak."""
    style = {'fontSize': '12px', 'marginTop': '2px'}
    if not targets:
        return html.Div('new row', style={**style, 'color': SAVED_COLOR})
    text = {key: t for (_, key, _), t in zip(cols, targets[0]['cells']) if key}
    if len(targets) == 1:
        second = f"{text.get('wl', '—')} nm, {text.get('date', '—')}"
    else:
        nums = [str(t['row']) for t in targets]
        second = f"rows {', '.join(nums[:-1])} and {nums[-1]}"
    return html.Div([f"replaces {text.get('label', '—')}", html.Br(), second],
                    style={**style, 'color': WARN_COLOR})


def _saved_row(saved, cols, replaced):
    """One of a file's saved rows ({'row': Excel row, 'cells': texts}), as
    the file shows it, in grey. When Save will mark it replaced, its row
    number and Status say so in orange."""
    style = {**VALUE, 'color': SAVED_COLOR}
    cells = [html.Td(f"row {saved['row']}", style={**ROW_HEAD, 'fontSize': '12px',
                                                  'color': WARN_COLOR if replaced else SAVED_COLOR})]
    for (_, key, _), text in zip(cols, saved['cells']):
        if key == 'status' and replaced:
            cells.append(html.Td(pf.REPLACED, style={**style, 'color': WARN_COLOR}))
            continue
        if key is None:   # a text column: long notes don't widen the table
            text = html.Div(text, title=text, style={'maxWidth': '140px', 'overflow': 'hidden',
                                                     'textOverflow': 'ellipsis'})
        cells.append(html.Td(text, style=style))
    return html.Tr(cells)


def _saved_rows(state, cols, replaced):
    """A file's last few rows above the new rows, as the file has them, then,
    below a dashed line, the rows Save will mark replaced, even ones that
    are among the last few too."""
    rows = [_saved_row(r, cols, False) for r in state.get('recent', [])]
    more = [_saved_row(s, cols, True) for s in state.get('saved', []) if s['row'] in replaced]
    if rows and more:
        # 2px, so it wins over the value cells' own 1px borders.
        more[0].style = {'borderTop': '2px dashed #bbb'}
    return rows + more


def table(state, peak_options, values_of, label, temperature, sublabel=None):
    """The dialog's table: decimals controls, column headers, a file's last
    few rows and the rows Save will mark replaced, then one row per peak with
    the values as the file will show them, and an "Add Peak…" row.
    values_of(peak) -> item key -> value for that peak's row. sublabel: the
    sublabel box's text, which its column shows in every row. A text column
    and a typed item (pf.TYPED) have a box in each row instead."""
    cols = _columns(state)
    is_new = state['mode'] == 'new'
    label = (label or '').strip()
    peak_options = [_peak_option(o) for o in peak_options]
    decs = [html.Th(style=ROW_HEAD)] + [_dec_cell(state, cid, key, h) for cid, key, h in cols]
    heads = [html.Th(style=ROW_HEAD)] + [_head_cell(state, cid, key, h) for cid, key, h in cols]
    if is_new:
        heads.append(html.Th(dcc.Dropdown(
            id={'type': 'pf-add', 'what': 'col'}, options=column_options(state, adding=True),
            value=None, placeholder='Add Column…', clearable=False, maxHeight=320,
            className='pf-dd', style=DROPDOWN), style=HEAD))
    new_rows, replaced = [], set()
    for r in state['rows']:
        values = {**values_of(r['peak']), 'label': label or None, 'temperature': temperature,
                  'status': pf.CURRENT, SUB: (sublabel or '').strip() or None}
        peak = dcc.Dropdown(id={'type': 'pf-row', 'row': r['id']}, options=peak_options,
                            value=r['peak'], clearable=True, className='pf-dd', style=DROPDOWN)
        first = [peak]
        if not is_new and label and values.get('wl') is not None:
            targets = pf.find_same(state['saved'], values)
            replaced.update(targets)
            first.append(_status([s for s in state['saved'] if s['row'] in targets], cols))
        cells = [html.Td(first, style=ROW_HEAD)]
        for cid, key, _ in cols:
            if key is None or key in pf.TYPED:
                cells.append(html.Td(dcc.Input(
                    id={'type': 'pf-text', 'row': r['id'], 'col': cid}, type='text',
                    value=r['texts'].get(str(cid), ''), debounce=True,
                    style=TEXT_BOX), style=CELL))
            else:
                cells.append(html.Td(pf.display(key, values.get(key), state['dec']), style=VALUE))
        new_rows.append(html.Tr(cells))
    body = _saved_rows(state, cols, replaced)
    if body and new_rows:
        # A line between the file's rows and the new ones.
        new_rows[0].style = {'borderTop': '2px solid #bbb'}
    body += new_rows
    body.append(html.Tr(html.Td(dcc.Dropdown(
        id={'type': 'pf-add', 'what': 'row'}, options=peak_options, value=None,
        placeholder='Add Peak…' if peak_options else 'No Peak to Add',
        disabled=not peak_options, clearable=False, className='pf-dd', style=DROPDOWN),
        style=ROW_HEAD)))
    return html.Table([html.Thead([html.Tr(decs), html.Tr(heads)]), html.Tbody(body)],
                      style={'borderCollapse': 'collapse'})


def file_line(state):
    """The line under the File menu: the file's full path, or for a new
    file, when it gets its name."""
    return state.get('path') or "New file. You'll name it when you press Save."


def save_hint(state):
    """The grey line under file_line's, for a file that can be used: choosing
    a file or a peak doesn't save anything by itself. A new file needs none,
    since its line already mentions Save."""
    if state['mode'] == 'file' and not state['bad']:
        return 'Press Save to write these peaks to the file.'
    return ''


def file_message(state):
    """The line under the file: why it can't be used (red) or a warning."""
    if not state.get('msg'):
        return ''
    return html.Span(state['msg'], style={'color': ERROR_COLOR if state['bad'] else WARN_COLOR})
