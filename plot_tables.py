"""
plot_tables.py - The tables under the graph window's plot: the Pass/Fail
table, the Custom peak table, the Delta table and the (auto-detected) Peak
table. Their columns, look and number formatting, and the "Customize" dialog
that shows/hides/reorders columns and sets decimals.

Layout and formatting only. plot.py owns the callbacks and the choices that are
remembered across plot windows.
"""
import math
import re

from dash import dcc, html

from constants import DATA_FONT, GRAPH_WINDOW_FONT


def css_font(family):
    """CSS font stack for a font family; None = the system's interface font."""
    return f'"{family}", sans-serif' if family else 'system-ui, sans-serif'


# The graph window's two fonts (see constants.py): one for its buttons, sidebar
# and dialogs, one for the tables and the plot text.
WINDOW_CSS_FONT = css_font(GRAPH_WINDOW_FONT)
DATA_CSS_FONT   = css_font(DATA_FONT)

# Left indent shared by the tables (and their captions).
TABLE_LEFT_MARGIN = '10px'
# Caption shown above each table.
TABLE_TITLE_STYLE = {'fontFamily': DATA_CSS_FONT, 'fontWeight': 'bold', 'fontSize': '13px',
                     'color': '#555', 'margin': '0 0 4px', 'marginLeft': TABLE_LEFT_MARGIN}

# ---- table look ---------------------------------------------------------------
# Centered cells with equal-width (tabular) digits, and a header like the Power
# readout table's: gray semibold text over a rule, no fill. Tahoma at 13 px
# looks about as big as most fonts at 14 px; headers are 12/14 of that and
# group headers (e.g. "Max base") 11/14.
CELL_PX = 13
TABLE_STYLE = {'marginBottom': '10px', 'marginLeft': TABLE_LEFT_MARGIN,
               'width': 'fit-content', 'borderCollapse': 'collapse'}
TD_STYLE = {'fontFamily': DATA_CSS_FONT, 'fontSize': f'{CELL_PX}px', 'fontVariantNumeric': 'tabular-nums',
            'textAlign': 'center', 'padding': '3px 10px', 'borderBottom': '1px solid #e8e8e8',
            'whiteSpace': 'nowrap'}
TH_STYLE = {**TD_STYLE, 'fontSize': f'{round(CELL_PX * 12 / 14, 1)}px', 'fontWeight': 600,
            'color': '#555', 'borderBottom': '1px solid #bbb', 'verticalAlign': 'bottom'}
GROUP_TH_STYLE = {**TH_STYLE, 'fontSize': f'{round(CELL_PX * 11 / 14, 1)}px', 'color': '#777',
                  'borderBottom': '1px solid #ddd', 'paddingBottom': '1px'}
DEEPEST_BG  = '#FFF3B0'   # peak table: the deepest peak
CRITERIA_BG = '#ADD8E6'   # peak table: the peak checked against Pass/Fail criteria
STRIPE_BG   = '#F2F2F2'   # every other row of the marker and Pass/Fail tables (same as Save peak info's read-only fields)

# ---- number formatting ----------------------------------------------------------
# Default decimal places by unit: 'dB|dBm' is a power reading (P: dB with a
# reference, dBm without), 'dB' a difference such as a depth. A table can set
# its own default for a column ('decimals'), and the Customize dialog changes
# them per column.
UNIT_DECIMALS = {'nm': 4, 'dB|dBm': 3, 'dB': 2, 'pm': 1, 'dB/nm': 1}
MAX_DECIMALS = 10
MINUS = '−'   # the true minus sign, as on the plot's axis labels
EMPTY = '—'        # a cell with no value (rather than a blank that looks broken)

# ---- the tables -------------------------------------------------------------------
# Per table: its name (the caption and the Customize dialog's title; the Show /
# hide popup keeps its own "Peak table"), an optional grey note after the caption,
# its columns in default order as id -> (group, header) (a group
# puts one spanning header over its adjacent columns), the column that can't be
# hidden, each numeric column's unit (which sets its default decimals; columns
# without one, like Ch and the IDs, get no decimals control), any column whose
# default decimals differ from its unit's, and whether every other row is shaded.
# A 'decimals_only' table's Customize dialog sets just its columns' decimals.
_PEAK_LABELS = {'Ch': (None, 'Ch'), 'Peak': (None, 'ID'), 'Category': (None, 'Note'),
                'x': ('Peak', 'λ (nm)'), 'y': ('Peak', 'P (dB|dBm)'),
                # The sweep's insertion loss, the same on every row. Only a
                # window with a reference has it; the others pass 'IL' as
                # absent to build_table and column_list.
                'IL': ('Reference', 'IL (dB)')}
for _b, _name in [('max', 'Max'), ('avg', 'Avg'), ('min', 'Min')]:
    _PEAK_LABELS[f'Depth_{_b}'] = (f'{_name} base', 'Depth (dB)')
    _PEAK_LABELS[f'FWHM_{_b}'] = (f'{_name} base', 'Width (pm)')

TABLES = {
    'custom': {
        'title': 'Custom peak',
        # The two Bandwidth markers: B1 is the peak, B2 the base.
        'labels': {'Ch': (None, 'Ch'), 'Peak': (None, 'ID'),
                   'x': ('Peak (B1)', 'λ (nm)'),
                   'y': ('Peak (B1)', 'P (dB|dBm)'),
                   'Depth': ('Peak properties', 'Depth (dB)'),
                   # The width, and how far above B1 it was measured.
                   'Width': ('Peak properties', 'Width (pm)'),
                   'Amplitude': ('Peak properties', 'Amplitude (dB)'),
                   'base_x': ('Base (B2)', 'λ (nm)'),
                   'base_y': ('Base (B2)', 'P (dB|dBm)')},
        'locked': 'Peak',
        'units': {'x': 'nm', 'y': 'dB|dBm', 'Depth': 'dB', 'Width': 'pm', 'Amplitude': 'dB',
                  'base_x': 'nm', 'base_y': 'dB|dBm'},
        # As fine as the Manual "Bandwidth amplitude (dB)" field's 0.001 step.
        'decimals': {'Amplitude': 3},
        'striped': True,   # its only row is the first, so it's shaded
    },
    'delta': {
        'title': 'Delta',
        'labels': {'Marker': (None, 'ID'), 'x': (None, 'λ (nm)'), 'y': (None, 'P (dB|dBm)'),
                   'mid_x': (None, 'Mid λ (nm)'), 'mid_y': (None, 'Mid P (dB|dBm)'),
                   # A difference of two powers is in dB, whether they were in dB or dBm.
                   'dx': (None, '|Δλ| (nm)'), 'dy': (None, '|ΔP| (dB)'),
                   'slope': (None, 'Slope (dB/nm)')},
        'locked': 'Marker',
        'units': {'x': 'nm', 'y': 'dB|dBm', 'mid_x': 'nm', 'mid_y': 'dB|dBm', 'dx': 'nm',
                  'dy': 'dB', 'slope': 'dB/nm'},
        'striped': True,
    },
    'peak': {
        'title': 'Peak',
        'note': '(auto-detected)',
        'labels': _PEAK_LABELS,
        'locked': 'Peak',
        'units': {'x': 'nm', 'y': 'dB|dBm', 'IL': 'dB', 'Depth_max': 'dB', 'FWHM_max': 'pm',
                  'Depth_avg': 'dB', 'FWHM_avg': 'pm', 'Depth_min': 'dB', 'FWHM_min': 'pm'},
        'decimals': {'IL': 1},
        'striped': False,  # its rows have their own highlight colors
    },
    'passfail': {
        'title': 'Peak test result',
        # Built by passfail_table, not build_table: its "columns" here are just
        # the Measured row's values, whose decimals the Customize dialog sets.
        # The header part of each label is also the table's column header.
        'decimals_only': True,
        'labels': {'x': ('Measured', 'λ (nm)'), 'depth': ('Measured', 'Depth (dB)'),
                   'width': ('Measured', 'Width (pm)')},
        'locked': None,
        'units': {'x': 'nm', 'depth': 'dB', 'width': 'pm'},
        'striped': True,
    },
}


def default_view(table):
    """A table's column order, hidden columns, and decimals changed by the user."""
    return {'order': list(TABLES[table]['labels']), 'hidden': [], 'decimals': {}}


def decimals_for(table, col, view):
    """Decimal places a column shows now, or None for a column without a unit."""
    unit = TABLES[table]['units'].get(col)
    if unit is None:
        return None
    default = TABLES[table].get('decimals', {}).get(col, UNIT_DECIMALS[unit])
    return view['decimals'].get(col, default)


def number_text(v, dec):
    """v with dec decimals and a true minus sign, and no plus sign. A value that
    rounds to zero shows no sign ("0.00", not "−0.00")."""
    s = f'{v:.{dec}f}'
    if float(s) == 0:
        s = s.lstrip('-')
    return s.replace('-', MINUS)


def _cell_text(table, col, row, dec):
    if table == 'peak' and col == 'Peak':
        return f"P{row['Peak']}"
    if table == 'peak' and col == 'Category':
        # Why the row is highlighted: "(deepest)(tested)" -> "deepest, tested"
        return ', '.join(re.findall(r'\((\w+)\)', row['Category']))
    if col not in row:
        return EMPTY   # e.g. the first Delta marker's mid/Δ/slope, or a base not set yet
    v = row[col]
    if dec is None:
        return str(v)
    if col == 'slope' and v is None:
        return '∞ (vertical)'
    return number_text(v, dec)


def _row_bg(table, i, row):
    if table == 'peak':
        # The tested peak's color wins over the deepest's when one peak is both.
        if '(tested)' in row['Category']:
            return CRITERIA_BG
        if '(deepest)' in row['Category']:
            return DEEPEST_BG
        return None
    return STRIPE_BG if TABLES[table]['striped'] and i % 2 == 0 else None


def _header_rows(cols, labels):
    """One header row, or two when grouped columns are visible: a group's name
    spans its run of adjacent columns, and the other headers span both rows. A
    group split by reordering gets one header per piece."""
    grouped = any(labels[c][0] for c in cols)
    top, sub = [], []
    i = 0
    while i < len(cols):
        group, header = labels[cols[i]]
        if group is None:
            top.append(html.Th(header, rowSpan=2 if grouped else 1, style=TH_STYLE))
            i += 1
            continue
        j = i
        while j < len(cols) and labels[cols[j]][0] == group:
            j += 1
        top.append(html.Th(group, colSpan=j - i, style=GROUP_TH_STYLE))
        sub += [html.Th(labels[c][1], style=TH_STYLE) for c in cols[i:j]]
        i = j
    return [html.Tr(top)] + ([html.Tr(sub)] if sub else [])


def build_table(table, view, rows, labels=None, absent=()):
    """An html.Table of rows (dicts keyed by column id) with the view's visible
    columns, in its order and decimals. Columns in `absent` don't exist in
    this window (e.g. the Peak table's IL without a reference)."""
    labels = labels or TABLES[table]['labels']
    cols = [c for c in view['order'] if c not in view['hidden'] and c not in absent]
    decs = {c: decimals_for(table, c, view) for c in cols}
    body = []
    for i, r in enumerate(rows):
        bg = _row_bg(table, i, r)
        td = {**TD_STYLE, 'backgroundColor': bg} if bg else TD_STYLE
        body.append(html.Tr([html.Td(_cell_text(table, c, r, decs[c]), style=td) for c in cols]))
    return html.Table([html.Thead(_header_rows(cols, labels)), html.Tbody(body)],
                      style=TABLE_STYLE)


# ---- rows of the marker tables ------------------------------------------------------
def delta_rows(markers):
    """Delta table rows (D1, D2, ...), newest on top. The first Delta has
    nothing to compare with, so its mid/Δ/slope cells stay empty."""
    rows = []
    for i, m in enumerate(markers):
        row = {'Marker': f'D{i + 1}', 'x': m['x'], 'y': m['y']}
        if i > 0:
            p = markers[i - 1]
            dl, dp = m['x'] - p['x'], m['y'] - p['y']
            # dB/nm as plotted; None marks a vertical step (same wavelength).
            row.update(mid_x=(m['x'] + p['x']) / 2, mid_y=(m['y'] + p['y']) / 2,
                       dx=abs(dl), dy=abs(dp), slope=None if dl == 0 else dp / dl)
        rows.append(row)
    return rows[::-1]


def custom_row(channel, m2):
    """The Custom peak table's row from the Bandwidth markers (m2): the peak is
    B1, the base is m2['base'] (B2). Without B2, base and depth stay empty."""
    row = {'Ch': channel, 'Peak': 'custom', 'x': m2['x'], 'y': m2['y']}
    if m2.get('width_pm') is not None:
        row['Width'] = m2['width_pm']
        row['Amplitude'] = m2['amplitude_db']
    base = m2.get('base')
    if base is not None:
        # Base minus the dip: dBm runs negative-down, so this keeps depth positive.
        row.update(base_x=base['x'], base_y=base['y'], Depth=base['y'] - m2['y'])
    return row


# ---- the Pass/Fail table -----------------------------------------------------------
PASS_COLOR, FAIL_COLOR = 'green', 'red'
# Row labels: semibold grey, at the column headers' smaller size.
ROW_HEAD_STYLE = {**TD_STYLE, 'textAlign': 'left', 'fontWeight': 600, 'color': '#555',
                  'fontSize': TH_STYLE['fontSize']}


def _range_cells(rng):
    """A criterion's min and max cells (both ends count; '∞' when there's no
    upper limit), or one EMPTY cell across both when it isn't set."""
    if rng is None:
        return [html.Td(EMPTY, colSpan=2, style=TD_STYLE)]
    return [html.Td('∞' if math.isinf(v) else f'{v:.10g}', style=TD_STYLE) for v in rng]


def _result_cell(result):
    if result is None:   # not checked
        return html.Td(EMPTY, colSpan=2, style=TD_STYLE)
    color = PASS_COLOR if result == 'Pass' else FAIL_COLOR
    return html.Td(result, colSpan=2, style={**TD_STYLE, 'fontWeight': 'bold', 'color': color})


def passfail_table(exam, view):
    """The Pass/Fail result as a table: each criterion's min and max, the
    tested peak's value (with the view's decimals) and each check's result,
    with the overall result ("Pass" in green or "Fail" in red, plus why no peak
    was tested, if so) in a last column that spans those three rows, set off
    by a white gap. Each criterion has two columns: min and max in the
    Criteria row, and one cell across both in the other rows. The top-left
    cell names what was tested: the peak and the base its depth and width are
    measured from ("P2 / Max base", or just "Max base" when no peak was
    tested). Its caption, with the Customize link, is caption('passfail').
    `exam` is analyze_data.exam_peak's dict; call this only when the test is on."""
    checks = exam['checks']
    labels = TABLES['passfail']['labels']   # in exam_peak's check order
    tested = f"{exam['base'].capitalize()} base"
    if exam['peak']:
        tested = f"P{exam['peak']} / {tested}"
    final_edge = {'borderLeft': '8px solid white'}   # a white gap before the column
    # In black rather than the headers' grey: it's information, not a header.
    head = html.Tr([html.Th(tested, style={**TH_STYLE, 'textAlign': 'left', 'color': 'black'})]
                   + [html.Th(labels[c][1], colSpan=2, style=TH_STYLE) for c in labels]
                   + [html.Th('Final result', style={**TH_STYLE, **final_edge})])
    rows = [
        [html.Td('Criteria [min, max]', style=ROW_HEAD_STYLE)]
        + [cell for c in checks for cell in _range_cells(c['range'])],
        [html.Td('Measured', style=ROW_HEAD_STYLE)]
        + [html.Td(EMPTY if chk['value'] is None
                   else number_text(chk['value'], decimals_for('passfail', col, view)),
                   colSpan=2, style=TD_STYLE)
           for chk, col in zip(checks, labels)],
        [html.Td('Result', style=ROW_HEAD_STYLE)] + [_result_cell(c['result']) for c in checks],
    ]
    # The overall result, one cell over all three rows, centered both ways. It
    # sits in the first row, so it sets its own white background rather than
    # taking that row's stripe.
    color = PASS_COLOR if exam['verdict'] == 'Pass' else FAIL_COLOR
    rows[0].append(html.Td([
        html.Div(exam['verdict'], style={'fontSize': '18px', 'fontWeight': 'bold', 'color': color}),
        html.Div(exam['note'], style={'fontSize': '11px', 'color': '#888', 'whiteSpace': 'normal',
                                      'maxWidth': '130px', 'margin': '2px auto 0'})
        if exam['note'] else None,
    ], rowSpan=len(rows), style={**TD_STYLE, **final_edge, 'verticalAlign': 'middle',
                                 'backgroundColor': 'white', 'padding': '3px 16px'}))
    # Every other row shaded, starting with the first, as in the Delta table.
    body = [html.Tr(cells, style={'backgroundColor': STRIPE_BG} if i % 2 == 0 else {})
            for i, cells in enumerate(rows)]
    return html.Table([html.Thead(head), html.Tbody(body)], style=TABLE_STYLE)


# ---- captions and the Customize dialog ------------------------------------------------
LINK_STYLE = {'border': 'none', 'background': 'none', 'padding': 0, 'cursor': 'pointer',
              'color': '#2c6fbb', 'textDecoration': 'underline', 'fontFamily': DATA_CSS_FONT,
              'fontSize': '13px', 'fontWeight': 'normal'}
CAPTION_STYLE = {**TABLE_TITLE_STYLE, 'display': 'flex', 'gap': '14px', 'alignItems': 'baseline'}
HINT_STYLE = {'color': '#b35900'}
SMALL_BTN_STYLE = {'width': '24px', 'height': '22px', 'padding': 0, 'fontSize': '11px',
                   'cursor': 'pointer'}
DEC_WIDTH, MOVE_WIDTH = '78px', '54px'   # the dialog list's Decimals and Move columns
# Centered like the other dialogs, but over a lighter backdrop, so the plot
# and the tables behind it stay easy to see while you change them.
DIALOG_OVERLAY = {'position': 'fixed', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0,
                  'backgroundColor': 'rgba(0,0,0,0.15)', 'zIndex': 1000,
                  'alignItems': 'center', 'justifyContent': 'center'}
DIALOG_HIDDEN = {**DIALOG_OVERLAY, 'display': 'none'}
DIALOG_SHOWN = {**DIALOG_OVERLAY, 'display': 'flex'}


def caption(table, extra=()):
    """A table's caption: its name, grey note if any, and "Customize..." link."""
    note = TABLES[table].get('note')
    title = [TABLES[table]['title']]
    if note:
        title.append(html.Span(f' {note}', style={'fontWeight': 'normal', 'color': '#888'}))
    return html.Div([html.Span(title),
                     html.Button('Customize...', n_clicks=0, style=LINK_STYLE,
                                 id={'type': 'tbl-open', 'table': table}),
                     *extra], style=CAPTION_STYLE)


def peak_label(row):
    """A peak's label in the dialog's Peaks list, e.g. "P1 (deepest)"."""
    return f"P{row['Peak']} {row['Category']}".rstrip()


def customize_modal(peak_rows, hidden_peaks):
    """The one Customize dialog the three tables share. plot.py fills in the
    title and column list for whichever table opened it. The Peaks section
    (peak table only) lists peak_rows; hidden_peaks start unchecked."""
    section = {'fontWeight': 'bold', 'marginBottom': '6px'}
    return html.Div(id='customize-modal', style=DIALOG_HIDDEN, children=html.Div([
        html.Div(id='customize-title', style={'fontWeight': 'bold', 'fontSize': '16px',
                                              'marginBottom': '12px'}),
        html.Div([
            html.Div([
                html.Div('Columns', style=section),
                html.Div(id='customize-columns'),
                html.Button('Reset columns', id='customize-reset', n_clicks=0,
                            style={**LINK_STYLE, 'marginTop': '8px'}),
            ]),
            html.Div(id='customize-peaks', children=[
                html.Div('Peaks', style=section),
                # Spacer so the first peak lines up with the first column row.
                html.Div(style={'height': '17px'}),
                dcc.Checklist(id='peak-show',
                              options=[{'label': peak_label(r), 'value': int(r['Peak'])}
                                       for r in peak_rows],
                              value=[int(r['Peak']) for r in peak_rows
                                     if int(r['Peak']) not in hidden_peaks],
                              labelStyle={'display': 'block', 'height': '24px'}),
                html.Button('Show all peaks', id='show-all-peaks', n_clicks=0,
                            style={**LINK_STYLE, 'marginTop': '8px'}),
            ]),
        ], style={'display': 'flex', 'gap': '40px', 'alignItems': 'flex-start'}),
        html.Div([
            html.Div('Your choices carry over to the next plot while the program runs.',
                     style={'fontSize': '12px', 'color': '#888'}),
            html.Button('Close (Esc)', id='customize-close', n_clicks=0),
        ], style={'display': 'flex', 'justifyContent': 'space-between',
                  'alignItems': 'flex-end', 'gap': '24px', 'marginTop': '16px'}),
    # maxHeight: a long peak list scrolls inside the box rather than pushing
    # its title and Close button off the screen.
    ], style={'backgroundColor': 'white', 'padding': '18px 22px', 'borderRadius': '8px',
              'fontFamily': WINDOW_CSS_FONT, 'fontSize': '14px',
              'maxHeight': '90vh', 'overflowY': 'auto', 'boxSizing': 'border-box',
              'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}))


def column_list(table, view, absent=()):
    """The dialog's column rows: show/hide checkbox, decimals (numeric columns
    only) and move arrows. Up means further left in the table. Columns in
    `absent` aren't listed (see build_table). A 'decimals_only' table gets
    just its labels and the decimals controls."""
    labels = TABLES[table]['labels']
    decimals_only = TABLES[table].get('decimals_only', False)
    order = [c for c in view['order'] if c not in absent]
    hidden = set(view['hidden'])
    items = [html.Div([html.Span('Column', style={'flex': '1'}),
                       html.Span('Decimals', style={'width': DEC_WIDTH, 'textAlign': 'center'})]
                      + ([] if decimals_only else
                         [html.Span('Move', style={'width': MOVE_WIDTH, 'textAlign': 'center'})]),
                      style={'display': 'flex', 'gap': '4px', 'fontSize': '11px', 'color': '#888'})]
    for i, c in enumerate(order):
        locked = c == TABLES[table]['locked']
        group, header = labels[c]
        label = (f'{group}: {header}' if group else header) + ('  (always shown)' if locked else '')
        dec = decimals_for(table, c, view)
        if dec is None:
            dec_ctrl = html.Span(style={'width': DEC_WIDTH})
        else:
            dec_ctrl = html.Span([
                html.Button('−', id={'type': 'tbl-dec-down', 'col': c}, n_clicks=0,
                            disabled=dec <= 0, title='Fewer decimal places',
                            style=SMALL_BTN_STYLE),
                html.Span(str(dec), style={'width': '22px', 'textAlign': 'center',
                                           'fontVariantNumeric': 'tabular-nums'}),
                html.Button('+', id={'type': 'tbl-dec-up', 'col': c}, n_clicks=0,
                            disabled=dec >= MAX_DECIMALS, title='More decimal places',
                            style=SMALL_BTN_STYLE),
            ], style={'width': DEC_WIDTH, 'display': 'flex', 'alignItems': 'center',
                      'justifyContent': 'center', 'gap': '2px'})
        if decimals_only:
            items.append(html.Div([
                html.Span(label, style={'flex': '1', 'whiteSpace': 'nowrap'}),
                dec_ctrl,
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '4px',
                      'height': '24px', 'minWidth': '250px'}))
            continue
        items.append(html.Div([
            dcc.Checklist(id={'type': 'tbl-col-show', 'col': c},
                          options=[{'label': label, 'value': c, 'disabled': locked}],
                          value=[] if c in hidden else [c],
                          style={'flex': '1', 'whiteSpace': 'nowrap'}),
            dec_ctrl,
            html.Span([
                html.Button('▲', id={'type': 'tbl-col-up', 'col': c}, n_clicks=0,
                            disabled=i == 0, title='Move left', style=SMALL_BTN_STYLE),
                html.Button('▼', id={'type': 'tbl-col-down', 'col': c}, n_clicks=0,
                            disabled=i == len(order) - 1, title='Move right',
                            style=SMALL_BTN_STYLE),
            ], style={'width': MOVE_WIDTH, 'display': 'flex', 'gap': '4px'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '4px',
                  'height': '24px', 'minWidth': '330px'}))
    return items
