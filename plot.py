import threading
import os
import tempfile
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, dash_table, Input, Output, State, Patch, callback_context
import webview
from webview import FileDialog

import json
import logging

log = logging.getLogger(__name__)

import shutdown
from structs import Params, Dataset
from analyze_data import peak_detection, find_bandwidth, exam_peak
from save_csv import save_csv_raw, save_csv_peak_row, COL_CH, COL_REF, COL_SCAN, RAW_DIR
from plot_helper import lttb, lttb_multi, pre_process
from datapath import data_path
from filters import FILTER_LABELS, FILTER_PARAMS, apply_filter, FilterError

# Shared styles for the three DataTables (peak, custom, delta markers).
# Row height is driven by the cell's vertical padding; keep it small for compact rows.
TABLE_CELL_STYLE = {'fontFamily': '"Times New Roman", Times, serif',
                    'fontSize': '15px', 'padding': '1px 8px', 'textAlign': 'right', 'height': '20px', 'lineHeight': '1'}
TABLE_HEADER_STYLE = {'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'}
# Left indent shared by the three tables and the exam Pass/Fail line above them.
TABLE_LEFT_MARGIN = '10px'
TABLE_STYLE = {'marginBottom': '10px', 'marginLeft': TABLE_LEFT_MARGIN, 'width': 'fit-content'}
# Caption shown above each table. Sans-serif + muted so it frames the serif data.
TABLE_TITLE_STYLE = {'fontFamily': 'system-ui, sans-serif', 'fontWeight': 'bold',
                     'fontSize': '13px', 'color': '#555',
                     'margin': '0 0 4px', 'marginLeft': TABLE_LEFT_MARGIN}

# Remembered across display_plot() calls (i.e. across loop iterations) so the
# "Choose a file" dropdown can pre-select the file used last time.
_last_peak_file   = ''
_last_peak_label  = ''
_last_temperature = None

def display_plot(raw_w: Dataset, params: Params, *, title="Absorption Spectrum"):
    """
    Parameters
    ----------

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

    # ------------------------------------------------------------------
    # Click-mode 2 fine-tune slider sensitivity
    #   SLIDER_RANGE : half-range of the slider offset in nm
    #                  (slider goes from -SLIDER_RANGE to +SLIDER_RANGE)
    #   SLIDER_STEP  : minimum increment per tick in nm
    #                  (e.g. 0.0001 nm = 0.1 pm)
    # ------------------------------------------------------------------
    SLIDER_RANGE = 0.002  # nm  
    SLIDER_STEP  = d_x    # nm 

    OFFSET_RANGE = 25 # half-range of searching in samples. 0.0125 pm * 2000 = 25.0 pm
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
    # data[2] — mode-2 single marker (always replaced)
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
    exam_out, exam_msg, exam_idx = exam_peak(pk, params)
    if pk is not None:
        # data[5..10] — peak annotation traces (Peaks, L/R bases, FWHM max/avg/min)
        initial_fig.add_scatter(x=pk.x_nm, y=dbm[pk.x_idx], mode='markers+text', name='Peaks', marker=dict(size=8, color='#E63946', symbol='circle', line=_border), text=[f"P{i}" for i, _ in enumerate(pk.x_idx, start=1)], textposition='bottom center')
        
        initial_fig.add_scatter(x=wl[pk.l_idx], y=dbm[pk.l_idx], mode='markers+text', name='Left bases', marker=dict(size=8, color='#2A9D8F', symbol='triangle-up', line=_border), text=[f"P{i}:L({e[0]:.3f}, {e[1]:.3f})" for i, e in enumerate(zip(wl[pk.l_idx], dbm[pk.l_idx]), start=1)], textposition='top right')
        
        initial_fig.add_scatter(x=wl[pk.r_idx], y=dbm[pk.r_idx], mode='markers+text', name='Right bases', marker=dict(size=8, color='#2A9D8F', symbol='triangle-down', line=_border), text=[f"P{i}:R({e[0]:.3f}, {e[1]:.3f})" for i, e in enumerate(zip(wl[pk.r_idx], dbm[pk.r_idx]), start=1)], textposition='top left')
        
        initial_fig.add_scatter(x=np.concatenate([pk.max.l_nm, pk.max.r_nm]), y=np.concatenate([pk.max.w_y, pk.max.w_y]), mode='markers', name="FWHM (max base)", visible=True, marker=dict(size=8, color='#F4A261', symbol='square', line=_border))

        initial_fig.add_scatter(x=np.concatenate([pk.avg.l_nm, pk.avg.r_nm]), y=np.concatenate([pk.avg.w_y, pk.avg.w_y]), mode='markers', name="FWHM (avg base)", visible=True, marker=dict(size=8, color='#457B9D', symbol='diamond', line=_border))

        initial_fig.add_scatter(x=np.concatenate([pk.min.l_nm, pk.min.r_nm]), y=np.concatenate([pk.min.w_y, pk.min.w_y]), mode='markers', name="FWHM (min base)", visible=True, marker=dict(size=8, color='#8E44AD', symbol='hexagon', line=_border))

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
        # Display-only column ("P1", "P2", ...). The integer "Peak" column stays
        # the key used by all lookups/ordering and the table filter_query; the
        # table renders this column in its place (see the columns list below).
        peak_df["Peak_disp"] = [f"P{p}" for p in peak_df["Peak"]]

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
    # Reference sweep. Insertion loss (deepest dip vs reference) is computed
    # on channel 1 only; a dashed reference line is drawn for every channel.
    # ------------------------------------------------------------------
    il_idx = None  # trace index of the IL marker (None when no reference)
    if params.reference:
        gmin_idx = int(np.nanargmin(dbm))
        gmin_x, gmin_y = float(wl[gmin_idx]), float(dbm[gmin_idx])
        initial_fig.add_scatter(
            x=[gmin_x], y=[gmin_y], mode='markers+text', name='Insertion loss',
            marker=dict(symbol='star', size=9, color='#C0392B', line=_border),
            text=[f"IL: {gmin_y:.5f} dB"], textposition='bottom center',
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
        xaxis_title=dict(text='<b>x - Wavelength (nm)</b>', font=dict(size=12), standoff=5),
        yaxis_title=dict(text='<b>y - Power (dBm or dB)</b>', font=dict(size=12), standoff=5),
        hovermode='closest',
        showlegend=True,
        legend=dict(x=1.0, xanchor='left'),
        height=550,
        width=1300,
        margin=dict(l=50, t=30, b=5),
        uirevision='constant',
    )

    initial_fig.update_yaxes(autorange='reversed')
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

    # Block the right mouse button over the plot. Plotly has no config flag to
    # disable right-drag panning, and that pan is what drops the y-axis
    # autorange:'reversed' orientation (a regression that only showed up in the
    # packaged build's bundled plotly.js). A capture-phase listener on the
    # document intercepts button-2 mousedown / contextmenu before they reach
    # Plotly's own drag handlers, so right-drag never starts. Injected via
    # index_string (not an assets/ folder) so it survives PyInstaller freezing.
    app.index_string = '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script>
        (function () {
            var onGraph = function (e) {
                return e.target && e.target.closest && e.target.closest('#spectrum');
            };
            document.addEventListener('mousedown', function (e) {
                if (e.button === 2 && onGraph(e)) {
                    e.stopPropagation();
                    e.preventDefault();
                }
            }, true);
            document.addEventListener('contextmenu', function (e) {
                if (onGraph(e)) { e.preventDefault(); }
            }, true);
        })();
        </script>
    </body>
</html>'''

    # ------------------------------------------------------------------
    # Right sidebar styles. The container sets the 14px default font, which
    # cascades to labels/checklists/radio items. Form controls (<input>)
    # don't inherit font-size, so INPUT_STYLE restates it. Hints/notes use
    # the smaller NOTE_STYLE (11px).
    # ------------------------------------------------------------------
    HEADING_STYLE = {'fontWeight': 'bold', 'display': 'block', 'marginBottom': '6px'}
    NOTE_STYLE = {'fontSize': '11px', 'color': '#888', 'display': 'block'}
    # NOTE: text stays left-aligned — WebKit (pywebview) ignores text-align on
    # type='number' inputs, and centering would require dropping the -/+ steppers.
    INPUT_STYLE = {'width': '140px', 'boxSizing': 'border-box',
                   'fontSize': '14px', 'padding': '2px 5px'}
    INPUT_STYLE_FULL = {**INPUT_STYLE, 'width': '100%'}

    right_sidebar = html.Div([
        html.Div([
            html.Label("Max points(x1000)/plot", style={**HEADING_STYLE, 'marginBottom': '4px'}),
            dcc.Input(
                id='max-display-input',
                type='number', min=0, max=1000, value=MAX_DISPLAY // 1000,
                debounce=True,
                style=INPUT_STYLE,
            ),
            html.Div("0 = no downsampling (may be slow)",
                     style={**NOTE_STYLE, 'marginTop': '2px'}),
        ]),
        html.Details([
            html.Summary("Show markers/table",
                         style={'fontWeight': 'bold', 'cursor': 'pointer', 'marginBottom': '6px'}),
            dcc.Checklist(
                id='fwhm-all',
                options=[{'label': 'all', 'value': 'all'}],
                value=['all'],
                style={'marginBottom': '2px'},
                labelStyle={'display': 'block'},
            ),
            dcc.Checklist(
                id='fwhm-dropdown',
                options=[
                    {'label': 'peaks', 'value': 'peaks'},
                    {'label': 'FWHM (max base)',  'value': 'max'},
                    {'label': 'FWHM (avg base)',  'value': 'avg'},
                    {'label': 'FWHM (min base)',  'value': 'min'},
                    {'label': 'peak table', 'value': 'table'},
                ] + ([{'label': 'Insertion loss', 'value': 'il'}] if il_idx is not None else []),
                value=['peaks', 'max', 'avg', 'min', 'table'] + (['il'] if il_idx is not None else []),
                style={'marginBottom': '4px', 'marginLeft': '16px'},
                labelStyle={'display': 'block'},
            ),
        ], open=True) if pk is not None else None,
        html.Div([
            html.Label("Click Mode", style=HEADING_STYLE),
            dcc.RadioItems(
                id='click-mode',
                options=[{'label': 'Delta marker', 'value': 1}, {'label': 'Bandwidth marker', 'value': 2}],
                value=1,
                inline=True,
                labelStyle={'display': 'inline-block', 'marginRight': '16px'},
                style={'display': 'inline-block'},
            ),
            html.Button('Clear markers', id='clear-btn', n_clicks=0,
                        style={'width': '150px', 'fontSize': '14px',
                               'padding': '5px 12px', 'marginTop': '5px'}),
            html.Div([
                html.Label("Fine tune (Bandwidth marker)",
                           style={**NOTE_STYLE, 'marginBottom': '4px'}),
                dcc.Slider(
                    id='mode2-slider',
                    min=-SLIDER_RANGE,
                    max=SLIDER_RANGE,
                    step=SLIDER_STEP,
                    value=0,
                    marks=None,
                    tooltip=None,
                    updatemode='drag',
                ),
                html.Div(id='mode2-marker-info',
                         style={'display': 'none'}),
                html.Label("Bandwidth amplitude (dB)",
                           style={**NOTE_STYLE, 'marginTop': '12px', 'marginBottom': '4px'}),
                dcc.Input(
                    id='mode2-offset-input',
                    type='number', step='any',
                    value=1,
                    debounce=True,
                    style=INPUT_STYLE_FULL,
                ),
                html.Label("Slider range (pm)",
                           style={**NOTE_STYLE, 'marginTop': '6px', 'marginBottom': '4px'}),
                dcc.Input(
                    id='slider-range-input',
                    type='number', step='any', value=SLIDER_RANGE * 1000,
                    debounce=True,
                    style=INPUT_STYLE_FULL,
                ),
                html.Div(id='mode2-offset-info',
                         style={'display': 'none'}),
                html.Label("Search range (pm)",
                           style={**NOTE_STYLE, 'marginTop': '12px', 'marginBottom': '4px'}),
                dcc.Input(
                    id='mode2-search-range-input',
                    type='number', step=5,
                    value=OFFSET_RANGE,
                    debounce=True,
                    style=INPUT_STYLE_FULL,
                ),
            ], style={'marginTop': '10px', 'width': '140px'}),
        ]),
    ], style={'padding': '20px 10px', 'display': 'flex', 'flexDirection': 'column',
              'gap': '20px', 'fontSize': '14px', 'fontFamily': 'system-ui, sans-serif'})

    # ------------------------------------------------------------------
    # Horizontal menu bar (top of the window). The action buttons live
    # here instead of the sidebar; their ids are unchanged so all the
    # existing callbacks (and the Enter keybind) keep working.
    # ------------------------------------------------------------------
    NAV_BTN_STYLE = {
        'fontSize': '14px', 'padding': '3px 14px', 'border': 'none',
        'background': 'transparent', 'color': '#fff', 'cursor': 'pointer',
        'fontFamily': 'system-ui, sans-serif',
    }
    # The callbacks still return their status strings into these divs; the divs
    # are just not rendered.
    NAV_INFO_STYLE = {'display': 'none'}
    top_navbar = html.Nav([
        html.Button('Save Raw data...', id='save-raw-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Div(id='save-raw-info', style=NAV_INFO_STYLE),
        html.Button(['Save ', html.U('P'), 'eak info...'], id='save-peak-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Div(id='save-peak-info', style=NAV_INFO_STYLE),
        html.Button('Apply filter...', id='apply-filter-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Button('Plot in Watt...', id='plot-watt-btn', n_clicks=0, style=NAV_BTN_STYLE),
        html.Div(id='plot-watt-info', style=NAV_INFO_STYLE),
        # Repeat: close this plot window and auto-Run the next sweep with the same parameters. Also bound to the Enter key (see the clientside callback below).
        html.Button('Repeat (Enter)', id='repeat-btn', n_clicks=0,
                    style={**NAV_BTN_STYLE, 'fontWeight': 'bold', 'marginLeft': 'auto'}),
        # Dummy sink for the keybind clientside callback; the keydown
        # listener it installs is what actually clicks the button.
        html.Div(id='repeat-keybind-dummy', style={'display': 'none'}),
    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '4px',
              'padding': '3px 16px', 'backgroundColor': '#2c3e50'})

    # ------------------------------------------------------------------
    # "Save peak info" modal — choose a detected peak (or the custom one)
    # and enter a label, then append a row to the fixed Peak Analyses CSV.
    # ------------------------------------------------------------------
    if pk is not None:
        # Put the highlighted peak (max Depth_max, see line ~329) at the top.
        max_peak = int(peak_df.loc[peak_df['Depth_max'].idxmax(), 'Peak'])
        if exam_idx is not None:
            ordered_peaks = [exam_idx] + ([max_peak] if max_peak != exam_idx else [] ) + [int(p) for p in peak_df['Peak'] if int(p) not in [exam_idx, max_peak]]
            peak_df.loc[peak_df["Peak"] == exam_idx, "Category"] += "(criteria)"
        else:
            ordered_peaks = [max_peak] + [int(p) for p in peak_df['Peak'] if int(p) != max_peak]
        peak_options = []
        for p in ordered_peaks:
            label = f'P{p}'
            if exam_idx is not None and p == exam_idx:
                label += " (criteria) "
            if p == max_peak:
                label += " (deepest)"
            peak_options.append({'label': label, 'value': f'peak:{p}'})
    else:
        peak_options = []
    peak_options += [{'label': 'custom', 'value': 'custom'}]

    # Directory where peak CSVs live, and the default filename to fall back on.
    PEAKS_DIR = data_path("Peaks")
    DEFAULT_PEAK_FILENAME = '.csv'

    def _peak_file_options():
        """Dropdown options for existing CSVs in PEAKS_DIR, plus an empty item."""
        files = sorted(f for f in os.listdir(PEAKS_DIR)
                       if f.lower().endswith('.csv')
                       and os.path.isfile(os.path.join(PEAKS_DIR, f)))
        opts = [{'label': f'Create new file', 'value': ''}]
        opts += [{'label': f, 'value': f} for f in files]
        return opts

    def _remembered_file_value(opts):
        """Last-used file if it still exists among the options, else ''."""
        values = {o['value'] for o in opts}
        return _last_peak_file if _last_peak_file in values and _last_peak_file else ''

    MODAL_OVERLAY = {
        'position': 'fixed', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0,
        'backgroundColor': 'rgba(0,0,0,0.45)', 'zIndex': 1000,
        'alignItems': 'center', 'justifyContent': 'center',
    }
    MODAL_HIDDEN = {**MODAL_OVERLAY, 'display': 'none'}
    MODAL_SHOWN  = {**MODAL_OVERLAY, 'display': 'flex'}

    def _peak_stats(sel, m2, markers):
        """Resolve (wavelength, depth, width) for the selected peak, mirroring
        the values used when saving. Returns None for any value that isn't
        available (e.g. a 'custom' peak with no markers placed yet)."""
        try:
            if sel == 'custom':
                if m2 is None or not markers:
                    return None, None, None
                return m2['x'], m2['y'] - markers[-1]['y'], m2.get('width_pm')
            i   = int(sel.split(':')[1])
            row = peak_df[peak_df['Peak'] == i].iloc[0]
            return float(row['x']), float(row['Depth_max']), float(row['FWHM_max'])
        except Exception:
            return None, None, None

    def _fmt_stat(v, nd):
        """Format a stat value to nd decimals, or '' when unavailable."""
        return '' if v is None else f'{float(v):.{nd}f}'

    # Insertion loss for the global minimum, same expression used at save time.
    _il_value = round(gmin_y, 5) if params.reference else None

    # Initial read-only stats for the default (first) peak selection.
    _init_wl, _init_depth, _init_width = _peak_stats(peak_options[0]['value'], None, None)

    _stat_label_style = {'fontWeight': 'bold', 'display': 'block', 'marginBottom': '4px'}
    _stat_input_style = {'width': '100%', 'boxSizing': 'border-box',
                         'marginBottom': '8px', 'backgroundColor': '#F2F2F2'}

    peak_modal = html.Div(
        id='peak-modal',
        style=MODAL_HIDDEN,
        children=html.Div([
            html.H4('Save peak info', style={'marginTop': 0}),
            html.Label('Select peak', style={'fontWeight': 'bold', 'display': 'block', 'marginBottom': '4px'}),
            dcc.Dropdown(id='peak-select', options=peak_options,
                         value=peak_options[0]['value'], clearable=False,
                         style={'marginBottom': '12px'}),
            html.Label('Wavelength (nm)', style=_stat_label_style),
            dcc.Input(id='peak-wavelength', type='text', readOnly=True,
                      value=_fmt_stat(_init_wl, 7), style=_stat_input_style),
            html.Label('Depth (dB)', style=_stat_label_style),
            dcc.Input(id='peak-depth', type='text', readOnly=True,
                      value=_fmt_stat(_init_depth, 5), style=_stat_input_style),
            html.Label('Width (pm)', style=_stat_label_style),
            dcc.Input(id='peak-width', type='text', readOnly=True,
                      value=_fmt_stat(_init_width, 3), style=_stat_input_style),
            html.Label('Insertion loss (IL)', style=_stat_label_style),
            dcc.Input(id='peak-loss', type='text', value=_il_value, readOnly=True, placeholder="Optional", style=_stat_input_style),
            html.Label('Label / Serial number', style={'fontWeight': 'bold', 'display': 'block',
                                       'marginBottom': '4px'}),
            dcc.Input(id='peak-label', type='text', value=_last_peak_label, debounce=False, placeholder="Required",
                      style={'width': '100%', 'boxSizing': 'border-box',
                             'marginBottom': '8px'}),
            html.Label('Temperature (\u00B0C)', style={'fontWeight': 'bold', 'display': 'block',
                                             'marginBottom': '4px'}),
            dcc.Input(id='peak-temperature', type='number', value=_last_temperature, debounce=False, placeholder="Optional",
                      style={'width': '100%', 'boxSizing': 'border-box',
                             'marginBottom': '8px'}),
            html.Label('Choose file', style={'fontWeight': 'bold', 'display': 'block',
                                               'marginBottom': '4px'}),
            dcc.Dropdown(id='peak-file-select', options=_peak_file_options(),
                         value=_remembered_file_value(_peak_file_options()),
                         clearable=False,
                         style={'marginBottom': '12px'}),
            html.Div(id='peak-modal-error',
                     style={'color': '#C0392B', 'fontSize': '12px',
                            'minHeight': '16px', 'marginBottom': '8px'}),
            html.Div([
                html.Button('Cancel', id='peak-cancel', n_clicks=0),
                html.Button('Save', id='peak-save-confirm', n_clicks=0,
                            style={'marginLeft': '8px'}),
            ], style={'textAlign': 'right'}),
        ], style={'backgroundColor': 'white', 'padding': '20px 24px',
                  'borderRadius': '8px', 'width': '320px',
                  'fontFamily': 'system-ui, sans-serif',
                  'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}),
    )

    # ------------------------------------------------------------------
    # "Apply filter" modal — pick a smoothing filter and its parameters,
    # then draw the filtered channel-1 signal as the "Smoothed" trace.
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
                         for val, name in FILTER_LABELS.items()],
                value=next(iter(FILTER_LABELS)),
                clearable=False, searchable=False,
                # Tall enough for every option so the menu never inner-scrolls
                # (default maxHeight is 200px); optionHeight default is 35px.
                optionHeight=35,
                maxHeight=300,
                style={'marginBottom': '12px'},
            ),
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
            html.Div(id='filter-modal-error',
                     style={'color': '#C0392B', 'fontSize': '12px',
                            'minHeight': '16px', 'marginBottom': '8px'}),
            html.Div([
                html.Button('Cancel', id='filter-cancel', n_clicks=0),
                html.Button('Apply', id='filter-apply-confirm', n_clicks=0,
                            style={'marginLeft': '8px'}),
            ], style={'textAlign': 'right'}),
        ], style={'backgroundColor': 'white', 'padding': '20px 24px',
                  'borderRadius': '8px', 'width': '320px', 'minHeight': '350px',
                  'fontFamily': 'system-ui, sans-serif',
                  'boxShadow': '0 4px 20px rgba(0,0,0,0.25)'}),
    )

    # Pass/Fail examination result shown between the spectrum graph and the
    # peak data table. None -> nothing; "Pass" -> green; "Fail" -> red + msg.
    if exam_out == "Pass":
        exam_div = html.Div(
            [html.Span("Pass, ", style={'fontWeight': 'bold'})]
            + ([html.Span(f"{exam_msg}")] if exam_msg else []),
            style={'color': 'green', 'fontSize': '18px', 'margin': '5px 0', 'marginLeft': TABLE_LEFT_MARGIN, 'fontFamily': 'system-ui, sans-serif'})
    elif exam_out == "Fail":
        exam_div = html.Div(
            [html.Span("Fail, ", style={'fontWeight': 'bold'})]
            + ([html.Span(f"{exam_msg}")] if exam_msg else []),
            style={'color': 'red', 'fontSize': '18px', 'margin': '5px 0', 'marginLeft': TABLE_LEFT_MARGIN, 'fontFamily': 'system-ui, sans-serif'})
    else:
        exam_div = None

    app.layout = html.Div([
        top_navbar,
        html.Div([
            html.Div([
                dcc.Graph(id='spectrum', figure=initial_fig, config={'scrollZoom':True}),
                # Delta-markers table and the custom table sit side by side.
                html.Div([
                    html.Div(id='marker-info'),
                    html.Div(id='custom-table-container', style={'display': 'none'}, children=[
                        html.Div('Custom Peak', style=TABLE_TITLE_STYLE),
                        dash_table.DataTable(
                            id='custom-table',
                            columns=[{'name': 'Peak No.' if c == 'Peak' else c, 'id': c} for c in
                                     ['Ch', 'Peak', 'x', 'y', 'Depth', 'Bandwidth', 'base_x', 'base_y']],
                            data=[{'Ch': channels[0], 'Peak': 'custom', 'x': '', 'y': '', 'Depth': '',
                                   'Bandwidth': '', 'base_x': '', 'base_y': ''}],
                            style_cell=TABLE_CELL_STYLE,
                            style_as_list_view=True,
                            style_header=TABLE_HEADER_STYLE,
                            style_table=TABLE_STYLE,
                        ),
                    ]),
                ], style={'display': 'flex', 'alignItems': 'flex-start', 'gap': '30px', 'marginTop': '5px'}),
                html.Div(id='peak-table-container', children=[exam_div, html.Div('Peaks (auto-detected)', style=TABLE_TITLE_STYLE), dash_table.DataTable(
                    data=peak_df.to_dict('records'),
                    columns=[
                        {'name': 'Peak No.', 'id': 'Peak_disp'}
                        if c == 'Peak' else {'name': c, 'id': c}
                        for c in peak_df.columns if c != 'Peak_disp'],
                    style_cell=TABLE_CELL_STYLE,
                    style_as_list_view=True,
                    style_header=TABLE_HEADER_STYLE,
                    style_table=TABLE_STYLE,
                    style_data_conditional=([{
                        'if': {'filter_query': '{{Depth_max}} >= {}'.format(peak_df['Depth_max'].max())},
                        'backgroundColor': '#FFF3B0',
                        # 'fontWeight': 'bold',
                    }] + ([{
                        # Listed after the max-depth rule so it takes precedence on overlap.
                        'if': {'filter_query': '{{Peak}} = {}'.format(exam_idx)},
                        'backgroundColor': '#ADD8E6',
                        # 'fontWeight': 'bold',
                    }] if exam_idx is not None else [])) if pk is not None else [],
                )]) if pk is not None else None,
            ]),
            right_sidebar,
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),
        dcc.Store(id='markers-store', data=[]),
        dcc.Store(id='mode2-anchor-store', data=None),
        dcc.Store(id='mode2-info-store', data=None),
        dcc.Store(id='idle-store', data=None),
        dcc.Interval(id='idle-check', interval=shutdown.IDLE_POLL_MS, n_intervals=0),
        html.Div(id='idle-shutdown-dummy', style={'display': 'none'}),
        peak_modal,
        filter_modal,
    ])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output('save-raw-info', 'children'),
        Input('save-raw-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def save_raw(n_clicks):
        window = _window_holder.get('window')
        if window is None:
            return dash.no_update

        initial_dir = data_path(RAW_DIR)

        result = window.create_file_dialog(
            FileDialog.SAVE,
            directory=os.path.abspath(initial_dir),
            save_filename='raw_data.csv',
            file_types=('CSV files (*.csv)', 'All files (*.*)'),
        )
        if not result:
            return ""
        # SAVE_DIALOG returns a str on some versions, a tuple/list on others.
        file_path = result[0] if isinstance(result, (list, tuple)) else result
        # data/ref are the full-resolution per-channel lists; save_csv_raw pairs
        # them with params.channel to label columns Ch.<n> / Ch.<n>(Ref).
        save_csv_raw(raw_w, params=params, file_path=file_path)
        return "Raw data saved."

    @app.callback(
        Output('plot-watt-info', 'children'),
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
            xaxis_title=dict(text='<b>Wavelength (nm)</b>', font=dict(size=12), standoff=5),
            yaxis_title=dict(text=f'<b>Power ({watt_s.unit})</b>', font=dict(size=12)),
            hovermode='closest', showlegend=True,
            legend=dict(x=1.0, xanchor='left'),
            height=750, width=1450, margin=dict(l=55, t=30, b=40),
        )
        fig.update_xaxes(tickformat='.8~f', hoverformat='.12~f', showspikes=True,
                         spikecolor='gray', spikemode='across', spikethickness=1)
        fig.update_yaxes(showspikes=True, spikemode='across',
                         spikecolor='gray', spikethickness=1)

        # Self-contained HTML (plotly.js inlined) so it opens offline / in the
        # packaged build. Fixed path in the temp dir — reused across clicks.
        html_path = os.path.join(tempfile.gettempdir(), 'wavelength_watt_plot.html')
        fig.write_html(html_path, include_plotlyjs=True, config={'scrollZoom': True})

        webview.create_window(
            f'{title} — Watt', html_path,
            width=1250, height=700, maximized=True,
        )
        return "Watt window opened."

    @app.callback(
        Output('repeat-keybind-dummy', 'children'),
        Input('repeat-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def on_repeat(n_clicks):
        # Remember the request, then close the window. webview.start() returns,
        # the function below shuts the server down, and display_plot() returns
        # _repeat['flag'] to the caller (main_sweep), which auto-Runs next loop.
        _repeat['flag'] = True
        window = _window_holder.get('window')
        if window is not None:
            window.destroy()
        return dash.no_update

    # Enter triggers Repeat — but only when focus isn't in a text/number field
    # or open dropdown, so typing a label/temperature and pressing Enter there
    # doesn't fire it. Installed once via a document-level keydown listener.
    app.clientside_callback(
        """
        function(n) {
            if (!window._repeatKeyBound) {
                window._repeatKeyBound = true;
                document.addEventListener('keydown', function(e) {
                    if (e.key !== 'Enter') return;
                    var t = e.target;
                    var tag = t && t.tagName ? t.tagName.toUpperCase() : '';
                    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
                    if (t && t.closest && t.closest('.Select')) return;  // dcc.Dropdown
                    var btn = document.getElementById('repeat-btn');
                    if (btn) btn.click();
                });
            }
            return '';
        }
        """,
        Output('repeat-btn', 'title'),
        Input('repeat-btn', 'n_clicks'),
    )

    # 'p' opens "Save peak info..." — same focus guard as Enter (skipped while
    # typing in an input/textarea/select or an open dropdown), and ignored when
    # a modifier is held so e.g. Cmd/Ctrl+P (print) still works.
    app.clientside_callback(
        """
        function(n) {
            if (!window._peakKeyBound) {
                window._peakKeyBound = true;
                document.addEventListener('keydown', function(e) {
                    if (e.key !== 'p' && e.key !== 'P') return;
                    if (e.metaKey || e.ctrlKey || e.altKey) return;
                    var t = e.target;
                    var tag = t && t.tagName ? t.tagName.toUpperCase() : '';
                    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
                    if (t && t.closest && t.closest('.Select')) return;  // dcc.Dropdown
                    var btn = document.getElementById('save-peak-btn');
                    if (btn) btn.click();
                });
            }
            return '';
        }
        """,
        Output('save-peak-btn', 'title'),
        Input('save-peak-btn', 'n_clicks'),
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

    @app.callback(
        Output('peak-modal', 'style'),
        Output('peak-file-select', 'options'),
        Output('peak-file-select', 'value'),
        Input('save-peak-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def open_peak_modal(n_clicks):
        opts = _peak_file_options()
        return MODAL_SHOWN, opts, _remembered_file_value(opts)

    @app.callback(
        Output('peak-wavelength', 'value'),
        Output('peak-depth', 'value'),
        Output('peak-width', 'value'),
        Input('peak-select', 'value'),
        # Also recompute when the modal is (re)opened: the dropdown retains its
        # value across openings, so a selection that hasn't changed (e.g. a
        # 'custom' peak that was edited in the meantime) would otherwise keep
        # showing stale stats until the user switches selection and back.
        Input('save-peak-btn', 'n_clicks'),
        State('mode2-info-store', 'data'),
        State('markers-store', 'data'),
    )
    def update_peak_stats(sel, _n_clicks, m2, markers):
        wl_v, depth, fwhm = _peak_stats(sel, m2, markers)
        return _fmt_stat(wl_v, 7), _fmt_stat(depth, 5), _fmt_stat(fwhm, 3)

    @app.callback(
        Output('peak-modal', 'style', allow_duplicate=True),
        Output('save-peak-info', 'children'),
        Output('peak-modal-error', 'children'),
        Input('peak-cancel', 'n_clicks'),
        Input('peak-save-confirm', 'n_clicks'),
        State('peak-select', 'value'),
        State('peak-label', 'value'),
        State('peak-loss', 'value'),
        State('peak-temperature', 'value'),
        State('peak-file-select', 'value'),
        State('mode2-info-store', 'data'),
        State('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def close_or_save_peak(cancel, confirm, sel, label, loss, temperature, chosen_file, m2, markers):
        triggered = callback_context.triggered[0]['prop_id']
        if 'peak-cancel' in triggered:
            return MODAL_HIDDEN, dash.no_update, ""

        if not label or not label.strip():
            return dash.no_update, dash.no_update, "Please enter a label."

        if sel == 'custom':
            if m2 is None or not markers:
                return (dash.no_update, dash.no_update,
                        "Custom peak needs a Mode 2 marker and a Mode 1 base marker.")
            wl_v  = m2['x']
            depth = m2['y'] - markers[-1]['y']
            fwhm  = m2.get('width_pm')
        else:
            i     = int(sel.split(':')[1])
            row   = peak_df[peak_df['Peak'] == i].iloc[0]
            wl_v  = float(row['x'])
            depth = float(row['Depth_max'])
            fwhm  = float(row['FWHM_max'])

        window = _window_holder.get('window')
        if window is None:
            return dash.no_update, dash.no_update, "Window not ready."

        if chosen_file:
            # User picked an existing file — save directly, skip the dialog.
            file_path = os.path.join(os.path.abspath(PEAKS_DIR), chosen_file)
        else:
            result = window.create_file_dialog(
                FileDialog.SAVE,
                directory=os.path.abspath(PEAKS_DIR),
                save_filename=DEFAULT_PEAK_FILENAME,
                file_types=('CSV files (*.csv)', 'All files (*.*)'),
            )
            if not result:
                # User cancelled the file dialog — keep the modal open.
                return dash.no_update, dash.no_update, ""
            file_path = result[0] if isinstance(result, (list, tuple)) else result

        save_csv_peak_row(label.strip(), wl_v, depth, fwhm, loss=loss, file_path=file_path, temperature=temperature, date=params.date)
        
        global _last_peak_file, _last_peak_label, _last_temperature
        _last_peak_file   = os.path.basename(file_path)
        _last_peak_label  = label
        _last_temperature = temperature
        return MODAL_HIDDEN, "Peak data saved.", ""

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
    # selected filter, hiding the second input for single-parameter filters.
    @app.callback(
        Output('param1-label', 'children'),
        Output('param1-input', 'value'),
        Output('param2-label', 'children'),
        Output('param2-input', 'value'),
        Output('param2-row', 'style'),
        Input('filter-select', 'value'),
    )
    def update_filter_params(filt):
        specs = FILTER_PARAMS.get(filt, [])
        if not specs:
            return (dash.no_update,) * 5
        label1, default1 = specs[0]
        if len(specs) > 1:
            label2, default2 = specs[1]
            return label1, default1, label2, default2, {}
        return label1, default1, dash.no_update, dash.no_update, {'display': 'none'}

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

    @app.callback(
        Output('markers-store', 'data'),
        Output('mode2-anchor-store', 'data', allow_duplicate=True),
        Input('spectrum', 'clickData'),
        Input('clear-btn', 'n_clicks'),
        State('markers-store', 'data'),
        State('click-mode', 'value'),
        prevent_initial_call=True,
    )
    def update_markers(clickData, n_clicks, markers, click_mode):
        triggered = callback_context.triggered[0]['prop_id']
        if 'clear-btn' in triggered:
            return [], None
        if clickData and click_mode == 1:
            pt = clickData['points'][0]
            markers.append({'x': pt['x'], 'y': pt['y']})
        return markers, dash.no_update

    @app.callback(
        Output('mode2-anchor-store', 'data'),
        Output('mode2-slider', 'value'),
        Input('spectrum', 'clickData'),
        State('click-mode', 'value'),
        prevent_initial_call=True,
    )
    def update_mode2_anchor(clickData, click_mode):
        if clickData and click_mode == 2:
            # Only the click's x-coordinate matters: Bandwidth is always measured
            # on the first main spectrum (dbm / channels[0]), so the clicked
            # curve's y is intentionally ignored. With several overlapping spectra
            # (multi-channel, reference, scans) this keeps the marker pinned to the
            # first spectrum no matter which line happened to register the click.
            return {'x': clickData['points'][0]['x']}, 0
        return dash.no_update, dash.no_update

    @app.callback(
        Output('spectrum', 'figure'),
        Output('marker-info', 'children'),
        Input('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def redraw_markers(markers):
        patched = Patch()
        xs = [m['x'] for m in markers]
        ys = [m['y'] for m in markers]
        patched['data'][1]['x']    = xs
        patched['data'][1]['y']    = ys
        patched['data'][1]['text'] = [f'M{i+1}' for i in range(len(markers))]

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

        # Delta Markers table, shown only when markers exist (empty markers
        # — e.g. after Clear — leaves marker-info blank). Delta columns are
        # blank for the first marker (nothing to difference against).
        if not markers:
            return patched, None

        rows = []
        for i, m in enumerate(markers):
            # First marker differences against the origin (0, 0); subsequent
            # markers difference against the previous marker.
            prev = markers[i - 1] if i > 0 else {'x': 0.0, 'y': 0.0}
            dl = m['x'] - prev['x']
            dp = m['y'] - prev['y']
            slope_str = "∞ (vertical)" if dl == 0 else f"{(dp / dl)*-1:+.1f}"
            # Midpoint (average) with the previous marker; blank for the first,
            # which has no previous marker to average against.
            mid_x = f"{(m['x'] + prev['x']) / 2:.3f}"
            mid_y = f"{(m['y'] + prev['y']) / 2:.3f}"
            rows.append({
                'Marker': f'M{i+1}',
                'x': f"{m['x']:.3f}", 'y': f"{m['y']:.3f}",
                'mid x': mid_x, 'mid y': mid_y,
                '|Δx|': f"{abs(dl):.3f}", '|Δy|': f"{abs(dp):.3f}",
                'slope': slope_str,
            })

        columns = ['Marker', 'x', 'y', 'mid x', 'mid y', '|Δx|', '|Δy|', 'slope']
        table = dash_table.DataTable(
            data=rows[::-1],  # newest marker on top
            columns=[{'name': c, 'id': c} for c in columns],
            style_cell=TABLE_CELL_STYLE,
            style_as_list_view=True,
            style_header=TABLE_HEADER_STYLE,
            style_table=TABLE_STYLE,
        )
        return patched, [html.Div('Delta Markers', style=TABLE_TITLE_STYLE), table]
    
    @app.callback(
        Output('mode2-slider', 'min'),
        Output('mode2-slider', 'max'),
        Output('mode2-slider', 'value', allow_duplicate=True),
        Input('slider-range-input', 'value'),
        prevent_initial_call=True,
    )
    def update_slider_range(range_pm):
        if not range_pm:
            return dash.no_update, dash.no_update, dash.no_update
        r = range_pm / 1000
        return -r, r, 0

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Output('mode2-marker-info', 'children'),
        Output('mode2-offset-info', 'children'),
        Output('mode2-info-store', 'data'),
        Input('mode2-anchor-store', 'data'),
        Input('mode2-slider', 'value'),
        Input('mode2-offset-input', 'value'),
        Input('mode2-search-range-input', 'value'),
        prevent_initial_call=True,
    )
    def update_mode2_markers(anchor, slider_val, y_offset, search_range_pm):
        patched = Patch()
        if anchor is None:
            for i in (2, 3, 4):
                patched['data'][i]['x'] = []
                patched['data'][i]['y'] = []
                patched['data'][i]['text'] = []
            return patched, "", "", None
        x_target = anchor['x'] + (slider_val or 0)
        i = np.searchsorted(wl, x_target)
        i = np.clip(i, 1, len(wl) - 1)
        idx = i if abs(wl[i] - x_target) < abs(wl[i-1] - x_target) else i - 1
        x, y = float(wl[idx]), float(dbm[idx])
        patched['data'][2]['x'] = [x]
        patched['data'][2]['y'] = [y]
        patched['data'][2]['text'] = [f'({x:.7f}, {y:.5f})']
        if y_offset:
            search_range = int(search_range_pm/(d_x*1000))
            left_nm, right_nm, width_pm = find_bandwidth(wl, dbm, idx, y_offset, search_range)
            # Clip the search-edge indices: near the spectrum ends idx-search_range
            # can go negative (numpy would wrap to the far end) and idx+search_range
            # can run past len(dbm) (IndexError). Clamp to valid bounds.
            i_left  = max(0, idx - search_range)
            i_right = min(len(dbm) - 1, idx + search_range)
            patched['data'][3]['x'] = [float(left_nm)]
            patched['data'][3]['y'] = [max(dbm[i_left], y - y_offset)]
            patched['data'][3]['text'] = ['L']
            patched['data'][4]['x'] = [float(right_nm)]
            patched['data'][4]['y'] = [max(dbm[i_right], y - y_offset)]
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
            width_pm = None
        offset = slider_val or 0
        info = {'x': x, 'y': y, 'width_pm': width_pm}
        return patched, f"Marker:{x:.7f} nm\n       {y:.5f} dBm\n", width_info, info

    @app.callback(
        Output('custom-table', 'data'),
        Output('custom-table-container', 'style'),
        Input('mode2-info-store', 'data'),
        Input('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def update_custom_table(m2, markers):
        # Only show the custom table once a mode-2 marker (data[2]) exists.
        if m2 is None:
            return dash.no_update, {'display': 'none'}
        row = {'Ch': channels[0], 'Peak': 'custom', 'x': '', 'y': '', 'Depth': '', 'Bandwidth': '', 'base_x': '', 'base_y': ''}
        row['x'] = f"{m2['x']:.7f}"
        row['y'] = f"{m2['y']:.5f}"
        if m2.get('width_pm') is not None:
            row['Bandwidth'] = f"{m2['width_pm']:.3f}"
        if markers:
            base = markers[-1]
            row['base_x'] = f"{base['x']:.7f}"
            row['base_y'] = f"{base['y']:.5f}"
            row['Depth'] = f"{m2['y'] - markers[-1]['y']:.5f}"
        return [row], {'display': 'block'}

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

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Input('spectrum', 'relayoutData'),
        State('max-display-input', 'value'),
        prevent_initial_call=True,
    )
    def resample_on_zoom(relayout, max_display):
        if not relayout:
            return dash.no_update

        # --- restore the inverted y-axis on Reset axes / autoscale -------
        # autorange='reversed' only holds while the axis is auto-ranging.
        # Right-click pan drops the reversal (and uirevision locks the
        # un-inverted view in), but we leave that alone — clicking the
        # modebar's "Reset axes"/"Autoscale" button (which emits
        # yaxis.autorange=True) is what puts the inversion back.
        # Disabled: right-drag pan is now blocked at the DOM level (see the
        # index_string script), so the y-axis can no longer be un-inverted and
        # this reset-axes correction is unnecessary.
        # y_fix = 'reversed' if relayout.get('yaxis.autorange') else None

        # --- x resample over the visible window --------------------------
        patched = dash.no_update
        if relayout.get('xaxis.autorange') or relayout.get('autosize'):
            patched = _resample_curves(max_display)
        elif 'xaxis.range[0]' in relayout:
            patched = _resample_curves(max_display, relayout['xaxis.range[0]'], relayout['xaxis.range[1]'])

        # if y_fix is not None:
        #     if patched is dash.no_update:
        #         patched = Patch()
        #     patched['layout']['yaxis']['autorange'] = y_fix

        return patched

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

    if pk is not None:
        _ALL_MARKERS = ['peaks', 'max', 'avg', 'min', 'table'] + (['il'] if il_idx is not None else [])

        @app.callback(
            Output('fwhm-dropdown', 'value'),
            Output('fwhm-all', 'value'),
            Input('fwhm-dropdown', 'value'),
            Input('fwhm-all', 'value'),
            prevent_initial_call=True,
        )
        def sync_all_checkbox(items, all_val):
            triggered = callback_context.triggered[0]['prop_id']
            if 'fwhm-all' in triggered:
                items = _ALL_MARKERS if all_val else []
            else:
                all_val = ['all'] if set(items or []) == set(_ALL_MARKERS) else []
            return items, all_val

        @app.callback(
            Output('spectrum', 'figure', allow_duplicate=True),
            Input('fwhm-dropdown', 'value'),
            prevent_initial_call=True,
        )
        def update_fwhm_visibility(value):
            value = value or []
            show_peaks = 'peaks' in value if 'peaks' in value else 'legendonly'
            show_max = 'max' in value if 'max' in value else 'legendonly'
            show_avg = 'avg' in value if 'avg' in value else 'legendonly'
            show_min = 'min' in value if 'min' in value else 'legendonly'
            patched = Patch()
            # Indices shifted +3 (data[2..4] are mode-2 traces). Each FWHM tier
            # is a single merged Left+Right trace.
            patched['data'][5]['visible'] = show_peaks   # Peaks
            patched['data'][6]['visible'] = show_peaks   # Bases:Left
            patched['data'][7]['visible'] = show_peaks   # Bases:Right
            patched['data'][8]['visible'] = show_max     # FWHM_max
            patched['data'][9]['visible'] = show_avg     # FWHM_avg
            patched['data'][10]['visible'] = show_min    # FWHM_min
            if il_idx is not None:
                patched['data'][il_idx]['visible'] = 'il' in value if 'il' in value else 'legendonly'
            return patched

        @app.callback(
            Output('peak-table-container', 'style'),
            Input('fwhm-dropdown', 'value'),
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
    _window_holder['window'] = window
    try:
        webview.start()
    finally:
        server.shutdown()
        thread.join()

    # True when the user clicked Repeat (or pressed Enter); the caller uses this
    # to auto-Run the next sweep. False on a normal window close.
    return _repeat['flag']


# ---------------------------------------------------------------------------
# Demo: run this file directly to test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from open_csv import plot_raw
    csv_path = "Raw Data/hc13n_watt_reference.csv"
    plot_raw(csv_path)
    