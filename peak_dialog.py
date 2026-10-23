"""
peak_dialog.py - The "Save peak info" dialog: its layout, the table that
previews the rows it saves, and how the table's controls change the dialog's
state. plot.py owns the callbacks, the peak values, and what's remembered
across plot windows. peak_file.py reads and writes the files.

The state lives in a dcc.Store ('pf-state') as a plain dict:
  mode   'new' for a new file, where you pick the columns, or 'file' for an
         existing file, whose header sets them
  cols   the columns. For a new file, the ones after the fixed columns
         (Date, Source, Detector, Label (SN), λ (nm)); for a file, all of
         them in its order. Each is {'id': n, 'item': key}, or {'id': n,
         'text': header} for a text column.
  dec    item key -> decimals
  rows   one per peak: {'id': n, 'peak': 'peak:2' or 'custom', 'texts':
         {column id as str: text}}
  saved  for a file: its saved rows, [Excel row, label, λ]
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
from plot_tables import DATA_CSS_FONT, WINDOW_CSS_FONT, SMALL_BTN_STYLE

# A new file's fixed columns get ids of their own (the others are numbers).
FIXED_IDS = {'date': 'f-date', 'source': 'f-source', 'detector': 'f-detector',
             'label': 'f-label', 'wl': 'f-wl'}
# The headers the table shows on two lines, to keep columns narrow. Any other
# header is one line.
TWO_LINES = {
    **{f'{q}_{b}': (q.capitalize(), f'{b} ({u})')
       for q, u in (('depth', 'dB'), ('width', 'pm'))
       for b in ('max', 'avg', 'min', 'custom')},
    'il_custom':   ('IL', 'custom (dB)'),
    'wl_start':    ('λ start', '(nm)'),
    'wl_stop':     ('λ stop', '(nm)'),
    'speed':       ('Sweep', 'speed (nm/s)'),
    'step':        ('Step size', '(pm)'),
    'tls_power':   ('TLS power', '(dBm)'),
    'avg_time':    ('Averaging', 'time (µs)'),
    'pm_range':    ('Power', 'range (dBm)'),
    'decrement':   ('Decrement', '(dB)'),
    'temperature': ('Temperature', '(°C)'),
}

ERROR_COLOR = '#C0392B'
WARN_COLOR = '#b35900'
SAVED_COLOR = '#888'   # a file's saved rows, listed above the new ones
LABEL_STYLE = {'fontWeight': 'bold', 'display': 'block', 'marginBottom': '4px'}
FIELD_STYLE = {'width': '180px', 'boxSizing': 'border-box', 'fontSize': '14px', 'padding': '2px 5px'}
# Values and decimals controls are centered; the column headers and the row
# headers (the first column: peaks, a file's row numbers) are left-aligned.
# That's the dialog only: Save doesn't set an alignment in the file.
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
    """A dropdown option's label: `text` on one line in the open list, and
    `first` over `second` in the dropdown's own field, which is narrower.
    plot.py's page template has the CSS that shows the field version in
    dropdowns with className "pf-dd". The list opens outside the dropdown's
    element, so it keeps the one-line version."""
    lines = [html.Span(first, className='pf-l1')]
    if second:
        lines.append(html.Span(second, className='pf-l2'))
    return html.Span([html.Span(text, className='pf-menu'), html.Span(lines, className='pf-field')])


def _column_option(option):
    if option.get('disabled'):                  # a group heading
        return option
    return {'label': _label(option['label'], *_lines(option['value'], option['label'])),
            'value': option['value'], 'search': option['label']}


def _peak_option(option):
    """A peak: "P2 (tested) (deepest)" in the list, and "P2" over "tested,
    deepest" in the field."""
    name, _, tags = option['label'].partition(' ')
    tags = ', '.join(t.strip('()') for t in tags.split())
    return {'label': _label(option['label'], name, tags), 'value': option['value'],
            'search': option['label']}


COLUMN_OPTIONS = [_column_option(o) for o in pf.column_options()]


def modal(hidden_style):
    """The dialog, hidden until "Save peak info" opens it. The file comes
    first, then the Label (SN) and Temperature boxes that every row shares,
    then the table. Temperature is saved only when its column is in the
    table, but its box is always there."""
    return html.Div(id='peak-modal', style=hidden_style, children=html.Div([
        html.H4('Save peak info', style={'marginTop': 0}),
        html.Div([
            html.Div([html.Label('File', style=LABEL_STYLE),
                      dcc.Dropdown(id='peak-file-select', options=[], value='',
                                   clearable=False, style={'width': '280px'})]),
            html.Div([html.Label('Label (SN)', style=LABEL_STYLE),
                      dcc.Input(id='peak-label', type='text', placeholder='Required',
                                debounce=False, style=FIELD_STYLE)]),
            html.Div([
                html.Label('Temperature (°C)', style=LABEL_STYLE),
                # Wide enough for "Optional" between Dash 4's -/+ buttons.
                dcc.Input(id='peak-temperature', type='number', placeholder='Optional',
                          debounce=False, style={**FIELD_STYLE, 'width': '170px'})]),
        ], style={'display': 'flex', 'gap': '16px', 'alignItems': 'flex-end', 'flexWrap': 'wrap'}),
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
    ], style={'backgroundColor': 'white', 'padding': '20px 24px', 'borderRadius': '8px',
              'width': 'fit-content', 'minWidth': '560px', 'maxWidth': '95vw',
              'maxHeight': '90vh', 'overflowY': 'auto', 'boxSizing': 'border-box',
              'fontFamily': WINDOW_CSS_FONT, 'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}))


# ---- the state ---------------------------------------------------------------------
def new_file_state(columns, decimals):
    """A new file's state, from the remembered columns ([{'item': key} or
    {'text': name}]) and decimals."""
    cols = [{'id': i, **c} for i, c in enumerate(columns, start=1)]
    return {'mode': 'new', 'cols': cols, 'dec': {**pf.DEFAULT_DECIMALS, **decimals},
            'rows': [], 'saved': [], 'recent': [], 'msg': '', 'bad': False,
            'next': len(cols) + 1}


def file_state(path, decimals):
    """An existing file's state, read from disk. decimals: the fallback for a
    column with no number in it yet. A file that can't be used gives a state
    with bad=True and the reason in msg."""
    try:
        info = pf.read(path)
    except pf.PeakFileError as e:
        return {'mode': 'file', 'cols': [], 'dec': dict(pf.DEFAULT_DECIMALS), 'rows': [],
                'saved': [], 'recent': [], 'msg': str(e), 'bad': True, 'next': 1}
    cols = [{'id': i, **c} for i, c in enumerate(info['columns'], start=1)]
    msg = ''
    if pf.in_use(path):
        msg = (f'{os.path.basename(path)} is open in another program, probably Excel. '
               'Close it before you press Save.')
    return {'mode': 'file', 'cols': cols,
            'dec': {**pf.DEFAULT_DECIMALS, **decimals, **info['decimals']},
            'rows': [], 'saved': info['saved'], 'recent': info['recent'],
            'msg': msg, 'bad': False, 'next': len(cols) + 1}


def add_row(state, peak):
    """Add a row for peak (in place)."""
    state['rows'].append({'id': state['next'], 'peak': peak, 'texts': {}})
    state['next'] += 1


def session_columns(state):
    """A new file's columns as the session remembers them (no ids, no cell text)."""
    return [{k: v for k, v in c.items() if k != 'id'} for c in state['cols']]


def _columns(state):
    """(column id, item key or None for a text column, header) per column, in order."""
    cols = [(c['id'], c.get('item'), pf.ITEM[c['item']].header if 'item' in c else c['text'])
            for c in state['cols']]
    if state['mode'] == 'new':
        cols = [(FIXED_IDS[k], k, pf.ITEM[k].header) for k in pf.FIXED] + cols
    return cols


def file_columns(state):
    """A new file's columns as (item key or None, header) pairs, fixed ones first."""
    return [(key, header.strip()) for _, key, header in _columns(state)]


def row_texts(state, row):
    """A row's text cells by column header."""
    return {header.strip(): row['texts'].get(str(cid), '')
            for cid, key, header in _columns(state) if key is None}


def _dec_key(state, cid):
    """The item key a decimals control's column shows."""
    for key, fixed_id in FIXED_IDS.items():
        if cid == fixed_id:
            return key
    return next((c.get('item') for c in state['cols'] if c['id'] == cid), None)


def _column_choice(value):
    """Whether a column dropdown's value is one of its options: an item that
    isn't fixed, or "Text column…" (not a group heading or anything else)."""
    return value == pf.TEXT or (value in pf.ITEM and value not in pf.FIXED)


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
            elif value == pf.TEXT and 'item' in c:
                del c['item']
                c['text'] = ''
            elif value != pf.TEXT and c.get('item') != value and _column_choice(value):
                c.pop('text', None)
                c['item'] = value
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
            if i['what'] == 'col' and s['mode'] == 'new' and _column_choice(value):
                col = {'id': s['next'], 'text': ''} if value == pf.TEXT else {'id': s['next'], 'item': value}
                s['cols'].append(col)
                s['next'] += 1
            elif i['what'] == 'row':
                add_row(s, value)
    s['cols'] = [c for c in s['cols'] if c['id'] not in gone_cols]
    s['rows'] = [r for r in s['rows'] if r['id'] not in gone_rows]
    text_ids = {str(c['id']) for c in s['cols'] if 'text' in c}
    for r in s['rows']:
        r['texts'] = {k: t for k, t in r['texts'].items() if k in text_ids}
    return None if s == state else s


def problem(state, label, values_of, name_of):
    """Why Save can't go ahead, worded for the dialog, or None.
    values_of(peak) -> item key -> value for that peak's row, as for table();
    name_of(peak) -> its name, like "P2"."""
    if state.get('bad'):
        return state['msg']
    if not label:
        return 'Enter a Label (SN).'
    rows = state['rows']
    if not rows:
        return 'Add a peak to save.'
    if state['mode'] == 'new':
        trouble = pf.column_problem(file_columns(state))
        if trouble:
            return trouble
    for a, ra in enumerate(rows):
        for rb in rows[a + 1:]:
            pa, pb = ra['peak'], rb['peak']
            if pa == pb:
                return f'{name_of(pa)} is in the table twice. Remove one.'
            wa, wb = values_of(pa).get('wl'), values_of(pb).get('wl')
            if wa is not None and wb is not None and abs(wa - wb) <= pf.SAME_PEAK_NM:
                return (f'{name_of(pa)} and {name_of(pb)} are within {pf.SAME_PEAK_NM} nm, '
                        "so they'd be the same row in the file. Remove one.")
    if state['mode'] == 'file':
        taken = {}
        for r in rows:
            target = pf.find_saved(state['saved'], {**values_of(r['peak']), 'label': label})
            if target is None:
                continue
            if target in taken:
                return (f'{taken[target]} and {name_of(r["peak"])} would both replace '
                        f'row {target}. Remove one.')
            taken[target] = name_of(r['peak'])
    return None


# ---- the table ---------------------------------------------------------------------
def _dec_cell(state, cid, key, header):
    """The cell above a column's header: its decimals control ("− n +"),
    greyed out for a file. A new file's text column, which has no decimals,
    has its name box here instead, so every header stays one dropdown tall."""
    if key is None and state['mode'] == 'new':
        return html.Th(dcc.Input(id={'type': 'pf-name', 'col': cid}, type='text', value=header,
                                 placeholder='Column name', debounce=True,
                                 style={**TEXT_BOX, 'textAlign': 'left'}),
                       style=CELL)
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
    return html.Th(dcc.Dropdown(id={'type': 'pf-col', 'col': cid}, options=COLUMN_OPTIONS,
                                value=key or pf.TEXT, clearable=True, maxHeight=320,
                                className='pf-dd', style=DROPDOWN), style=HEAD)


def _status(target):
    """For a file: whether Save adds the row or replaces a saved one, shown
    below the row's peak."""
    style = {'fontSize': '12px', 'marginTop': '2px'}
    if target is None:
        return html.Div('new row', style={**style, 'color': SAVED_COLOR})
    return html.Div(f'replaces row {target}', style={**style, 'color': WARN_COLOR})


def _saved_rows(state, cols, replaced):
    """A file's last few rows, as the file shows them, in grey above the new
    rows. A row that Save would replace is crossed out."""
    rows = []
    for saved in state.get('recent', []):
        gone = saved['row'] in replaced
        style = {**VALUE, 'color': SAVED_COLOR}
        if gone:
            style['textDecoration'] = 'line-through'
        cells = [html.Td(f"row {saved['row']}",
                         style={**ROW_HEAD, 'fontSize': '12px',
                                'color': WARN_COLOR if gone else SAVED_COLOR})]
        for (_, key, _), text in zip(cols, saved['cells']):
            if key is None:   # a text column: long notes don't widen the table
                text = html.Div(text, title=text, style={'maxWidth': '140px', 'overflow': 'hidden',
                                                         'textOverflow': 'ellipsis'})
            cells.append(html.Td(text, style=style))
        rows.append(html.Tr(cells))
    return rows


def table(state, peak_options, values_of, label, temperature):
    """The dialog's table: decimals controls, column headers, a file's last
    few rows, then one row per peak with the values as they'll be saved, and
    an "Add peak…" row. values_of(peak) -> item key -> value for that peak's row."""
    cols = _columns(state)
    is_new = state['mode'] == 'new'
    label = (label or '').strip()
    peak_options = [_peak_option(o) for o in peak_options]
    decs = [html.Th(style=ROW_HEAD)] + [_dec_cell(state, cid, key, h) for cid, key, h in cols]
    heads = [html.Th(style=ROW_HEAD)] + [_head_cell(state, cid, key, h) for cid, key, h in cols]
    if is_new:
        heads.append(html.Th(dcc.Dropdown(
            id={'type': 'pf-add', 'what': 'col'}, options=COLUMN_OPTIONS, value=None,
            placeholder='Add column…', clearable=False, maxHeight=320, className='pf-dd',
            style=DROPDOWN), style=HEAD))
    new_rows, replaced = [], set()
    for r in state['rows']:
        values = {**values_of(r['peak']), 'label': label or None, 'temperature': temperature}
        peak = dcc.Dropdown(id={'type': 'pf-row', 'row': r['id']}, options=peak_options,
                            value=r['peak'], clearable=True, className='pf-dd', style=DROPDOWN)
        first = [peak]
        if not is_new and label and values.get('wl') is not None:
            target = pf.find_saved(state['saved'], values)
            if target is not None:
                replaced.add(target)
            first.append(_status(target))
        cells = [html.Td(first, style=ROW_HEAD)]
        for cid, key, _ in cols:
            if key is None:
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
        placeholder='Add peak…' if peak_options else 'No peak to add',
        disabled=not peak_options, clearable=False, className='pf-dd', style=DROPDOWN),
        style=ROW_HEAD)))
    return html.Table([html.Thead([html.Tr(decs), html.Tr(heads)]), html.Tbody(body)],
                      style={'borderCollapse': 'collapse'})


def file_message(state):
    """The line under the file: why it can't be used (red) or a warning."""
    if not state.get('msg'):
        return ''
    return html.Span(state['msg'], style={'color': ERROR_COLOR if state['bad'] else WARN_COLOR})
