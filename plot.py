import copy
import threading
import os
import sys
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output, State, Patch, ALL, callback_context
import flask
import webview
from webview import FileDialog

import json
import logging

log = logging.getLogger(__name__)

import shutdown
from constants import GRAPH_WINDOW_ZOOM, FILENAME_BAD_CHARS
from datapath import data_path
from structs import Params, Dataset
from analyze_data import peak_detection, find_bandwidth, exam_peak
from save_csv import save_csv_raw, auto_raw_path,COL_CH, COL_REF, COL_SCAN, RAW_DIR, PEAKS_DIR
from plot_helper import lttb, lttb_multi, pre_process
from filters import FILTER_LABELS, FILTER_OFF, FILTER_PARAMS, apply_filter, FilterError
from readout import READOUT_COLUMNS, DASH_REFRESH_MS, format_row, format_actual, format_wl
import plot_tables as pt
from plot_tables import DATA_CSS_FONT, WINDOW_CSS_FONT
import peak_dialog as pdlg
import peak_file as pf

# Remembered across display_plot() calls (i.e. across loop iterations) for the
# "Save peak info" dialog: the file saved to last (a full path), where the
# dialog starts, and a new file's columns ([{'item': key} or {'text': name}]
# after the fixed ones) and decimals (item key -> decimals). Label (SN) and
# Temperature aren't.
_last_peak_file = ''
_peak_columns   = []
_peak_decimals  = {}
# The files "Save peak info" opened or saved to lately, kept across runs:
# newest first, one path per line (see peak_file.remember). The File menu
# lists them under "Recent files".
RECENT_PEAK_FILES = data_path('recent_peak_files.txt', mkdir=False)
# Also remembered across display_plot() calls: each table's columns and
# decimals from its Customize dialog, and the peak numbers hidden in the peak
# table (by number, so P3 stays hidden in a later sweep that finds a P3).
_table_views  = {t: pt.default_view(t) for t in pt.TABLES}
_hidden_peaks = []
# Also remembered: the Show / hide items left unticked, by key (e.g. 'lbase'),
# kept even through a sweep that doesn't have the item.
_hidden_items = set()

# Page template: Dash's default plus one style block. Buttons and form fields
# don't inherit the page font by default, so they're told to. The pf- rules
# are for the Save peak info table (peak_dialog._label): an option's label
# holds a one-line text for the open list (.pf-menu) and a two-line one for
# the field (.pf-field). Dropdowns with class pf-dd show the two-line one,
# left-aligned, in a narrower field. The list opens outside the dropdown's
# element, so it keeps the one-line text. Dash's field grid puts the text in
# an auto-width first column; 1fr gives the text the free space instead.
# The File menu (class pf-file-dd) always shows its placeholder, "File menu",
# so the placeholder gets the normal text color.
INDEX_STRING = '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body { font-family: __FONT__; }
            button, input, select, textarea { font-family: inherit; }
            .pf-field { display: none; }
            .pf-dd .pf-menu { display: none; }
            .pf-dd .pf-field { display: block; }
            .pf-dd .pf-l1, .pf-dd .pf-l2 {
                display: block; overflow: hidden; text-overflow: ellipsis; }
            .pf-dd .dash-dropdown-value {
                white-space: nowrap; line-height: 1.15;
                justify-self: stretch; text-align: left; }
            .pf-dd .dash-dropdown-trigger { padding: 0 6px; gap: 4px; }
            .pf-dd .dash-dropdown-grid-container { grid-template-columns: 1fr auto; }
            .pf-dd .dash-dropdown-grid-container:has(> :nth-child(3)) {
                grid-template-columns: 1fr auto auto; }
            .pf-dd .dash-dropdown-grid-container:has(> :nth-child(4)) {
                grid-template-columns: 1fr auto auto auto; }
            .pf-file-dd .dash-dropdown-placeholder { color: inherit; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>'''.replace('__FONT__', WINDOW_CSS_FONT)


def _apply_zoom(window):
    """Set GRAPH_WINDOW_ZOOM on a graph window's WebView2 (Windows only).

    Runs on each page load (window.events.loaded), on pywebview's event thread,
    so the change is handed to the window's UI thread with Invoke, the way
    pywebview's own WinForms code does it. A zoom the app sets carries over to
    later page loads, so setting it again is harmless. Never raises: a failure
    only leaves the window at its normal size.
    """
    if GRAPH_WINDOW_ZOOM == 1 or not sys.platform.startswith('win'):
        return
    try:
        from System import Func, Type   # pythonnet, already loaded by pywebview
        form = window.native            # pywebview's WinForms form
        control = form.webview          # its WebView2 control (EdgeChromium)

        def _set():
            control.ZoomFactor = GRAPH_WINDOW_ZOOM

        form.Invoke(Func[Type](_set))
    except Exception:
        log.warning("Could not set the graph window zoom", exc_info=True)


def _status(text, error=False):
    """One message for the status strip under the nav bar; red for errors."""
    return html.Span(text, style={'color': '#c0392b' if error else '#555'})


def _label_error(text):
    """Why `text` can't be the label, or None. The label goes into file names,
    so it follows the config window's rules for its prefix."""
    if any(c in FILENAME_BAD_CHARS for c in text):
        return f"Can't use {' '.join(FILENAME_BAD_CHARS)}."
    if text != text.rstrip(' .'):
        return "Can't end with a space or a dot."
    return None


def display_plot(raw_w: Dataset, params: Params, *, readout=None, title="Absorption Spectrum",
                 autosaved_to=None, autosave_error=None):
    """
    Parameters
    ----------
    readout : readout.PowerReadout, optional
        The session's live power readout, shown in the "Power Readout" modal.
        None (e.g. plotting a saved CSV) leaves the button disabled.

    Notes
    -----
    This call is BLOCKING — control does not return to the caller until
    the user closes the window. It must be called from the main thread
    (a pywebview requirement).
    """
    wl, watt_s, dbm_s = pre_process(raw_w, params)
    d_x = round(wl[1] - wl[0], 7)
    channels = tuple(params.channel)

    if params.reference:
        mainplots = dbm_s.diff
    else:
        mainplots = dbm_s.data
    
    dbm = mainplots[0]
    overlays = dbm_s.scans if len(dbm_s.scans) > 1 else []
    peak_df = pd.DataFrame()

    MAX_DISPLAY  = 10000  # max points rendered at once for the spectrum

    # ------------------------------------------------------------------
    # Initial figure (built once, captures the data)
    # ------------------------------------------------------------------
    # Every line is solid; each line (main, reference or scan) gets its own
    # color, assigned in draw order from this palette.
    LINE_COLORS = [
        '#378ADD', '#D85A30', '#2A9D8F', '#9B59B6', '#E8A020', '#50C878',
        '#E63946', '#457B9D', '#F4A261', '#264653', '#8E44AD', '#16A085',
    ]
    _color_state = {'i': 0}
    def _next_color():
        c = LINE_COLORS[_color_state['i'] % len(LINE_COLORS)]
        _color_state['i'] += 1
        return c

    wl_init, dbm_init = lttb(wl, dbm, MAX_DISPLAY)
    initial_fig = go.Figure()
    # data[0] — channel-1 spectrum (the analyzed channel). SVG scatter (not
    # scattergl): WebGL partial Patch updates on this line trace occasionally
    # fail to repaint, leaving a blank/stale curve after a zoom. At
    # <=MAX_DISPLAY points SVG is fine.
    initial_fig.add_scatter(
        x=wl_init, y=dbm_init, mode='lines', name=f'{COL_CH}{channels[0]}_{dbm_s.unit}',
        line=dict(color=_next_color(), width=2),
        hovertemplate='%{x:.12~f}<br>%{y:.5~f}<extra></extra>',
    )
    # Trace-index bookkeeping for the resampler: (trace index, wl-aligned y).
    # data[0] is channel 1; the remaining channels, references and scans are
    # appended AFTER all the fixed-index marker & peak traces below, so those
    # indices (data[1..10]) stay put for the callbacks.
    main_traces    = [(0, dbm)]
    ref_traces     = []
    overlay_traces = []
    _border = dict(width=1, color='#333')
    # data[1..4] use SVG scatter to match data[0] and the peak traces below —
    # keep the whole figure on one renderer (mixing scattergl draws WebGL
    # traces on a separate layer above the SVG line).
    # data[1] — mode-1 accumulated markers
    initial_fig.add_scatter(
        x=[], y=[], mode='markers+text', name='Delta',
        marker=dict(symbol='diamond', size=7, color='#D85A30', line=_border),
        text=[], textposition='top center',
    )
    # data[2] — mode-2 markers B1 (peak) and B2 (base); clicks alternate between them
    initial_fig.add_scatter(
        x=[], y=[], mode='markers+text', name='Bandwidth',
        marker=dict(symbol='x', size=11, color='#E8A020', line=_border),
        text=[], textposition='bottom right',
    )
    # data[3] — mode-2 left offset marker
    initial_fig.add_scatter(
        x=[], y=[], mode='markers', name='Bandwidth:Left',
        marker=dict(symbol='triangle-right', size=10, color='#50C878', line=_border),
        text=[], textposition='top center',
    )
    # data[4] — mode-2 right offset marker
    initial_fig.add_scatter(
        x=[], y=[], mode='markers+text', name='Bandwidth:Right',
        marker=dict(symbol='triangle-left', size=10, color='#50C878', line=_border),
        text=[], textposition='middle right',
    )
    
    pk = peak_detection(wl, dbm)
    exam = exam_peak(pk, params)
    exam_out, exam_idx = exam['verdict'], exam['peak']
    if pk is not None:
        # data[5..10] — peak annotation traces (Peaks, L/R bases, FWHM max/avg/min)
        initial_fig.add_scatter(x=pk.x_nm, y=dbm[pk.x_idx], mode='markers+text', name='Peak', marker=dict(size=5, color='#E63946', symbol='circle', line=_border), text=[f"P{i}" for i, _ in enumerate(pk.x_idx, start=1)], textposition='bottom center')
        
        initial_fig.add_scatter(x=wl[pk.l_idx], y=dbm[pk.l_idx], mode='markers+text', name='Peak:Left base', marker=dict(size=8, color='#2A9D8F', symbol='triangle-up', line=_border), text=[f"P{i}:L({e[0]:.3f}, {e[1]:.3f})" for i, e in enumerate(zip(wl[pk.l_idx], dbm[pk.l_idx]), start=1)], textposition='top right')
        
        initial_fig.add_scatter(x=wl[pk.r_idx], y=dbm[pk.r_idx], mode='markers+text', name='Peak:Right base', marker=dict(size=8, color='#2A9D8F', symbol='triangle-down', line=_border), text=[f"P{i}:R({e[0]:.3f}, {e[1]:.3f})" for i, e in enumerate(zip(wl[pk.r_idx], dbm[pk.r_idx]), start=1)], textposition='top left')
        
        initial_fig.add_scatter(x=np.concatenate([pk.max.l_nm, pk.max.r_nm]), y=np.concatenate([pk.max.w_y, pk.max.w_y]), mode='markers', name="Width (max base)", visible=True, marker=dict(size=8, color='#F4A261', symbol='square', line=_border))

        initial_fig.add_scatter(x=np.concatenate([pk.avg.l_nm, pk.avg.r_nm]), y=np.concatenate([pk.avg.w_y, pk.avg.w_y]), mode='markers', name="Width (avg base)", visible=True, marker=dict(size=8, color='#457B9D', symbol='diamond', line=_border))

        initial_fig.add_scatter(x=np.concatenate([pk.min.l_nm, pk.min.r_nm]), y=np.concatenate([pk.min.w_y, pk.min.w_y]), mode='markers', name="Width (min base)", visible=True, marker=dict(size=8, color='#8E44AD', symbol='hexagon', line=_border))

        peak_dict = {
            "x"           : np.round(pk.x_nm, decimals=7),
            "y"           : np.round(dbm[pk.x_idx], decimals=5),
            "Depth_max"   : np.round(pk.max.depth, decimals=5),
            "FWHM_max"    : np.round(pk.max.w_pm, decimals=3),
            "Depth_avg"   : np.round(pk.avg.depth, decimals=5),
            "FWHM_avg"    : np.round(pk.avg.w_pm, decimals=3),
            "Depth_min"   : np.round(pk.min.depth, decimals=5),
            "FWHM_min"    : np.round(pk.min.w_pm, decimals=3),
                     }
        
        peak_df = pd.DataFrame(peak_dict)
        peak_df.insert(0, "Peak", [i+1 for i in range(len(peak_df))])
        peak_df.insert(0, "Ch", [channels[0] for _ in range(len(peak_df))])
        # peak_df["Category"] = ""
        peak_df.insert(2, "Category", "")
        peak_df.loc[peak_df["Depth_max"].idxmax(), "Category"] += "(deepest)"

    # ------------------------------------------------------------------
    # Remaining channels (channel 1 is data[0] above). Appended AFTER the
    # fixed-index marker/peak traces so data[1..10] stay put. Solid line,
    # one color per channel.
    # ------------------------------------------------------------------    
    for k, (ch, d_arr) in enumerate(zip(channels, mainplots)):
        if k == 0:
            continue
        wl_d, d_d = lttb(wl, d_arr, MAX_DISPLAY)
        initial_fig.add_scatter(
            x=wl_d, y=d_d, mode='lines', name=f'{COL_CH}{ch}_{dbm_s.unit
            }',
            line=dict(color=_next_color(), width=2),
            hovertemplate='%{x:.12~f}<br>%{y:.5~f}<extra></extra>',
        )
        main_traces.append((len(initial_fig.data) - 1, d_arr))

    # ------------------------------------------------------------------
    # Reference sweep. Insertion loss is computed
    # on channel 1 only; a dashed reference line is drawn for every channel.
    # ------------------------------------------------------------------
    il_idx = None  # trace index of the IL marker (None when no reference)
    if params.reference:
        # Issue #90
        gmax_idx = int(np.nanargmax(dbm))
        gmax_x, gmax_y = float(wl[gmax_idx]), float(dbm[gmax_idx])
        initial_fig.add_scatter(
            x=[gmax_x], y=[gmax_y], mode='markers+text', name='Insertion loss',
            marker=dict(symbol='star', size=9, color='#C0392B', line=_border),
            # Negated (not abs) so a negative IL still reads as negative — that
            # means the device came out above the reference, usually a bad ref sweep.
            text=[f"IL: {-gmax_y:.5f} dB"], textposition='bottom center',
            textfont=dict(size=14, color='#C0392B'),
            hovertemplate='%{x:.12~f}<br>%{y:.5f}<extra>IL</extra>',
        )
        il_idx = len(initial_fig.data) - 1
        for k, (ch, r_arr, d_arr) in enumerate(zip(channels, dbm_s.ref, dbm_s.data)):
            wl_d, r_d = lttb(wl, r_arr, MAX_DISPLAY)
            wl_d, d_d = lttb(wl, d_arr, MAX_DISPLAY)
            initial_fig.add_scatter(
                x=wl_d, y=r_d, mode='lines', name=f'{COL_REF}{ch}_dBm',
                line=dict(color=_next_color(), width=2),
                hovertemplate='%{x:.12~f}<br>%{y:.5f}<extra></extra>', visible='legendonly',
            )
            ref_traces.append((len(initial_fig.data) - 1, r_arr))
            initial_fig.add_scatter(
                x=wl_d, y=d_d, mode='lines', name=f'Raw_{COL_CH}{ch}_dBm',
                line=dict(color=_next_color(), width=2),
                hovertemplate='%{x:.12~f}<br>%{y:.5f}<extra></extra>', visible='legendonly',
            )
            ref_traces.append((len(initial_fig.data) - 1, d_arr))

    # ------------------------------------------------------------------
    # Overlay scans (display-only, legend-only by default). One dotted line
    # per (scan, channel). Appended last so the fixed indices above stay put.
    # ------------------------------------------------------------------
    for s, scan in enumerate(overlays, start=1):
        for k, (ch, c_arr) in enumerate(zip(channels, scan)):
            wl_d, o_d = lttb(wl, c_arr, MAX_DISPLAY)
            initial_fig.add_scatter(
                x=wl_d, y=o_d, mode='lines', name=f'{COL_SCAN}{s}_{COL_CH}{ch}_dBm',
                line=dict(color=_next_color(), width=2),
                hovertemplate='%{x:.12~f}<br>%{y:.5f}<extra></extra>',
                visible='legendonly',
            )
            overlay_traces.append((len(initial_fig.data) - 1, c_arr))

    # ------------------------------------------------------------------
    # Smoothed (filtered) channel-1 trace. Added LAST so every fixed trace
    # index above stays put. Starts empty/hidden; the "Apply filter" modal
    # fills it in. `_smooth['y']` holds the full-resolution filtered array
    # so the zoom/max-points resampler can downsample it like the others.
    # ------------------------------------------------------------------
    initial_fig.add_scatter(
        x=[], y=[], mode='lines', name='Smoothed', visible=False,
        line=dict(color='#111111', width=2),
        hovertemplate='%{x:.12~f}<br>%{y:.5f}<extra>Smoothed</extra>',
    )
    smooth_idx = len(initial_fig.data) - 1
    _smooth = {'y': None}  # full-res filtered channel-1 array (None until applied)

    # Pale line connecting the mode-1 (Delta) markers. A separate trace from the
    # diamonds (data[1]) and appended last (like the smoothed trace) so the fixed
    # marker/peak indices above stay put. It is sampled with many interpolated
    # points per segment (see redraw_markers) rather than one vertex per marker,
    # so Plotly's closest-point click snaps ONTO the line — letting the user drop
    # a Delta marker anywhere along the connector, not only at an existing marker.
    initial_fig.add_scatter(
        x=[], y=[], mode='lines', name='Delta:line', showlegend=False,
        line=dict(color='rgba(216,90,48,0.35)', width=1.5),
        hovertemplate='%{x:.12~f}<br>%{y:.5f}',
    )
    delta_line_idx = len(initial_fig.data) - 1

    initial_fig.update_layout(
        font=dict(family=DATA_CSS_FONT),   # same font as the tables
        xaxis_title=dict(text='λ (nm)', font=dict(size=12), standoff=5),
        yaxis_title=dict(text='Power (dB | dBm)', font=dict(size=12), standoff=5),
        hovermode='closest',
        showlegend=True,
        legend=dict(x=1.0, xanchor='left'),
        # No width or height: the dcc.Graph below is responsive, so the plot
        # fills its box, which is as wide as the sidebar leaves and 550px tall.
        margin=dict(l=50, t=30, b=5),
        uirevision='constant',
    )

    initial_fig.update_xaxes(tickformat='.7~f', hoverformat='.12~f')
    initial_fig.update_xaxes(showspikes=True, spikecolor="gray", spikemode="across", spikethickness=1)
    initial_fig.update_yaxes(showspikes=True, spikemode="across", spikecolor="gray", spikethickness=1)

    # ------------------------------------------------------------------
    # Dash app
    # ------------------------------------------------------------------
    # Holder so callbacks (running on the server thread) can reach the
    # pywebview window, which is only created later in this function.
    _window_holder = {}
    # Set by the Repeat button; read after the window closes to tell the caller
    # to auto-Run the next sweep. NOT part of Params (which stays run-only).
    _repeat = {'flag': False}

    # Dash callbacks run on the Flask server thread; an unhandled exception
    # there is caught by Dash and would otherwise surface only as an HTTP 500 in
    # the browser/console — it never propagates back through webview.start() to
    # main.py's try/except, so it would miss the log file. Route it through our
    # logger, the same fix as config_window's report_callback_exception override.
    def _log_dash_error(err):
        log.error("Dash callback error", exc_info=err)

    app = dash.Dash(__name__, on_error=_log_dash_error)
    app.index_string = INDEX_STRING

    # ------------------------------------------------------------------
    # Right sidebar styles. The container sets the 14px default font, which
    # cascades to labels/checklists/radio items. Form controls (<input>)
    # don't inherit font-size, so INPUT_STYLE restates it. Section titles use
    # HEADING_STYLE; field labels and notes the smaller NOTE_STYLE (11px).
    # ------------------------------------------------------------------
    HEADING_STYLE = {'fontWeight': 'bold', 'display': 'block', 'marginBottom': '6px'}
    NOTE_STYLE = {'fontSize': '11px', 'color': '#888', 'display': 'block'}
    # NOTE: text stays left-aligned — WebKit (pywebview) ignores text-align on
    # type='number' inputs, and centering would require dropping the -/+ steppers.
    INPUT_STYLE = {'width': '140px', 'boxSizing': 'border-box',
                   'fontSize': '14px', 'padding': '2px 5px'}
    INPUT_STYLE_FULL = {**INPUT_STYLE, 'width': '100%'}
    # The Bandwidth marker's settings, under Click mode. Hidden while Click
    # mode is Delta (show_bandwidth_settings), which is also where it starts.
    BW_SETTINGS_STYLE = {'marginTop': '10px', 'width': '140px'}
    BW_SETTINGS_HIDDEN = {**BW_SETTINGS_STYLE, 'display': 'none'}

    # Three sections, top to bottom: Label (SN), Plot sampling and Click mode,
    # each under a bold title. Show / hide lives in its own popup (menu bar, H).
    right_sidebar = html.Div([
        # The sweep's label, which the user can change here (update_label).
        # Below it, what happened to the last change. That line is always two
        # lines tall, even when empty, so the sections below never move. A
        # longer message (a long label) is cut with "…" at the end of line 2.
        html.Div([
            html.Label("Label (SN)", style=HEADING_STYLE),
            dcc.Input(id='label-input', type='text', value=params.label or '',
                      placeholder='No label', debounce=False, style=INPUT_STYLE),
            html.Div(id='label-status',
                     style={**NOTE_STYLE, 'marginTop': '4px', 'lineHeight': '1.2', 'height': '2.4em',
                            'display': '-webkit-box', 'WebkitBoxOrient': 'vertical',
                            'WebkitLineClamp': '2', 'overflow': 'hidden'}),
        ]),
        html.Div([
            html.Label("Plot sampling", style=HEADING_STYLE),
            html.Label("Max points per curve (x1000)",
                       style={**NOTE_STYLE, 'marginBottom': '4px'}),
            dcc.Input(
                id='max-display-input',
                type='number', min=0, max=1000, value=MAX_DISPLAY // 1000,
                debounce=True,
                style=INPUT_STYLE,
            ),
            html.Div("0 = no downsampling (may be slow)",
                     style={**NOTE_STYLE, 'marginTop': '2px'}),
        ]),
        html.Div([
            html.Label("Click mode", style=HEADING_STYLE),
            dcc.RadioItems(
                id='click-mode',
                options=[{'label': 'Delta', 'value': 1}, {'label': 'Bandwidth', 'value': 2}],
                value=1,
                inline=True,
                labelStyle={'display': 'inline-block', 'marginRight': '16px'},
                style={'display': 'inline-block'},
            ),
            html.Button('Clear all', id='clear-btn', n_clicks=0,
                        style={'width': '150px', 'fontSize': '13px',
                               'padding': '5px 12px', 'marginTop': '5px'}),
            # The width at the Bandwidth markers' peak, B1. Bandwidth mode picks
            # how its level is set: Automatic measures at a % of the depth
            # from B1 up to B2 (the base), searching as far out as B2 is;
            # Manual takes a fixed amplitude and search range.
            # Shown only while Click mode is Bandwidth.
            html.Div([
                html.Div(id='mode2-marker-info',
                         style={'display': 'none'}),
                html.Label("Bandwidth mode",
                           style={**NOTE_STYLE, 'marginTop': '12px', 'marginBottom': '4px'}),
                dcc.RadioItems(
                    id='bw-mode',
                    options=[{'label': 'Automatic', 'value': 'auto'}, {'label': 'Manual', 'value': 'manual'}],
                    value='auto',
                    inline=True,
                    labelStyle={'display': 'inline-block', 'marginRight': '16px'},
                ),
                html.Div([
                    html.Label("Bandwidth amplitude (%)",
                               style={**NOTE_STYLE, 'marginTop': '12px', 'marginBottom': '4px'}),
                    dcc.Input(
                        id='bw-pct-input',
                        type='number', step=1,
                        min=1, max=99, value=50,
                        debounce=True,
                        style=INPUT_STYLE_FULL,
                    ),
                ], id='bw-auto-fields'),
                html.Div([
                    html.Label("Bandwidth amplitude (dB)",
                               style={**NOTE_STYLE, 'marginTop': '12px', 'marginBottom': '4px'}),
                    dcc.Input(
                        id='mode2-offset-input',
                        type='number', step=0.001,
                        min=0, max=50, value=0.1,
                        debounce=True,
                        style=INPUT_STYLE_FULL,
                    ),
                ], id='bw-manual-fields', style={'display': 'none'}),
                html.Div(id='mode2-offset-info',
                         style={'display': 'none'}),
                # Why there's no width, or why it's cut short (orange).
                html.Div(id='bw-hint', style={**NOTE_STYLE, **pt.HINT_STYLE, 'marginTop': '6px'}),
            ], id='bw-settings', style=BW_SETTINGS_HIDDEN),
        ]),
    # A fixed width, so the graph beside it doesn't resize when the Bandwidth
    # settings appear or hide. It fits the widest item, the 150px Clear all button.
    ], style={'padding': '20px 10px', 'display': 'flex', 'flexDirection': 'column',
              'gap': '20px', 'fontSize': '14px', 'fontFamily': WINDOW_CSS_FONT,
              'width': '150px', 'flexShrink': 0})

    # ------------------------------------------------------------------
    # Horizontal menu bar (top of the window). The action buttons live
    # here instead of the sidebar; their ids are unchanged so all the
    # existing callbacks (and the Enter keybind) keep working.
    # ------------------------------------------------------------------
    NAV_BTN_STYLE = {
        'fontSize': '12px', 'padding': '2px 12px', 'border': 'none',
        'background': 'transparent', 'color': '#fff', 'cursor': 'pointer',
        'fontFamily': WINDOW_CSS_FONT,
    }

    # What the "Show / hide" popup lists, as (value, label) per group. An item
    # is listed only when this window has it: peaks found, peak test criteria
    # set (the table exam_div shows), a reference (the insertion loss marker).
    # The Peak test result table shows even with no peak found, so then it's
    # the Peak group's only item.
    SH_ITEMS = {
        'peak': ([('peak', 'Peak'), ('lbase', 'Peak:Left base'), ('rbase', 'Peak:Right base')]
                 if pk is not None else [])
                # The two tables in their on-screen order: the test result first.
                + ([('passfail', 'Peak test result')] if exam_out in ('Pass', 'Fail') else [])
                # Keeps "table" here, unlike the table's own caption ("Peak").
                + ([('table', 'Peak table')] if pk is not None else []),
        'width': [('max', 'Width (max base)'), ('avg', 'Width (avg base)'),
                  ('min', 'Width (min base)')] if pk is not None else [],
        'other': [('il', 'Insertion loss')] if il_idx is not None else [],
    }
    SH_KEYS = {group: [value for value, _ in items] for group, items in SH_ITEMS.items()}
    has_show_hide = any(SH_KEYS.values())
    # The plot trace behind each item: data[5] the peaks, [6]/[7] their
    # left/right bases, [8..10] the max/avg/min-base widths (fixed indices).
    SH_TRACES = {'peak': 5, 'lbase': 6, 'rbase': 7, 'max': 8, 'avg': 9, 'min': 10} if pk is not None else {}
    if il_idx is not None:
        SH_TRACES['il'] = il_idx
    # Start from the remembered choices. apply_show_hide runs only on a
    # change, so what _hidden_items hides is hidden here from the start (the
    # Pass/Fail table and the Peak table get the same treatment in the layout).
    for key, i in SH_TRACES.items():
        if key in _hidden_items:
            initial_fig.data[i].visible = 'legendonly'

    top_navbar = html.Nav([
        html.Button('Save raw data...(S)', id='save-raw-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Button(['Save peak info...(P)'], id='save-peak-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Button('Apply filter...(F)', id='apply-filter-btn', n_clicks=0, style=NAV_BTN_STYLE),
        # Disabled when there's nothing to show or hide (no peaks, criteria or reference).
        html.Button('Show / hide...(H)', id='show-hide-btn', n_clicks=0,
                    disabled=not has_show_hide,
                    style=NAV_BTN_STYLE if has_show_hide
                    else {**NAV_BTN_STYLE, 'opacity': 0.4, 'cursor': 'default'}),
        html.Button('Plot in Watt...', id='plot-watt-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Div(id='plot-watt-dummy', style={'display': 'none'}),
        html.Button('Sweep info...(I)', id='sweep-info-btn', n_clicks=0, style=NAV_BTN_STYLE),
        # Power Readout: live meter values in a modal (readout.PowerReadout).
        # Disabled when there is no readout, e.g. plotting a saved CSV.
        html.Button('Power readout...(R)', id='readout-btn', n_clicks=0,
                    disabled=readout is None,
                    style=NAV_BTN_STYLE if readout is not None
                    else {**NAV_BTN_STYLE, 'opacity': 0.4, 'cursor': 'default'}),

        # Close & Repeat: close this plot window and auto-Run the next sweep with the same parameters. Also bound to the Enter key (see the clientside callback below).
        html.Button('Close & Repeat (Enter)', id='repeat-btn', n_clicks=0,
                    style={**NAV_BTN_STYLE, 'fontWeight': 'bold', 'marginLeft': 'auto'}),
        # Dummy sink for the keybind clientside callback; the keydown
        # listener it installs is what actually clicks the button.
        html.Div(id='repeat-keybind-dummy', style={'display': 'none'}),
                # Close Window: just close this plot window (same as the window's close
        # button). marginLeft: auto pushes it and the Repeat button to the right edge.
        html.Button('Close window (W)', id='close-btn', n_clicks=0,
                    style={**NAV_BTN_STYLE}),
        html.Div(id='close-dummy', style={'display': 'none'}),
        # No visible button: the X shortcut clicks this to reset the plot's
        # zoom, like the modebar's Autoscale (see the clientside callback right
        # after KEY_SHORTCUTS).
        html.Button(id='reset-zoom-btn', n_clicks=0, style={'display': 'none'}),
    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '4px',
              'padding': '2px 16px', 'backgroundColor': '#2c3e50'})

    # Status strip under the nav bar: one line, the newest message replaces the
    # last. Fixed height so the graph doesn't shift as messages come and go.
    # Opens with the auto-save result, if main.py auto-saved this sweep.
    if autosave_error:
        initial_status = _status("Auto-save failed; use Save raw data.", error=True)
    elif autosaved_to:
        initial_status = _status(f"Auto-saved: {os.path.basename(autosaved_to)}")
    else:
        initial_status = ""
    nav_status = html.Div(initial_status, id='nav-status', style={
        'height': '20px', 'lineHeight': '20px', 'padding': '0 30px',
        'fontSize': '12px', 'fontFamily': WINDOW_CSS_FONT,
        'backgroundColor': '#ecf0f1', 'overflow': 'hidden', 'whiteSpace': 'nowrap'})

    # ------------------------------------------------------------------
    # "Save peak info" dialog (peak_dialog.py): pick a peak file, then the
    # columns and the peaks in a table that previews the rows to save.
    # ------------------------------------------------------------------
    if pk is not None:
        # The tested peak first, then the deepest (max Depth_max), then the rest.
        max_peak = int(peak_df.loc[peak_df['Depth_max'].idxmax(), 'Peak'])
        if exam_idx is not None:
            ordered_peaks = [exam_idx] + ([max_peak] if max_peak != exam_idx else [] ) + [int(p) for p in peak_df['Peak'] if int(p) not in [exam_idx, max_peak]]
            peak_df.loc[peak_df["Peak"] == exam_idx, "Category"] += "(tested)"
        else:
            ordered_peaks = [max_peak] + [int(p) for p in peak_df['Peak'] if int(p) != max_peak]
        peak_options = []
        for p in ordered_peaks:
            label = f'P{p}'
            if exam_idx is not None and p == exam_idx:
                label += " (tested)"
            if p == max_peak:
                label += " (deepest)"
            peak_options.append({'label': label, 'value': f'peak:{p}'})
    else:
        ordered_peaks, peak_options = [], []

    # What every row of this sweep shares: its date, insertion loss (the IL
    # marker's value) and settings.
    _sweep_values = pf.sweep_values(params, -gmax_y if params.reference else None)

    def _has_custom(m2):
        """Whether both Bandwidth markers are set, so "custom" is a peak to save."""
        return bool(m2 and m2.get('base'))

    def _peak_choices(m2):
        """The peak dropdowns' options: the detected peaks, then "custom"."""
        return peak_options + ([{'label': 'custom', 'value': 'custom'}] if _has_custom(m2) else [])

    def _default_peak(m2):
        """A new dialog's one row: the tested peak, else the deepest, else custom."""
        if ordered_peaks:
            return f'peak:{ordered_peaks[0]}'
        return 'custom' if _has_custom(m2) else None

    def _peak_name(peak):
        """A peak's name in messages: "P2" or "custom"."""
        return 'custom' if peak == 'custom' else f"P{peak.split(':')[1]}"

    def _row_values(peak, m2):
        """Item key -> value for a row with this peak; a value it doesn't have
        is missing. A detected peak has no custom values, and the custom peak
        (the Bandwidth markers: B1 the peak, B2 the base) has no max, avg or
        min ones. Full precision: the dialog rounds them for display and Save."""
        values = dict(_sweep_values)
        if peak == 'custom':
            if _has_custom(m2):
                base_y = m2['base']['y']
                values.update(wl=m2['x'], depth_custom=base_y - m2['y'],
                              width_custom=m2.get('width_pm'))
                if params.reference:
                    # Negated like IL, so a base above the reference reads as a gain.
                    values['il_custom'] = -base_y
        elif peak and pk is not None:
            i = int(peak.split(':')[1]) - 1
            values['wl'] = float(pk.x_nm[i])
            for base in ('max', 'avg', 'min'):
                widths = getattr(pk, base)
                values[f'depth_{base}'] = float(widths.depth[i])
                values[f'width_{base}'] = float(widths.w_pm[i])
        return values

    def _peak_file_options():
        """The File menu, with the recent files that still exist."""
        return pdlg.file_options([p for p in pf.recent_files(RECENT_PEAK_FILES)
                                  if os.path.isfile(p)])

    def _remember_peak_file(path):
        """Put path at the top of the recent files."""
        try:
            pf.remember(RECENT_PEAK_FILES, path)
        except OSError as e:
            # Nothing else depends on the list; the File menu just misses the file.
            log.warning("Could not update %s: %s", RECENT_PEAK_FILES, e)

    def _first_peak_file():
        """The file the dialog starts with: the file saved to last in this
        run, or a new file ('') when there's none or it's gone."""
        return _last_peak_file if _last_peak_file and os.path.isfile(_last_peak_file) else ''

    def _peak_folder(current):
        """Where the system's Open and Save dialogs start: the folder of the
        dialog's file, else of the newest recent file, else Peaks."""
        for path in [current] + pf.recent_files(RECENT_PEAK_FILES):
            if path and os.path.isdir(os.path.dirname(path)):
                return os.path.dirname(path)
        return os.path.abspath(PEAKS_DIR)

    MODAL_OVERLAY = {
        'position': 'fixed', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0,
        'backgroundColor': 'rgba(0,0,0,0.45)', 'zIndex': 1000,
        'alignItems': 'center', 'justifyContent': 'center',
    }
    MODAL_HIDDEN = {**MODAL_OVERLAY, 'display': 'none'}
    MODAL_SHOWN  = {**MODAL_OVERLAY, 'display': 'flex'}

    peak_modal = pdlg.modal(MODAL_HIDDEN)

    # ------------------------------------------------------------------
    # "Apply filter" modal — pick a smoothing filter and its parameters,
    # then draw the filtered channel-1 signal as the "Smoothed" trace, or
    # pick "Off" (last in the list) to remove it.
    # Each filter's parameter controls live in their own block; the dropdown
    # toggles which block is visible, so new filters can be added by dropping
    # in another block + a branch in `apply_filter`.
    # ------------------------------------------------------------------
    LABEL_STYLE = {'fontWeight': 'bold', 'display': 'block', 'marginBottom': '4px'}
    PARAM_LABEL_STYLE = {'fontSize': '13px', 'display': 'block', 'marginBottom': '4px'}
    filter_modal = html.Div(
        id='filter-modal',
        style=MODAL_HIDDEN,
        children=html.Div([
            html.Label('Select filter', style=LABEL_STYLE),
            dcc.Dropdown(
                id='filter-select',
                options=[{'label': name, 'value': val}
                         for val, name in FILTER_LABELS.items()]
                        + [{'label': 'Off', 'value': FILTER_OFF}],
                value=next(iter(FILTER_LABELS)),
                clearable=False, searchable=False,
                # Tall enough for every option so the menu never inner-scrolls
                # (default maxHeight is 200px); optionHeight default is 35px.
                optionHeight=35,
                maxHeight=300,
                style={'marginBottom': '12px'},
            ),
            # Hidden for "Off", which has no parameters.
            html.Div(id='filter-params', children=[
                html.Label('Parameters', style=LABEL_STYLE),
                # Two generic parameter inputs; their labels/visibility are set per
                # filter from FILTER_PARAMS by the `update_filter_params` callback.
                # parameter1 maps to the first param, parameter2 to the second.
                html.Label(id='param1-label', style=PARAM_LABEL_STYLE),
                dcc.Input(id='param1-input', type='number', step=1, value=21, debounce=False,
                          style={'width': '100%', 'boxSizing': 'border-box', 'marginBottom': '8px'}),
                html.Div(id='param2-row', children=[
                    html.Label(id='param2-label', style=PARAM_LABEL_STYLE),
                    dcc.Input(id='param2-input', type='number', step=1, value=3, debounce=False,
                              style={'width': '100%', 'boxSizing': 'border-box', 'marginBottom': '8px'}),
                ]),
            ]),
            html.Div(id='filter-modal-error',
                     style={'color': '#C0392B', 'fontSize': '12px',
                            'minHeight': '16px', 'marginBottom': '8px'}),
            html.Div([
                html.Button('Cancel (Esc)', id='filter-cancel', n_clicks=0),
                html.Button('Apply', id='filter-apply-confirm', n_clicks=0,
                            style={'marginLeft': '8px'}),
            ], style={'textAlign': 'right'}),
        ], style={'backgroundColor': 'white', 'padding': '20px 24px',
                  'borderRadius': '8px', 'width': '320px', 'minHeight': '350px',
                  'fontFamily': WINDOW_CSS_FONT,
                  'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}),
    )

    # Pass/Fail result, shown just above the Peak table: a table of each check
    # with the overall result in its last column, under a caption with a
    # Customize link (the Measured row's decimals). render_passfail_table fills
    # it in. Nothing when the test is off (every criterion 0).
    exam_div = html.Div([pt.caption('passfail'), html.Div(id='passfail-table')],
                        style={'marginTop': '5px'}) if exam_out else None

    # ------------------------------------------------------------------
    # "Sweep Info" modal — read-only table of the sweep parameters, from
    # Params.describe(), so a field added to Params shows up on its own.
    # Rebuilt each time it opens: the label can change while the window is open.
    # ------------------------------------------------------------------
    _info_cell  = {'padding': '1px 12px 1px 0', 'whiteSpace': 'nowrap', 'verticalAlign': 'top'}
    _info_label = {**_info_cell, 'color': '#555'}
    _info_group = {'textAlign': 'left', 'paddingTop': '10px', 'paddingBottom': '2px'}

    def _sweep_info_rows():
        rows, last_group = [], None
        for group, label, text in params.describe():
            if group != last_group:
                style = {**_info_group, 'paddingTop': 0} if not rows else _info_group
                rows.append(html.Tr(html.Th(group, colSpan=2, style=style)))
                last_group = group
            rows.append(html.Tr([html.Td(label, style=_info_label),
                                 html.Td(text,  style=_info_cell)]))
        return rows

    sweep_info_modal = html.Div(
        id='sweep-info-modal',
        style=MODAL_HIDDEN,
        children=html.Div([
            html.H4('Sweep info', style={'marginTop': 0}),
            html.Table(_sweep_info_rows(), id='sweep-info-table',
                       style={'borderCollapse': 'collapse', 'fontSize': '13px'}),
            html.Div(html.Button('Close (Esc)', id='sweep-info-close', n_clicks=0),
                     style={'textAlign': 'right', 'marginTop': '12px'}),
        ], style={'backgroundColor': 'white', 'padding': '20px 24px',
                  'borderRadius': '8px', 'width': '360px',
                  'maxHeight': '90vh', 'overflowY': 'auto',
                  'fontFamily': WINDOW_CSS_FONT,
                  'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}),
    )

    # ------------------------------------------------------------------
    # "Show / hide" popup (menu bar, H): what the plot and the tables show.
    # Centered over a light backdrop like the Customize dialog, so the plot
    # stays in view while boxes are ticked. "All" and each group's "(all)" box
    # tick or clear their items (sync_show_hide). The boxes start from the
    # choices remembered in _hidden_items. Every checklist is always in the
    # layout so the callbacks can name it; a group this window doesn't have
    # is just empty and hidden.
    # ------------------------------------------------------------------
    sh_shown = {g: [k for k in keys if k not in _hidden_items] for g, keys in SH_KEYS.items()}
    sh_full = {g: len(sh_shown[g]) == len(SH_KEYS[g]) for g in SH_KEYS}

    def _sh_box(id_, label, ticked, shown=True):
        """One "(all)" checkbox over a group."""
        return dcc.Checklist(id=id_, options=[{'label': label, 'value': 'all'}],
                             value=['all'] if ticked else [], labelStyle={'display': 'block'},
                             style={'marginTop': '6px'} if shown else {'display': 'none'})

    def _sh_items(group, indent=True):
        return dcc.Checklist(id=f'sh-{group}',
                             options=[{'label': label, 'value': value}
                                      for value, label in SH_ITEMS[group]],
                             value=sh_shown[group], labelStyle={'display': 'block'},
                             style={'marginLeft': '20px'} if indent else {'marginTop': '6px'})

    show_hide_modal = html.Div(id='show-hide-modal', style=pt.DIALOG_HIDDEN, children=html.Div([
        html.Div('Show / hide', style={'fontWeight': 'bold', 'fontSize': '16px', 'marginBottom': '6px'}),
        _sh_box('sh-all', 'All', all(sh_full.values())),
        _sh_box('sh-peak-all', 'Peak (all)', sh_full['peak'], bool(SH_ITEMS['peak'])),
        _sh_items('peak'),
        _sh_box('sh-width-all', 'Width (all)', sh_full['width'], bool(SH_ITEMS['width'])),
        _sh_items('width'),
        _sh_items('other', indent=False),
        html.Div([
            html.Div('Your choices carry over to the next plot while the program runs.',
                     style={'fontSize': '12px', 'color': '#888', 'maxWidth': '170px'}),
            html.Button('Close (Esc)', id='show-hide-close', n_clicks=0),
        ], style={'display': 'flex', 'justifyContent': 'space-between',
                  'alignItems': 'flex-end', 'gap': '24px', 'marginTop': '16px'}),
    ], style={'backgroundColor': 'white', 'padding': '18px 22px', 'borderRadius': '8px',
              'fontFamily': WINDOW_CSS_FONT, 'fontSize': '14px',
              'maxHeight': '90vh', 'overflowY': 'auto', 'boxSizing': 'border-box',
              'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}))

    # ------------------------------------------------------------------
    # "Power Readout" modal — the live meter readout (readout.PowerReadout),
    # polled by a dcc.Interval only while the modal is open. Opening starts
    # the readout, closing stops it. Without a readout (plotting a saved CSV)
    # the button is disabled and none of this runs.
    # ------------------------------------------------------------------
    _ro_has_laser = readout is not None and readout.has_laser
    # The emission state the Laser on box last showed. refresh_readout pushes
    # the box only when readout.emission moves away from this (front-panel
    # button). Pushing it every tick could undo a click still in flight.
    _ro_shown = {'emission': readout is not None and readout.emission}
    _ro_cell  = {'padding': '2px 10px', 'textAlign': 'right', 'whiteSpace': 'nowrap',
                 'fontSize': '16px', 'fontVariantNumeric': 'tabular-nums'}
    _ro_head  = {**_ro_cell, 'fontSize': '13px', 'color': '#555', 'borderBottom': '1px solid #ccc'}
    # The three power columns are held wide enough for "-888.888 dBm" (99.8px
    # in 16px Tahoma, plus slack), so they don't shift as values gain or lose
    # digits. In an auto-layout table a cell's width is only a minimum:
    # anything wider still widens its column. Ch. (1-4) and Range (10 to
    # -70 dBm, at most 60px) never outgrow their headers, so they need none.
    _ro_head_fixed = {**_ro_head, 'width': '108px'}
    _ro_label = {'fontSize': '13px', 'display': 'inline-block', 'width': '120px'}
    _ro_row   = {'display': 'flex', 'alignItems': 'center', 'marginBottom': '4px'}
    _ro_input = {'width': '90px', 'fontSize': '14px', 'padding': '2px 5px', 'boxSizing': 'border-box'}
    # The read-back beside each field: what the meter and laser report now.
    _ro_actual = {'fontSize': '13px', 'color': '#555', 'marginLeft': '10px', 'whiteSpace': 'nowrap'}

    def _readout_actual():
        """Text for the two read-back spans (wavelength row, power row)."""
        if readout is None:
            return '', ''
        pm_s, lwl_s, ldbm_s = format_actual(readout.actual, readout.has_laser)
        return f"pm {pm_s}, laser {lwl_s}", f"laser {ldbm_s}"

    def _readout_rows(rows):
        """One <tr> per channel from read()'s output; None -> placeholders."""
        trs = []
        for i in range(4):
            if rows is None:
                cells = ('—',) * 4
            else:
                rng, w = rows[i]
                cells = format_row(rng, w, readout.max_w[i])
            trs.append(html.Tr([html.Td(str(i + 1), style=_ro_cell)]
                               + [html.Td(c, style=_ro_cell) for c in cells]))
        return trs

    readout_modal = html.Div(
        id='readout-modal',
        style=MODAL_HIDDEN,
        children=html.Div([
            html.H4('Power readout', style={'marginTop': 0}),
            # Same order as the config window's section: Laser on, the two
            # fields, then Apply / Reset Max.
            dcc.Checklist(
                id='readout-laser',
                options=[{'label': ' Laser on', 'value': 'on', 'disabled': not _ro_has_laser}],
                value=['on'] if (readout is not None and readout.emission) else [],
                style={'fontSize': '13px', 'marginBottom': '6px'}),
            html.Div([
                html.Label('λ (nm)', style=_ro_label),
                dcc.Input(id='readout-wl', type='text', style=_ro_input,
                          value=format_wl(readout.wl_nm) if readout is not None else ''),
                html.Span(_readout_actual()[0], id='readout-wl-actual', style=_ro_actual),
            ], style=_ro_row),
            html.Div([
                html.Label('TLS Power (dBm)', style=_ro_label),
                dcc.Input(id='readout-dbm', type='text', style=_ro_input, disabled=not _ro_has_laser,
                          value=f"{readout.dbm:g}" if readout is not None else ''),
                html.Span(_readout_actual()[1], id='readout-dbm-actual', style=_ro_actual),
            ], style=_ro_row),
            html.Div([
                html.Button('Apply', id='readout-apply', n_clicks=0),
                html.Button('Reset Max', id='readout-reset', n_clicks=0, style={'marginLeft': '8px'}),
            ], style={'marginTop': '6px'}),
            html.Div(id='readout-msg', style={'minHeight': '18px', 'fontSize': '13px', 'marginTop': '4px'}),
            html.Table([
                html.Thead(html.Tr([html.Th(c, style=_ro_head if i < 2 else _ro_head_fixed)
                                    for i, c in enumerate(READOUT_COLUMNS)])),
                html.Tbody(id='readout-rows', children=_readout_rows(None)),
            ], style={'borderCollapse': 'collapse', 'marginTop': '6px'}),
            # Close & Repeat here does the same as the menu bar's button (and
            # Enter): close the window and auto-Run the next sweep.
            html.Div([
                html.Button('Close (Esc)', id='readout-close', n_clicks=0),
                html.Button('Close & Repeat (Enter)', id='readout-repeat-btn', n_clicks=0,
                            style={'marginLeft': '8px'}),
            ], style={'textAlign': 'right', 'marginTop': '12px'}),
            dcc.Interval(id='readout-tick', interval=DASH_REFRESH_MS, n_intervals=0, disabled=True),
        # The table is the widest thing in the box, and its fixed columns
        # (_ro_head_fixed) keep it one width, so the box doesn't resize as
        # readings change. Only a value wider than "-888.888 dBm" widens it.
        ], style={'backgroundColor': 'white', 'padding': '20px 24px',
                  'borderRadius': '8px', 'width': 'fit-content',
                  'fontFamily': WINDOW_CSS_FONT,
                  'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}),
    )

    # The peak table's rows, also listed in its Customize dialog. Built after
    # the Save peak section above has tagged the tested peak in Category.
    # With a reference, each row also carries the sweep's insertion loss (the
    # same value the IL marker on the plot shows).
    peak_rows = peak_df.to_dict('records') if pk is not None else []
    if params.reference:
        for r in peak_rows:
            r['IL'] = -gmax_y
    # Columns a table doesn't have in this window. They keep their place (and
    # shown/hidden choice) in the remembered column order for later windows.
    TABLE_ABSENT = {'custom': (), 'delta': (), 'passfail': (),
                    'peak': () if params.reference else ('IL',)}

    # The Bandwidth markers' clicked x positions, [B1 (peak), B2 (base)], and
    # which of them the next click places or moves (0 = B1, 1 = B2).
    BW_EMPTY = {'points': [], 'next': 0}

    app.layout = html.Div([
        top_navbar,
        nav_status,
        html.Div([
            html.Div([
                # A responsive graph sizes the plot to this box and follows the
                # window. The box needs its own height: left to Dash, it's
                # "100%" of a parent with no set height, which collapses to 0
                # and lets the plot cover everything below it.
                dcc.Graph(id='spectrum', figure=initial_fig, 
                          config={'scrollZoom': True, 'displayModeBar': True,  'displaylogo': False}, responsive=True, style={'height': '550px'}),
                # Top to bottom, one table per row: the Custom peak table (once
                # a Bandwidth marker exists), the Delta table (once a Delta
                # marker exists), the Pass/Fail table, and the Peak table. The
                # render_* callbacks below fill in the marker and Peak tables.
                # The Pass/Fail table sits outside the Peak table's container,
                # so it still shows when no peak was found or the table is
                # hidden. Its wrapper is what Show / hide's "Peak test result"
                # hides.
                html.Div(id='custom-block', style={'display': 'none', 'marginTop': '5px'}, children=[
                    pt.caption('custom'), html.Div(id='custom-table')]),
                html.Div(id='delta-block', style={'display': 'none', 'marginTop': '5px'}, children=[
                    pt.caption('delta'), html.Div(id='delta-table')]),
                html.Div(exam_div, id='exam-block',
                         style={'display': 'none'} if 'passfail' in _hidden_items else {}),
                html.Div(id='peak-table-container', children=[
                    pt.caption('peak', [html.Span(id='peak-hint', style=pt.HINT_STYLE)]),
                    html.Div(id='peak-table'),
                ], style={'display': 'none'} if 'table' in _hidden_items else {})
                if pk is not None else None,
            # Takes all the width the sidebar leaves. Below 900px the page
            # scrolls sideways instead of squeezing the plot.
            ], style={'flex': '1', 'minWidth': '900px'}),
            right_sidebar,
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),
        dcc.Store(id='markers-store', data=[]),
        dcc.Store(id='bw-anchors-store', data=BW_EMPTY),
        dcc.Store(id='mode2-info-store', data=None),
        dcc.Store(id='idle-store', data=None),
        # Each table's columns/decimals (starts from the remembered ones) and
        # which table the Customize dialog is editing.
        dcc.Store(id='table-views', data=copy.deepcopy(_table_views)),
        dcc.Store(id='customize-table', data=None),
        dcc.Interval(id='idle-check', interval=shutdown.IDLE_POLL_MS, n_intervals=0),
        html.Div(id='idle-shutdown-dummy', style={'display': 'none'}),
        peak_modal,
        filter_modal,
        sweep_info_modal,
        readout_modal,
        show_hide_modal,
        pt.customize_modal(peak_rows, set(_hidden_peaks)),
    ])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output('nav-status', 'children', allow_duplicate=True),
        Input('save-raw-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def save_raw(n_clicks):
        window = _window_holder.get('window')
        if window is None:
            return dash.no_update

        stem = f"{params.label}_{params.time}" if params.label else params.time
        result = window.create_file_dialog(
            FileDialog.SAVE,
            directory=os.path.abspath(RAW_DIR),
            save_filename=f"{stem}.csv",
            file_types=('CSV files (*.csv)', 'All files (*.*)'),
        )
        if not result:
            return dash.no_update   # cancelled: keep whatever the strip shows
        # SAVE_DIALOG returns a str on some versions, a tuple/list on others.
        file_path = result[0] if isinstance(result, (list, tuple)) else result
        # data/ref are the full-resolution per-channel lists; save_csv_raw pairs
        # them with params.channel to label columns Ch.<n> / Ch.<n>(Ref).
        save_csv_raw(raw_w, params=params, file_path=file_path)
        return _status(f"Raw data saved: {os.path.basename(file_path)}")

    @app.callback(
        Output('plot-watt-dummy', 'children'),
        Input('plot-watt-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def plot_watt(n_clicks):
        # Option A: build a standalone Plotly figure in linear (Watt) units and
        # open it in a SECOND pywebview window as a self-contained HTML file.
        # It's a zoomable viewer only (no Dash callbacks / analysis behind it).
        # Full resolution — no lttb — so deep zoom stays faithful (the static
        # HTML can't re-downsample on zoom the way the main window does).
        _cs = {'i': 0}
        def _color():
            c = LINE_COLORS[_cs['i'] % len(LINE_COLORS)]
            _cs['i'] += 1
            return c

        def _line(y_arr, name, **kw):
            fig.add_scatter(
                x=wl, y=y_arr, mode='lines', name=name,
                line=dict(color=_color(), width=2),
                hovertemplate='%{x:.12~f}<br>%{y:.5e}<extra></extra>', **kw,
            )

        fig = go.Figure()
        if params.reference:
            # Main = data - ref (linear); raw data and reference kept legend-only.
            for ch, d in zip(channels, watt_s.diff):
                _line(d, f'{COL_CH}{ch}_{watt_s.unit}')
            for ch, r in zip(channels, watt_s.ref):
                _line(r, f'{COL_REF}{ch}_{watt_s.unit}', visible='legendonly')
            for ch, d in zip(channels, watt_s.data):
                _line(d, f'Raw_{COL_CH}{ch}_{watt_s.unit}', visible='legendonly')
        else:
            for ch, d in zip(channels, watt_s.data):
                _line(d, f'{COL_CH}{ch}_{watt_s.unit}')

        # Dynamic-range scans (display-only, legend-only); only with >1 scan.
        if len(watt_s.scans) > 1:
            for s, scan in enumerate(watt_s.scans, start=1):
                for ch, c_arr in zip(channels, scan):
                    _line(c_arr, f'{COL_SCAN}{s}_{COL_CH}{ch}_{watt_s.unit}', visible='legendonly')

        fig.update_layout(
            font=dict(family=DATA_CSS_FONT),
            xaxis_title=dict(text='λ (nm)', font=dict(size=12), standoff=5),
            yaxis_title=dict(text=f'Power ({watt_s.unit})', font=dict(size=12)),
            hovermode='closest', showlegend=True,
            legend=dict(x=1.0, xanchor='left'),
            # No width: to_html makes the plot responsive, so it fills the window.
            height=750, margin=dict(l=55, t=30, b=40),
        )
        fig.update_xaxes(tickformat='.8~f', hoverformat='.12~f', showspikes=True,
                         spikecolor='gray', spikemode='across', spikethickness=1)
        fig.update_yaxes(showspikes=True, spikemode='across',
                         spikecolor='gray', spikethickness=1)

        # Self-contained HTML (plotly.js inlined) so it opens offline / in the
        # packaged build, served by this window's own Dash server (see
        # watt_plot_page). This callback runs inside a Dash request, so
        # host_url is that server's address.
        _watt_page['html'] = fig.to_html(include_plotlyjs=True, config={'scrollZoom': True})
        watt_window = webview.create_window(
            f'{title} — Watt', flask.request.host_url + 'watt-plot',
            width=1250, height=700, maximized=True,
        )
        watt_window.events.loaded += _apply_zoom
        return dash.no_update

    # The Watt plot page. It used to be a temp file opened by path, but
    # pywebview (6.2) never loads a local file in a window created after
    # start(): its check for a running file server reads a property off the
    # server class, which is always truthy, so no server starts for the file.
    _watt_page = {'html': ''}

    @app.server.route('/watt-plot')
    def watt_plot_page():
        return _watt_page['html']

    @app.callback(
        Output('repeat-keybind-dummy', 'children'),
        Input('repeat-btn', 'n_clicks'),
        Input('readout-repeat-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_repeat(_menu_clicks, _readout_clicks):
        # Remember the request, then close the window. webview.start() returns,
        # the function below shuts the server down, and display_plot() returns
        # _repeat['flag'] to the caller (main_sweep), which auto-Runs next loop.
        # From the Power Readout modal, the readout.stop() after webview.start()
        # stops the readout, as the modal's Close would.
        _repeat['flag'] = True
        window = _window_holder.get('window')
        if window is not None:
            window.destroy()
        return dash.no_update

    @app.callback(
        Output('close-dummy', 'children'),
        Input('close-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_close(n_clicks):
        # Just close the window, exactly like the window's own close button:
        # no repeat flag, so display_plot() returns False and main_sweep waits
        # for the user instead of auto-Running.
        window = _window_holder.get('window')
        if window is not None:
            window.destroy()
        return dash.no_update

    # Each modal overlay -> the button that dismisses it (Esc clicks it). The
    # keybinds below look up which modal, if any, is open.
    MODAL_CLOSE_BTNS = {
        'peak-modal': 'peak-cancel',
        'filter-modal': 'filter-cancel',
        'sweep-info-modal': 'sweep-info-close',
        'readout-modal': 'readout-close',
        'show-hide-modal': 'show-hide-close',
        'customize-modal': 'customize-close',
    }
    MODAL_IDS = list(MODAL_CLOSE_BTNS)
    # Modals where Enter still means Close & Repeat, through the modal's own
    # button. In any other open modal, Enter is left to the modal.
    MODAL_REPEAT_BTNS = {'readout-modal': 'readout-repeat-btn'}

    # Enter triggers Repeat, except while typing in a text/number field (e.g. a
    # label or temperature), in a dcc.Dropdown (Dash 4 renders its trigger as a
    # <button> with class dash-dropdown and its open menu as
    # dash-dropdown-content; it also preventDefaults Enter), or while a modal
    # not in MODAL_REPEAT_BTNS is open (Enter belongs to that modal's own
    # buttons and fields). A focused button or checkbox doesn't block Repeat:
    # WebView2 keeps a clicked button focused, and preventDefault stops that
    # button from also firing. Installed once via a document-level keydown
    # listener.
    app.clientside_callback(
        """
        function(n) {
            if (!window._repeatKeyBound) {
                window._repeatKeyBound = true;
                var modals = __MODALS__;
                var repeatBtns = __REPEAT_BTNS__;
                document.addEventListener('keydown', function(e) {
                    if (e.key !== 'Enter' || e.defaultPrevented) return;
                    var target = 'repeat-btn';
                    for (var i = 0; i < modals.length; i++) {
                        var m = document.getElementById(modals[i]);
                        if (m && m.style.display !== 'none') {
                            target = repeatBtns[modals[i]];
                            if (!target) return;
                            break;
                        }
                    }
                    var t = e.target;
                    var tag = t && t.tagName ? t.tagName.toUpperCase() : '';
                    if (tag === 'TEXTAREA' || tag === 'SELECT') return;
                    if (tag === 'INPUT' && !/^(checkbox|radio)$/i.test(t.type)) return;
                    if (t && t.closest && t.closest('.dash-dropdown, .dash-dropdown-content')) return;
                    e.preventDefault();
                    var btn = document.getElementById(target);
                    if (btn) btn.click();
                });
            }
            return '';
        }
        """.replace('__MODALS__', json.dumps(MODAL_IDS))
           .replace('__REPEAT_BTNS__', json.dumps(MODAL_REPEAT_BTNS)),
        Output('repeat-btn', 'title'),
        Input('repeat-btn', 'n_clicks'),
    )

    # Esc dismisses the open modal by clicking its button in MODAL_CLOSE_BTNS.
    # In a text or number field, the first Esc only leaves the field and keeps
    # what was typed (a debounced field sends its value then); the next Esc
    # closes the modal. An open dcc.Dropdown menu also gets Esc first: Dash 4's
    # menu closes on it and preventDefaults the event, so the modal stays open
    # until the next Esc.
    app.clientside_callback(
        """
        function(n) {
            if (!window._escKeyBound) {
                window._escKeyBound = true;
                var closers = __CLOSERS__;
                document.addEventListener('keydown', function(e) {
                    if (e.key !== 'Escape' || e.defaultPrevented) return;
                    for (var id in closers) {
                        var m = document.getElementById(id);
                        if (m && m.style.display !== 'none') {
                            var t = e.target;
                            var tag = t && t.tagName ? t.tagName.toUpperCase() : '';
                            if (tag === 'TEXTAREA' ||
                                    (tag === 'INPUT' && !/^(checkbox|radio)$/i.test(t.type))) {
                                e.preventDefault();
                                t.blur();
                                return;
                            }
                            var btn = document.getElementById(closers[id]);
                            if (btn) {
                                e.preventDefault();
                                btn.click();
                            }
                            return;
                        }
                    }
                });
            }
            return '';
        }
        """.replace('__CLOSERS__', json.dumps(MODAL_CLOSE_BTNS)),
        Output('sweep-info-close', 'title'),
        Input('sweep-info-close', 'n_clicks'),
    )

    # Letter shortcuts for the menu buttons: the key shown in a button's "(X)"
    # suffix clicks that button. Same focus guard as Enter (skipped while typing
    # in a text/number field or in a dropdown), ignored when a modifier is held
    # so e.g. Cmd/Ctrl+P (print) still works, and ignored while any modal is
    # open so a second one can't stack on top. One document-level keydown
    # listener serves every entry; add a key here and a "(X)" to the button
    # label to bind a new one.
    KEY_SHORTCUTS = {
        's': 'save-raw-btn',
        'p': 'save-peak-btn',
        'f': 'apply-filter-btn',
        'h': 'show-hide-btn',
        'i': 'sweep-info-btn',
        'r': 'readout-btn',
        'w': 'close-btn',
        'x': 'reset-zoom-btn',   # hidden; the callback after this listener resets the zoom
    }
    app.clientside_callback(
        """
        function(n) {
            if (!window._menuKeysBound) {
                window._menuKeysBound = true;
                var keys = __KEYS__;
                var modals = __MODALS__;
                document.addEventListener('keydown', function(e) {
                    var id = keys[(e.key || '').toLowerCase()];
                    if (!id) return;
                    if (e.metaKey || e.ctrlKey || e.altKey) return;
                    var t = e.target;
                    var tag = t && t.tagName ? t.tagName.toUpperCase() : '';
                    if (tag === 'TEXTAREA' || tag === 'SELECT') return;
                    if (tag === 'INPUT' && !/^(checkbox|radio)$/i.test(t.type)) return;
                    if (t && t.closest && t.closest('.dash-dropdown, .dash-dropdown-content')) return;
                    for (var i = 0; i < modals.length; i++) {
                        var m = document.getElementById(modals[i]);
                        if (m && m.style.display !== 'none') return;
                    }
                    var btn = document.getElementById(id);
                    if (btn) btn.click();
                });
            }
            return '';
        }
        """.replace('__KEYS__', json.dumps(KEY_SHORTCUTS)).replace('__MODALS__', json.dumps(MODAL_IDS)),
        Output('save-peak-btn', 'title'),
        Input('save-peak-btn', 'n_clicks'),
    )

    # X (via the hidden reset-zoom-btn): autoscale both axes, the same as the
    # modebar's Autoscale or Reset axes for this plot. It must run in the
    # browser: Plotly then reports the change in relayoutData, and
    # resample_on_zoom redraws the curves for the full sweep. A reset sent from
    # the server wouldn't be reported, leaving the zoomed-in sampling in place.
    app.clientside_callback(
        """
        function(n) {
            var gd = document.querySelector('#spectrum .js-plotly-plot');
            if (gd) Plotly.relayout(gd, {'xaxis.autorange': true, 'yaxis.autorange': true});
            return window.dash_clientside.no_update;
        }
        """,
        Output('reset-zoom-btn', 'title'),
        Input('reset-zoom-btn', 'n_clicks'),
        prevent_initial_call=True,
    )

    # Idle auto-close: track activity browser-side and, after IDLE_MS with none,
    # ask the server to close the window (once, via the _idleFired latch). Unlike
    # the config window (whose close already exits), a normal plot close loops
    # back to config — so the paired server callback sets the shared shutdown
    # flag to break main.py's loop. Capture-phase listeners so typing counts too.
    #
    # prevent_initial_call keeps this off the initial render: on load the store
    # must not be written, or the downstream callback fires immediately (its own
    # prevent_initial_call does NOT protect it from an upstream write during load,
    # e.g. a clientside no_update that serializes to null). Runs from the first
    # Interval tick on, where the init block sets _lastActivity fresh.
    app.clientside_callback(
        """
        function(n) {
            var now = Date.now();
            if (!window._idleActivityBound) {
                window._idleActivityBound = true;
                window._lastActivity = now;
                ['mousemove', 'mousedown', 'keydown', 'click', 'wheel', 'touchstart'].forEach(function(ev) {
                    document.addEventListener(ev, function() {
                        window._lastActivity = Date.now();
                    }, true);
                });
            }
            var idle = now - window._lastActivity;
            if (!window._idleFired && idle > __IDLE_MS__) {
                window._idleFired = true;
                return idle;
            }
            return window.dash_clientside.no_update;
        }
        """.replace('__IDLE_MS__', str(shutdown.IDLE_MS)),
        Output('idle-store', 'data'),
        Input('idle-check', 'n_intervals'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('idle-shutdown-dummy', 'children'),
        Input('idle-store', 'data'),
        prevent_initial_call=True,
    )
    def on_idle_timeout(idle_ms):
        # Act only on a real measured idle duration. A spurious/empty update (a
        # clientside no_update that serializes as null, or an initial-render
        # write) arrives as falsy and must be ignored — otherwise the window
        # closes the moment it opens.
        if not idle_ms:
            return dash.no_update
        log.info("Idle timeout (%.0f s idle) — closing plot window.", idle_ms / 1000)
        shutdown.request()
        window = _window_holder.get('window')
        if window is not None:
            window.destroy()
        return ''

    # ------------------------------------------------------------------
    # Save peak info: open the dialog, pick its file, keep its state
    # (pf-state) in step with the table's controls, draw the table, and Save
    # or Cancel.
    # ------------------------------------------------------------------
    def _fresh_peak_state(path, m2):
        """The dialog's state for the chosen file (its path, or '' for a new
        file), with one row for the default peak."""
        if path:
            state = pdlg.file_state(path, _peak_decimals)
        else:
            state = pdlg.new_file_state(_peak_columns, _peak_decimals)
        peak = _default_peak(m2)
        if peak and not state['bad']:
            pdlg.add_row(state, peak)
        return state

    # Opening the dialog starts its state over, with the file saved to last.
    # The state is built here, in one response with the File menu: Dash drops
    # a callback's unfinished run when the callback fires again, so a state
    # left to update_peak_state could be lost to the table's controls firing it.
    @app.callback(
        Output('peak-modal', 'style'),
        Output('peak-file-select', 'options', allow_duplicate=True),
        Output('pf-state', 'data', allow_duplicate=True),
        Output('peak-label', 'value'),
        Output('peak-temperature', 'value'),
        Output('peak-modal-error', 'children', allow_duplicate=True),
        Input('save-peak-btn', 'n_clicks'),
        State('mode2-info-store', 'data'),
        prevent_initial_call=True,
    )
    def open_peak_modal(n_clicks, m2):
        # Label (SN) starts with the sweep's label, and Temperature empty.
        return (MODAL_SHOWN, _peak_file_options(), _fresh_peak_state(_first_peak_file(), m2),
                params.label or '', None, '')

    # A pick in the File menu. Its value goes back to None, so it shows "File
    # menu" again. "Open file…" asks the system's Open dialog for the file. A
    # file other than the dialog's own starts the state over, built here (see
    # open_peak_modal), and goes to the top of the recent files if it opens
    # without an error. The dialog's own file, or Cancel in the Open dialog,
    # changes nothing.
    @app.callback(
        Output('peak-file-select', 'value'),
        Output('peak-file-select', 'options'),
        Output('pf-state', 'data', allow_duplicate=True),
        Input('peak-file-select', 'value'),
        State('pf-state', 'data'),
        State('mode2-info-store', 'data'),
        prevent_initial_call=True,
    )
    def pick_peak_file(value, state, m2):
        if value is None or not state:
            return dash.no_update, dash.no_update, dash.no_update
        path = '' if value == pdlg.NEW_FILE else value
        if value == pdlg.OPEN_FILE:
            window = _window_holder.get('window')
            result = None
            if window is not None:
                result = window.create_file_dialog(
                    FileDialog.OPEN,
                    directory=_peak_folder(state['path']),
                    file_types=('Excel files (*.xlsx)',),
                )
            if not result:
                return None, dash.no_update, dash.no_update
            path = os.path.abspath(result[0] if isinstance(result, (list, tuple)) else result)
        if path == state['path'] or (path and state['path'] and pf.same_file(path, state['path'])):
            return None, dash.no_update, dash.no_update
        new = _fresh_peak_state(path, m2)
        if not path or new['bad']:
            return None, dash.no_update, new
        _remember_peak_file(path)
        return None, _peak_file_options(), new

    # Any other change is a control in the table: peak_dialog.update works
    # out the change from every control's current value.
    @app.callback(
        Output('pf-state', 'data'),
        Input({'type': 'pf-col', 'col': ALL}, 'value'),
        Input({'type': 'pf-name', 'col': ALL}, 'value'),
        Input({'type': 'pf-dec', 'col': ALL, 'step': ALL}, 'n_clicks'),
        Input({'type': 'pf-row', 'row': ALL}, 'value'),
        Input({'type': 'pf-text', 'row': ALL, 'col': ALL}, 'value'),
        Input({'type': 'pf-add', 'what': ALL}, 'value'),
        State('pf-state', 'data'),
        prevent_initial_call=True,
    )
    def update_peak_state(*rest):
        state = rest[-1]
        if not state:
            return dash.no_update
        current = {}
        for group in callback_context.inputs_list:
            for item in group:
                current.setdefault(item['id']['type'], []).append((item['id'], item.get('value')))
        changes = [(json.loads(t['prop_id'].rsplit('.', 1)[0]), t.get('value'))
                   for t in callback_context.triggered if t['prop_id'].startswith('{')]
        new = pdlg.update(state, changes, current)
        if new is None:
            return dash.no_update
        if new['mode'] == 'new':
            # A new file's columns and decimals carry over to the next one,
            # in this and later plot windows.
            _peak_columns[:] = pdlg.session_columns(new)
            _peak_decimals.clear()
            _peak_decimals.update(new['dec'])
        return new

    @app.callback(
        Output('pf-table', 'children'),
        Output('pf-file-path', 'children'),
        Output('pf-save-hint', 'children'),
        Output('pf-file-msg', 'children'),
        Output('peak-modal-error', 'children', allow_duplicate=True),
        Input('pf-state', 'data'),
        Input('peak-label', 'value'),
        Input('peak-temperature', 'value'),
        State('mode2-info-store', 'data'),
        prevent_initial_call=True,
    )
    def render_peak_dialog(state, label, temperature, m2):
        # Any change also clears the last Save's error message.
        if not state:
            return [], '', '', '', ''
        table = pdlg.table(state, _peak_choices(m2), lambda peak: _row_values(peak, m2),
                           label, temperature)
        return table, pdlg.file_line(state), pdlg.save_hint(state), pdlg.file_message(state), ''

    @app.callback(
        Output('peak-modal', 'style', allow_duplicate=True),
        Output('nav-status', 'children', allow_duplicate=True),
        Output('peak-modal-error', 'children'),
        Input('peak-cancel', 'n_clicks'),
        Input('peak-save-confirm', 'n_clicks'),
        State('pf-state', 'data'),
        State('peak-label', 'value'),
        State('peak-temperature', 'value'),
        State('mode2-info-store', 'data'),
        prevent_initial_call=True,
    )
    def close_or_save_peak(cancel, confirm, state, label, temperature, m2):
        if callback_context.triggered_id == 'peak-cancel':
            return MODAL_HIDDEN, dash.no_update, ''
        if not state:
            return dash.no_update, dash.no_update, ''
        label = (label or '').strip()
        trouble = pdlg.problem(state, label, lambda peak: _row_values(peak, m2), _peak_name)
        if trouble:
            return dash.no_update, dash.no_update, trouble
        rows = [{**_row_values(r['peak'], m2), 'label': label, 'temperature': temperature,
                 'texts': pdlg.row_texts(state, r)} for r in state['rows']]

        window = _window_holder.get('window')
        if window is None:
            return dash.no_update, dash.no_update, "Window not ready."
        try:
            if state['mode'] == 'new':
                result = window.create_file_dialog(
                    FileDialog.SAVE,
                    directory=_peak_folder(state['path']),
                    save_filename='.xlsx',
                    file_types=('Excel files (*.xlsx)', 'All files (*.*)'),
                )
                if not result:
                    # User cancelled the file dialog — keep the modal open.
                    return dash.no_update, dash.no_update, ''
                path = result[0] if isinstance(result, (list, tuple)) else result
                if not path.lower().endswith('.xlsx'):
                    path += '.xlsx'
                added, replaced = pf.save(path, rows, columns=pdlg.file_columns(state),
                                          decimals=state['dec'])
            else:
                path = state['path']
                added, replaced = pf.save(path, rows, decimals=state['dec'])
        except pf.PeakFileError as e:
            return dash.no_update, dash.no_update, str(e)

        global _last_peak_file
        _last_peak_file = os.path.abspath(path)
        _remember_peak_file(path)
        log.info(f"Saved peak info: {path} (rows added {added}, replaced {replaced})")
        done = []
        if added:
            done.append(f"{len(added)} new row" + ('s' if len(added) > 1 else ''))
        if replaced:
            done.append(f"replaced row{'s' if len(replaced) > 1 else ''} "
                        + ', '.join(str(r) for r in replaced))
        return MODAL_HIDDEN, _status(f"Peak info saved: {os.path.basename(path)} ({', '.join(done)})"), ''

    # ------------------------------------------------------------------
    # Apply-filter modal: open / cancel / apply
    # ------------------------------------------------------------------
    @app.callback(
        Output('filter-modal', 'style'),
        Input('apply-filter-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def open_filter_modal(n_clicks):
        return MODAL_SHOWN

    # Relabel the two generic parameter inputs (and their defaults) for the
    # selected filter, hiding the second input for single-parameter filters,
    # and all of them for "Off".
    @app.callback(
        Output('param1-label', 'children'),
        Output('param1-input', 'value'),
        Output('param2-label', 'children'),
        Output('param2-input', 'value'),
        Output('param2-row', 'style'),
        Output('filter-params', 'style'),
        Input('filter-select', 'value'),
    )
    def update_filter_params(filt):
        if filt == FILTER_OFF:
            return (dash.no_update,) * 5 + ({'display': 'none'},)
        specs = FILTER_PARAMS.get(filt, [])
        if not specs:
            return (dash.no_update,) * 6
        label1, default1 = specs[0]
        if len(specs) > 1:
            label2, default2 = specs[1]
            return label1, default1, label2, default2, {}, {}
        return label1, default1, dash.no_update, dash.no_update, {'display': 'none'}, {}

    @app.callback(
        Output('filter-modal', 'style', allow_duplicate=True),
        Output('spectrum', 'figure', allow_duplicate=True),
        Output('filter-modal-error', 'children'),
        Input('filter-cancel', 'n_clicks'),
        Input('filter-apply-confirm', 'n_clicks'),
        State('filter-select', 'value'),
        State('param1-input', 'value'),
        State('param2-input', 'value'),
        State('max-display-input', 'value'),
        State('spectrum', 'figure'),
        prevent_initial_call=True,
    )
    def close_or_apply_filter(cancel, confirm, filt, parameter1, parameter2,
                              max_display, figure):
        triggered = callback_context.triggered[0]['prop_id']
        if 'filter-cancel' in triggered:
            return MODAL_HIDDEN, dash.no_update, ""

        if filt == FILTER_OFF:
            # Remove the line, legend entry included; zooming no longer redraws it.
            _smooth['y'] = None
            patched = Patch()
            patched['data'][smooth_idx]['x'] = []
            patched['data'][smooth_idx]['y'] = []
            patched['data'][smooth_idx]['visible'] = False
            return MODAL_HIDDEN, patched, ""

        try:
            _smooth['y'] = apply_filter(filt, dbm, parameter1, parameter2)
        except FilterError as e:
            return dash.no_update, dash.no_update, str(e)

        # Downsample the new line over the currently visible x-range and show it.
        xaxis = (figure or {}).get('layout', {}).get('xaxis', {})
        rng = None if xaxis.get('autorange') else xaxis.get('range')
        if rng:
            i0 = max(0, int(np.searchsorted(wl, rng[0])) - 1)
            i1 = min(len(wl), int(np.searchsorted(wl, rng[1])) + 1)
        else:
            i0, i1 = 0, len(wl)
        cap = MAX_DISPLAY // 1000 if max_display in (None, '') else int(max_display)
        cap *= 1000
        if cap <= 0:
            w_d, y_d = wl[i0:i1], _smooth['y'][i0:i1]
        else:
            w_d, y_d = lttb(wl[i0:i1], _smooth['y'][i0:i1], cap)

        patched = Patch()
        patched['data'][smooth_idx]['x'] = w_d
        patched['data'][smooth_idx]['y'] = y_d
        patched['data'][smooth_idx]['name'] = FILTER_LABELS.get(filt, 'Smoothed')
        patched['data'][smooth_idx]['visible'] = True
        return MODAL_HIDDEN, patched, ""

    # Sweep-info modal: open / close. Read-only, so there is nothing to apply.
    # Opening rebuilds the table, which picks up a changed label.
    @app.callback(
        Output('sweep-info-modal', 'style'),
        Output('sweep-info-table', 'children'),
        Input('sweep-info-btn', 'n_clicks'),
        Input('sweep-info-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_sweep_info(open_clicks, close_clicks):
        triggered = callback_context.triggered[0]['prop_id']
        if 'sweep-info-close' in triggered:
            return MODAL_HIDDEN, dash.no_update
        return MODAL_SHOWN, _sweep_info_rows()

    # The Label field (right panel). Each change is the sweep's label at once,
    # so even closing the window with its own X keeps it. Save raw data, Save
    # peak info and Sweep info read params.label, and so does main.py once the
    # window closes (config_window.relabel). A label that can't go into a file
    # name isn't used: the last good one stays.
    _run_label = params.label or ''

    @app.callback(
        Output('label-status', 'children'),
        Input('label-input', 'value'),
        prevent_initial_call=True,
    )
    def update_label(text):
        text = text or ''
        error = _label_error(text)
        if error:
            used = f" Still using {params.label}." if params.label else " Still no label."
            return html.Span(error + used, style={'color': '#c0392b'})
        params.label = text or None
        if not text:
            return "Label removed."
        if text == _run_label:
            return f"Back to the original label: {text}"
        return f"Label updated: {text}"

    # Power-readout modal. Opening starts the readout and enables its poll;
    # closing stops both. start() blocks for the instrument check (~1 s).
    @app.callback(
        Output('readout-modal', 'style'),
        Output('readout-tick', 'disabled'),
        Input('readout-btn', 'n_clicks'),
        Input('readout-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_readout(open_clicks, close_clicks):
        if readout is None:
            return dash.no_update, dash.no_update
        if 'readout-close' in callback_context.triggered[0]['prop_id']:
            readout.stop()
            return MODAL_HIDDEN, True
        try:
            readout.start()
        except Exception:
            # check_inst now raises; a Dash callback would swallow it silently
            # and the modal would open with no rows and no explanation.
            log.exception("Power readout failed to start")
        return MODAL_SHOWN, False

    @app.callback(
        Output('readout-rows', 'children'),
        Output('readout-wl-actual', 'children'),
        Output('readout-dbm-actual', 'children'),
        Output('readout-laser', 'value'),
        Input('readout-tick', 'n_intervals'),
        prevent_initial_call=True,
    )
    def refresh_readout(_n):
        # wait=False: skip this tick rather than queue behind a worker thread
        # still mid-query (Dash runs callbacks on a pool, so ticks can overlap).
        rows = readout.read(wait=False) if readout is not None else None
        if rows is None:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update
        laser = dash.no_update
        if readout.emission != _ro_shown['emission']:
            _ro_shown['emission'] = readout.emission
            laser = ['on'] if readout.emission else []
        return (_readout_rows(rows), *_readout_actual(), laser)

    @app.callback(
        Output('readout-msg', 'children'),
        Input('readout-apply', 'n_clicks'),
        Input('readout-laser', 'value'),
        Input('readout-reset', 'n_clicks'),
        State('readout-wl', 'value'),
        State('readout-dbm', 'value'),
        prevent_initial_call=True,
    )
    def readout_controls(_apply, laser_value, _reset, wl_text, dbm_text):
        if readout is None:
            return dash.no_update
        triggered = callback_context.triggered[0]['prop_id']
        if 'readout-laser' in triggered:
            on = 'on' in (laser_value or [])
            # Equal when refresh_readout pushed the box itself: nothing to send.
            # Update _ro_shown only after set_emission, so a tick in between
            # can't push the old state back over this click.
            if on != readout.emission:
                readout.set_emission(on)
            _ro_shown['emission'] = on
            return ''
        if 'readout-reset' in triggered:
            readout.reset_max()
            return ''
        err = readout.set_wavelength(wl_text)
        if err is None and readout.has_laser:
            err = readout.set_power(dbm_text)
        return html.Span(err or 'Applied.', style={'color': 'red' if err else 'blue'})

    @app.callback(
        Output('markers-store', 'data'),
        Output('bw-anchors-store', 'data', allow_duplicate=True),
        Input('spectrum', 'clickData'),
        Input('clear-btn', 'n_clicks'),
        State('markers-store', 'data'),
        State('click-mode', 'value'),
        prevent_initial_call=True,
    )
    def update_markers(clickData, n_clicks, markers, click_mode):
        triggered = callback_context.triggered[0]['prop_id']
        if 'clear-btn' in triggered:
            return [], BW_EMPTY
        if clickData and click_mode == 1:
            pt = clickData['points'][0]
            markers.append({'x': pt['x'], 'y': pt['y']})
        return markers, dash.no_update

    @app.callback(
        Output('bw-anchors-store', 'data'),
        Input('spectrum', 'clickData'),
        State('click-mode', 'value'),
        State('bw-anchors-store', 'data'),
        prevent_initial_call=True,
    )
    def add_bw_marker(clickData, click_mode, anchors):
        if clickData and click_mode == 2:
            # Only the click's x-coordinate matters: Bandwidth is always measured
            # on the first main spectrum (dbm / channels[0]), so the clicked
            # curve's y is intentionally ignored. With several overlapping spectra
            # (multi-channel, reference, scans) this keeps the marker pinned to the
            # first spectrum no matter which line happened to register the click.
            # Clicks alternate between B1 (peak) and B2 (base): the first two
            # place them, then the third moves B1, the fourth B2, and so on.
            points, nxt = list(anchors['points']), anchors['next']
            new = {'x': clickData['points'][0]['x']}
            if nxt < len(points):
                points[nxt] = new
            else:
                points.append(new)
            return {'points': points, 'next': 1 - nxt}
        return dash.no_update

    @app.callback(
        Output('spectrum', 'figure'),
        Input('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def redraw_markers(markers):
        patched = Patch()
        xs = [m['x'] for m in markers]
        ys = [m['y'] for m in markers]
        patched['data'][1]['x']    = xs
        patched['data'][1]['y']    = ys
        patched['data'][1]['text'] = [f'D{i+1}' for i in range(len(markers))]

        # Densify the connector: sample many points along each marker-to-marker
        # segment so a click "snaps" onto the line (Plotly reports the nearest of
        # these points). Empty until there are at least two markers to join.
        lx, ly = [], []
        for i in range(len(markers) - 1):
            seg_dx = xs[i + 1] - xs[i]
            # One interpolated point every ~d_x (the native wavelength spacing)
            # along the segment's x-span, so snap resolution follows the data.
            n = max(2, int(round(abs(seg_dx) / d_x)) + 1)
            t = np.linspace(0.0, 1.0, n)
            lx.extend((xs[i] + t * seg_dx).tolist())
            ly.extend((ys[i] + t * (ys[i + 1] - ys[i])).tolist())
        patched['data'][delta_line_idx]['x'] = lx
        patched['data'][delta_line_idx]['y'] = ly
        return patched

    # ------------------------------------------------------------------
    # The three tables (plot_tables.py builds them). Each re-renders when its
    # data or its Customize choices (table-views) change.
    # ------------------------------------------------------------------
    @app.callback(
        Output('delta-table', 'children'),
        Output('delta-block', 'style'),
        Input('markers-store', 'data'),
        Input('table-views', 'data'),
    )
    def render_delta_table(markers, views):
        # Shown only while Delta markers exist (e.g. not after Clear).
        if not markers:
            return None, {'display': 'none'}
        return (pt.build_table('delta', views['delta'], pt.delta_rows(markers)),
                {'marginTop': '5px'})

    @app.callback(
        Output('custom-table', 'children'),
        Output('custom-block', 'style'),
        Input('mode2-info-store', 'data'),
        Input('table-views', 'data'),
    )
    def render_custom_table(m2, views):
        # Shown once B1 exists; its base columns fill in once B2 does.
        if m2 is None:
            return None, {'display': 'none'}
        return (pt.build_table('custom', views['custom'], [pt.custom_row(channels[0], m2)]),
                {'marginTop': '5px'})

    if pk is not None:
        @app.callback(
            Output('peak-table', 'children'),
            Output('peak-hint', 'children'),
            Input('table-views', 'data'),
            Input('peak-show', 'value'),
        )
        def render_peak_table(views, shown_peaks):
            # Hiding a peak only hides its row here; the plot, the Pass/Fail
            # table and Save peak info still use every peak.
            shown = set(shown_peaks or [])
            rows = [r for r in peak_rows if int(r['Peak']) in shown]
            n_hidden = len(peak_rows) - len(rows)
            hint = f'{n_hidden} of {len(peak_rows)} peaks hidden' if n_hidden else ''
            return pt.build_table('peak', views['peak'], rows, absent=TABLE_ABSENT['peak']), hint

    if exam_out:
        @app.callback(
            Output('passfail-table', 'children'),
            Input('table-views', 'data'),
        )
        def render_passfail_table(views):
            # Redrawn when its Customize dialog changes the Measured decimals.
            return pt.passfail_table(exam, views['passfail'])

    # ------------------------------------------------------------------
    # Customize dialog: one modal for all the tables. The "Customize..."
    # link beside a table's caption opens it for that table.
    # ------------------------------------------------------------------
    @app.callback(
        Output('customize-modal', 'style'),
        Output('customize-table', 'data'),
        Output('customize-title', 'children'),
        Output('customize-peaks', 'style'),
        Output('customize-reset', 'children'),
        Input({'type': 'tbl-open', 'table': ALL}, 'n_clicks'),
        Input('customize-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_customize(_opens, _close):
        trig = callback_context.triggered_id
        if trig == 'customize-close':
            return pt.DIALOG_HIDDEN, *([dash.no_update] * 4)
        if trig is None or not callback_context.triggered[0]['value']:
            return (dash.no_update,) * 5
        table = trig['table']
        # A decimals-only table (Pass/Fail) has no columns to show or move.
        reset = 'Reset decimals' if pt.TABLES[table].get('decimals_only') else 'Reset columns'
        return (pt.DIALOG_SHOWN, table, pt.TABLES[table]['title'],
                {} if table == 'peak' else {'display': 'none'}, reset)

    @app.callback(
        Output('customize-columns', 'children'),
        Input('table-views', 'data'),
        Input('customize-table', 'data'),
    )
    def render_column_list(views, table):
        return pt.column_list(table, views[table], TABLE_ABSENT[table]) if table else []

    @app.callback(
        Output('table-views', 'data'),
        Input({'type': 'tbl-col-up', 'col': ALL}, 'n_clicks'),
        Input({'type': 'tbl-col-down', 'col': ALL}, 'n_clicks'),
        Input({'type': 'tbl-col-show', 'col': ALL}, 'value'),
        Input({'type': 'tbl-dec-down', 'col': ALL}, 'n_clicks'),
        Input({'type': 'tbl-dec-up', 'col': ALL}, 'n_clicks'),
        Input('customize-reset', 'n_clicks'),
        State('table-views', 'data'),
        State('customize-table', 'data'),
        prevent_initial_call=True,
    )
    def update_table_view(_up, _down, shows, _dec_down, _dec_up, _reset, views, table):
        trig = callback_context.triggered_id
        if trig is None or table is None:
            return dash.no_update
        view = copy.deepcopy(views[table])
        if trig == 'customize-reset':
            view = pt.default_view(table)
        elif trig['type'] == 'tbl-col-show':
            cols = [item['id']['col'] for item in callback_context.inputs_list[2]]
            locked = pt.TABLES[table]['locked']
            hidden = {c for c, v in zip(cols, shows) if not v and c != locked}
            # A column this window doesn't list keeps its remembered choice.
            hidden |= {c for c in view['hidden'] if c in TABLE_ABSENT[table]}
            view['hidden'] = [c for c in view['order'] if c in hidden]
        else:
            # The column list is rebuilt after every change, and its fresh
            # buttons (n_clicks=0) fire this callback too: only a click counts.
            if not callback_context.triggered[0]['value']:
                return dash.no_update
            col = trig['col']
            if trig['type'] in ('tbl-col-up', 'tbl-col-down'):
                # Move it past the next column the dialog lists, stepping over
                # any this window doesn't have, so every click moves it. Only
                # this column changes place; the rest keep their order.
                up = trig['type'] == 'tbl-col-up'
                order = view['order']
                listed = [c for c in order if c not in TABLE_ABSENT[table]]
                k = listed.index(col) + (-1 if up else 1)
                if not 0 <= k < len(listed):
                    return dash.no_update
                order.remove(col)
                order.insert(order.index(listed[k]) + (0 if up else 1), col)
                view['hidden'] = [c for c in order if c in set(view['hidden'])]
            else:
                dec = pt.decimals_for(table, col, view)
                dec += 1 if trig['type'] == 'tbl-dec-up' else -1
                if not 0 <= dec <= pt.MAX_DECIMALS:
                    return dash.no_update
                view['decimals'][col] = dec
        if view == views[table]:
            return dash.no_update
        _table_views[table] = copy.deepcopy(view)   # kept for the next plot window
        return {**views, table: view}

    @app.callback(
        Output('peak-show', 'value'),
        Input('show-all-peaks', 'n_clicks'),
        prevent_initial_call=True,
    )
    def show_all_peaks(_n):
        _hidden_peaks.clear()   # also forgets numbers this sweep doesn't have
        return [int(r['Peak']) for r in peak_rows]

    @app.callback(
        Input('peak-show', 'value'),
        prevent_initial_call=True,
    )
    def remember_hidden_peaks(shown):
        # Keep remembered numbers this sweep doesn't have (e.g. P3 when it found
        # two peaks), so they stay hidden in a later sweep that has them again.
        ids = {int(r['Peak']) for r in peak_rows}
        kept = {p for p in _hidden_peaks if p not in ids}
        _hidden_peaks[:] = sorted(kept | (ids - set(shown or [])))

    def _bw_sample(anchor):
        """The spectrum sample a Bandwidth marker sits on: its clicked x
        snapped to the nearest point of `wl`. Returns (idx, x, y)."""
        x_target = anchor['x']
        i = np.searchsorted(wl, x_target)
        i = np.clip(i, 1, len(wl) - 1)
        idx = i if abs(wl[i] - x_target) < abs(wl[i-1] - x_target) else i - 1
        return idx, float(wl[idx]), float(dbm[idx])

    @app.callback(
        Output('bw-auto-fields', 'style'),
        Output('bw-manual-fields', 'style'),
        Input('bw-mode', 'value'),
        prevent_initial_call=True,
    )
    def show_bw_mode_fields(mode):
        hidden = {'display': 'none'}
        return ({}, hidden) if mode == 'auto' else (hidden, {})

    @app.callback(
        Output('bw-settings', 'style'),
        Input('click-mode', 'value'),
        prevent_initial_call=True,
    )
    def show_bandwidth_settings(click_mode):
        return BW_SETTINGS_STYLE if click_mode == 2 else BW_SETTINGS_HIDDEN

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Output('mode2-marker-info', 'children'),
        Output('mode2-offset-info', 'children'),
        Output('mode2-info-store', 'data'),
        Output('bw-hint', 'children'),
        Input('bw-anchors-store', 'data'),
        Input('bw-mode', 'value'),
        Input('bw-pct-input', 'value'),
        Input('mode2-offset-input', 'value'),
        prevent_initial_call=True,
    )
    def update_mode2_markers(anchors, mode, pct, manual_offset):
        patched = Patch()
        if not anchors['points']:
            for i in (2, 3, 4):
                patched['data'][i]['x'] = []
                patched['data'][i]['y'] = []
                patched['data'][i]['text'] = []
            return patched, "", "", None, ""
        # B1 is the peak (the dip the width is measured at), B2 the base.
        samples = [_bw_sample(a) for a in anchors['points']]
        idx, x, y = samples[0]
        base = {'x': samples[1][1], 'y': samples[1][2]} if len(samples) > 1 else None
        patched['data'][2]['x'] = [s[1] for s in samples]
        patched['data'][2]['y'] = [s[2] for s in samples]
        patched['data'][2]['text'] = [f'B{i + 1}' for i in range(len(samples))]

        # The level to measure at (y_offset dB above the dip's bottom) and how
        # far out to search on each side, in samples.
        y_offset, search_range, hint = None, None, ""
        if mode == 'auto':
            if base is None:
                hint = "Click again to place B2 (the base)."
            elif base['y'] <= y:
                hint = "B2 (the base) must be above B1 (the peak)."
            elif pct:
                # pct of the depth from B1 up to B2 (the depth the Custom peak
                # table shows), searching out to B2's distance from B1.
                y_offset = (base['y'] - y) * pct / 100
                search_range = max(1, round(abs(base['x'] - x) / d_x))
        elif manual_offset:
            # No search limit: the whole spectrum (about 1-3 ms even for 2M
            # points). If the curve never rises that far on a side, there's
            # no width to show.
            y_offset = manual_offset
            search_range = len(wl)

        width_pm = None
        if y_offset:
            left_nm, right_nm, width_pm, found = find_bandwidth(wl, dbm, idx, y_offset, search_range)
            if not found:
                # A side never reached the level within the search (Manual
                # searches to the spectrum's end). Its edge would sit at the end
                # of the search, off the level, so show no width at all.
                width_pm = None
                hint = ("No width: the amplitude is too large for this dip." if mode == 'manual' else
                        f"No width: an edge wasn't found within B2's distance from B1 "
                        f"(±{search_range * d_x * 1000:g} pm).")

        if width_pm is not None:
            # Both width markers sit on the level, so they always form a
            # horizontal line.
            level = y + y_offset
            patched['data'][3]['x'] = [float(left_nm)]
            patched['data'][3]['y'] = [level]
            patched['data'][3]['text'] = ['L']
            patched['data'][4]['x'] = [float(right_nm)]
            patched['data'][4]['y'] = [level]
            patched['data'][4]['text'] = [f'(width: {width_pm:.3f} pm)']

            width_info = f"width: {width_pm:.3f} pm\n"
        else:
            patched['data'][3]['x'] = []
            patched['data'][3]['y'] = []
            patched['data'][3]['text'] = []
            patched['data'][4]['x'] = []
            patched['data'][4]['y'] = []
            patched['data'][4]['text'] = []
            width_info = ""
        # B1's position, its width and the amplitude it was measured at (None
        # when there's no width), and B2 as the base (None until placed): what
        # the Custom peak table and Save peak info read.
        info = {'x': x, 'y': y, 'width_pm': width_pm,
                'amplitude_db': y_offset if width_pm is not None else None, 'base': base}
        return patched, f"Marker:{x:.7f} nm\n       {y:.5f} dBm\n", width_info, info, hint

    def _resample_curves(max_display, x0=None, x1=None):
        """Patch every spectrum/reference/overlay line to <=max_display points
        over the wavelength window [x0, x1] (full range when x0/x1 are None).

        Every line shares the same `wl` axis (and the same [x0, x1] slice), so
        they are downsampled together in a single lttb_multi pass. The trace
        index + wl-aligned y for each line were recorded during figure build
        (main_traces / ref_traces / overlay_traces), so only the lines that were
        actually drawn are touched."""
        # The field value is in thousands of points; multiply to get the real
        # cap. None/empty input -> default; 0 -> downsampling disabled (full data).
        max_display = MAX_DISPLAY // 1000 if max_display in (None, '') else int(max_display)
        max_display *= 1000
        curves = main_traces + ref_traces + overlay_traces
        # Include the filtered line once it has been applied.
        if _smooth['y'] is not None:
            curves = curves + [(smooth_idx, _smooth['y'])]

        if x0 is None or x1 is None:
            i0, i1 = 0, len(wl)
        else:
            i0 = max(0, int(np.searchsorted(wl, x0)) - 1)
            i1 = min(len(wl), int(np.searchsorted(wl, x1)) + 1)
        w_arr = wl[i0:i1]
        if max_display <= 0:
            results = [(w_arr, d[i0:i1]) for _, d in curves]
        else:
            results = lttb_multi(w_arr, [d[i0:i1] for _, d in curves], max_display)

        patched = Patch()
        for (idx, _), (w_d, d_d) in zip(curves, results):
            patched['data'][idx]['x'] = w_d
            patched['data'][idx]['y'] = d_d
        return patched

    # The x-range on screen, as the zoom messages last reported it (None = the
    # whole sweep). A window resize arrives as {'autosize': True} with no range
    # while the view stays zoomed, so it must redraw this range, not the sweep.
    _view = {'x': None}

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Input('spectrum', 'relayoutData'),
        State('max-display-input', 'value'),
        prevent_initial_call=True,
    )
    def resample_on_zoom(relayout, max_display):
        if not relayout:
            return dash.no_update

        # Resample over the visible x-window.
        if relayout.get('xaxis.autorange'):
            _view['x'] = None
        elif 'xaxis.range[0]' in relayout:
            _view['x'] = (relayout['xaxis.range[0]'], relayout['xaxis.range[1]'])
        elif not relayout.get('autosize'):
            return dash.no_update
        return _resample_curves(max_display, *(_view['x'] or ()))

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Input('max-display-input', 'value'),
        State('spectrum', 'figure'),
        prevent_initial_call=True,
    )
    def resample_on_max_display(max_display, figure):
        # Re-render at the new resolution over the currently visible x-range
        # (read from the live figure layout; None => full autorange).
        xaxis = (figure or {}).get('layout', {}).get('xaxis', {})
        rng = None if xaxis.get('autorange') else xaxis.get('range')
        if rng:
            return _resample_curves(max_display, rng[0], rng[1])
        return _resample_curves(max_display)

    # ------------------------------------------------------------------
    # Show / hide popup (built above as show_hide_modal).
    # ------------------------------------------------------------------
    @app.callback(
        Output('show-hide-modal', 'style'),
        Input('show-hide-btn', 'n_clicks'),
        Input('show-hide-close', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_show_hide(_open, _close):
        if callback_context.triggered_id == 'show-hide-close':
            return pt.DIALOG_HIDDEN
        return pt.DIALOG_SHOWN

    @app.callback(
        Output('sh-all', 'value'),
        Output('sh-peak-all', 'value'),
        Output('sh-peak', 'value'),
        Output('sh-width-all', 'value'),
        Output('sh-width', 'value'),
        Output('sh-other', 'value'),
        Input('sh-all', 'value'),
        Input('sh-peak-all', 'value'),
        Input('sh-peak', 'value'),
        Input('sh-width-all', 'value'),
        Input('sh-width', 'value'),
        Input('sh-other', 'value'),
        prevent_initial_call=True,
    )
    def sync_show_hide(all_box, peak_box, peak, width_box, width, other):
        """Ticking "All" or a group's "(all)" box ticks or clears its items,
        and each of those boxes stays ticked only while all its items are."""
        trig = callback_context.triggered_id
        if trig == 'sh-all':
            peak, width, other = (SH_KEYS[g] if all_box else [] for g in ('peak', 'width', 'other'))
        elif trig == 'sh-peak-all':
            peak = SH_KEYS['peak'] if peak_box else []
        elif trig == 'sh-width-all':
            width = SH_KEYS['width'] if width_box else []
        peak, width, other = peak or [], width or [], other or []
        full = {g: set(v) >= set(SH_KEYS[g])
                for g, v in (('peak', peak), ('width', width), ('other', other))}
        box = lambda on: ['all'] if on else []
        return box(all(full.values())), box(full['peak']), peak, box(full['width']), width, other

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Output('exam-block', 'style'),
        Input('sh-peak', 'value'),
        Input('sh-width', 'value'),
        Input('sh-other', 'value'),
        prevent_initial_call=True,
    )
    def apply_show_hide(peak, width, other):
        shown = set(peak or []) | set(width or []) | set(other or [])
        # Remembered for the next plot window. An item this window doesn't
        # have keeps whatever was remembered for it.
        listed = {k for keys in SH_KEYS.values() for k in keys}
        _hidden_items.difference_update(listed)
        _hidden_items.update(listed - shown)
        patched = Patch()
        # A hidden plot item stays in the legend ('legendonly'), where a click
        # still brings it back.
        for key, i in SH_TRACES.items():
            patched['data'][i]['visible'] = True if key in shown else 'legendonly'
        return patched, ({} if 'passfail' in shown else {'display': 'none'})

    if pk is not None:
        @app.callback(
            Output('peak-table-container', 'style'),
            Input('sh-peak', 'value'),
            prevent_initial_call=True,
        )
        def toggle_peak_table(value):
            return {} if 'table' in (value or []) else {'display': 'none'}

    # ------------------------------------------------------------------
    # Launch — Dash in a background thread, webview in main thread
    #
    # Use make_server (instead of app.run) so we hold a server handle and
    # can shut it down when the window closes. Otherwise the daemon thread
    # keeps the previous server alive on `port`, and the next call to
    # plot_plotly connects to that stale server (showing the old data).
    # ------------------------------------------------------------------
    from werkzeug.serving import make_server

    # Bind to port 0 so the OS hands out a *fresh, guaranteed-free* port on
    # every call. Reusing a fixed port (e.g. 8050) across repeated calls in
    # the main_single loop races with the previous server's teardown: the
    # socket can linger in TIME_WAIT and the new window connects to a stale
    # server, leaving the figure unresponsive until the next run.
    server = make_server('127.0.0.1', 0, app.server, threaded=True)
    bound_port = server.server_port
    # poll_interval=0.1 (vs werkzeug's 0.5 default) so thread.join() below
    # notices server.shutdown() ~5x faster on window close.
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.1), daemon=True)
    thread.start()

    window = webview.create_window(
        title,
        f'http://127.0.0.1:{bound_port}',
        width=1200, height=800, maximized=True,
    )
    window.events.loaded += _apply_zoom
    _window_holder['window'] = window
    try:
        webview.start()
    finally:
        server.shutdown()
        thread.join()

    # The readout modal may have been open when the window closed. stop() is
    # idempotent and waits out a tick still in flight on a worker thread.
    if readout is not None:
        readout.stop()

    # True when the user clicked Repeat (or pressed Enter); the caller uses this
    # to auto-Run the next sweep. False on a normal window close.
    return _repeat['flag']


# ---------------------------------------------------------------------------
# Demo: run this file directly to test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from open_csv import plot_raw
    from inst_dummy import dummy_readout
    # csv_path = "Raw Data/hc13n_watt_reference.csv"
    csv_path = "Raw Data/02609299.csv"
    # Dummy instruments, so the Power Readout modal can be exercised here.
    plot_raw(csv_path, readout=dummy_readout("N7778C"))
    