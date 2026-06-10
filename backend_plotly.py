import threading
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, dash_table, Input, Output, State, Patch, callback_context
import webview
from webview import FileDialog

from structs import PeakInfo, Params
from analyze_data import peak_detection, find_bandwidth
from save_csv import save_csv_raw, save_csv_peak_row
from helper_plotly import lttb

# Remembered across display_plot() calls (i.e. across loop iterations) so the
# "Choose a file" dropdown can pre-select the file used last time.
_last_peak_file   = ''
_last_peak_label  = ''
_last_temperature = None

def display_plot(data, params: Params = None, *, overlays=None,
                  title="Absorption Spectrum",
                  width=1400, height=1000, port=8050):
    """
    Parameters
    ----------
    data : sequence
        Primary spectrum: ``data[0]`` is the wavelength array (nm) and
        ``data[1]`` the power array (dBm). All peak/marker analysis runs
        on this spectrum.
    overlays : list, optional
        Additional spectra to draw on top, each an ``(wl, dbm)`` or
        ``(wl, dbm, label)`` tuple. These are display-only — peak
        detection, FWHM and the bandwidth tools ignore them.
    width, height : int, optional
        Initial dimensions of the desktop window in pixels.
    port : int, optional
        Deprecated / ignored. The Dash server now binds an OS-assigned
        ephemeral port on each call to avoid stale-server races; kept only
        for backward-compatible call sites.

    Notes
    -----
    This call is BLOCKING — control does not return to the caller until
    the user closes the window. It must be called from the main thread
    (a pywebview requirement).
    """
    wl  = data[0]
    dbm = data[1]
    d_x = round(wl[1] - wl[0], 7)
    
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
    MAX_DISPLAY  = 20000  # max points rendered at once for the spectrum

    # ------------------------------------------------------------------
    # Initial figure (built once, captures the data)
    # ------------------------------------------------------------------
    wl_init, dbm_init = lttb(wl, dbm, MAX_DISPLAY)
    initial_fig = go.Figure()
    # data[0] — main spectrum. SVG scatter (not scattergl): WebGL partial
    # Patch updates on this line trace occasionally fail to repaint, leaving
    # a blank/stale curve after a zoom. At <=MAX_DISPLAY points SVG is fine.
    initial_fig.add_scatter(
        x=wl_init, y=dbm_init, mode='lines', name='Spectrum',
        line=dict(color='#378ADD', width=2),
        hovertemplate='%{x:.7f}<br>%{y:.5f}<extra></extra>',
    )
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
        x=[], y=[], mode='markers', name='Bandwidth',
        marker=dict(symbol='x', size=11, color='#E8A020', line=_border),
        text=[], textposition='top left',
    )
    # data[3] — mode-2 left offset marker
    initial_fig.add_scatter(
        x=[], y=[], mode='markers', name='Bandwidth:Left',
        marker=dict(symbol='triangle-right', size=10, color='#50C878', line=_border),
        text=[], textposition='top center',
    )
    # data[4] — mode-2 right offset marker
    initial_fig.add_scatter(
        x=[], y=[], mode='markers', name='Bandwidth:Right',
        marker=dict(symbol='triangle-left', size=10, color='#50C878', line=_border),
        text=[], textposition='top center',
    )
    
    pk = peak_detection(data)
    if pk is not None:

        # data[3..9] — peak annotation traces (shifted +1 due to mode-2 trace)
        initial_fig.add_scatter(x=pk.peaks.wl, y=dbm[pk.peaks.idx], mode='markers+text', name='Peaks', marker=dict(size=8, color='#E63946', symbol='circle', line=_border))
        
        initial_fig.add_scatter(x=wl[pk.peaks.lt_idx], y=dbm[pk.peaks.lt_idx], mode='markers+text', name='Bases:Left', marker=dict(size=8, color='#2A9D8F', symbol='triangle-up', line=_border), text=[f"L:({x:.3f}, {y:.3f})" for x, y in zip(wl[pk.peaks.lt_idx], dbm[pk.peaks.lt_idx])], textposition='top right')

        initial_fig.add_scatter(x=wl[pk.peaks.rt_idx], y=dbm[pk.peaks.rt_idx], mode='markers+text', name='Bases:Right', marker=dict(size=8, color='#2A9D8F', symbol='triangle-down', line=_border), text=[f"R:({x:.3f}, {y:.3f})" for x, y in zip(wl[pk.peaks.rt_idx], dbm[pk.peaks.rt_idx])], textposition='top left')
        
        initial_fig.add_scatter(x=pk.max_fwhm.lt, y=pk.max_fwhm.dbm, mode='markers', name="FWHM_max:Left", visible=True, marker=dict(size=8, color='#F4A261', symbol='square', line=_border))
        
        initial_fig.add_scatter(x=pk.max_fwhm.rt, y=pk.max_fwhm.dbm, mode='markers', name="FWHM_max:Right", visible=True, marker=dict(size=8, color='#F4A261', symbol='square', line=_border))
        
        initial_fig.add_scatter(x=pk.avg_fwhm.lt, y=pk.avg_fwhm.dbm, mode='markers', name="FWHM_avg:Left", visible=True, marker=dict(size=8, color='#457B9D', symbol='diamond', line=_border))
        
        initial_fig.add_scatter(x=pk.avg_fwhm.rt, y=pk.avg_fwhm.dbm, mode='markers', name="FWHM_avg:Right", visible=True, marker=dict(size=8, color='#457B9D', symbol='diamond', line=_border))

        
        peak_dict = {
            "x"           : np.round(pk.peaks.wl, decimals=6),
            "y"           : np.round(dbm[pk.peaks.idx], decimals=5),
            "Depth_max"   : np.round(pk.peaks.max_depths, decimals=5),
            "FWHM_max"    : [round(w, 3) for w in pk.max_fwhm.width],
            "Depth_avg"   : np.round(pk.peaks.avg_depths, decimals=5),
            "FWHM_avg"    : [round(w, 3) for w in pk.avg_fwhm.width],
            # "Left_base_x" : np.round(wl[pk.peaks.lt_idx], decimals=6),
            # "Left_base_y" : np.round(dbm[pk.peaks.lt_idx], decimals=5),
            # "Right_base_x": np.round(wl[pk.peaks.rt_idx], decimals=6),
            # "Right_base_y": np.round(dbm[pk.peaks.rt_idx], decimals=5)
                     }
        
        peak_df = pd.DataFrame(peak_dict)
        peak_df.insert(0, "Peak", [i+1 for i in range(len(peak_df))])

    # ------------------------------------------------------------------
    # Overlay spectra (display-only). Appended AFTER every other trace so
    # the hard-coded indices used by the marker/peak callbacks (data[0..11])
    # stay put. overlay_start is the index of the first overlay trace and is
    # reused by resample_on_zoom to refresh them on zoom.
    # ------------------------------------------------------------------
    overlays = list(overlays or [])
    overlay_start = len(initial_fig.data)
    _overlay_colors = ['#9B59B6', '#16A085', '#E67E22', '#34495E', '#C0392B']
    for i, ov in enumerate(overlays):
        ov_wl, ov_dbm = ov[0], ov[1]
        ov_name = ov[2] if len(ov) > 2 else f'Spectrum {i + 2}'
        ov_wl_d, ov_dbm_d = lttb(ov_wl, ov_dbm, MAX_DISPLAY)
        initial_fig.add_scatter(
            x=ov_wl_d, y=ov_dbm_d, mode='lines', name=ov_name,
            line=dict(color=_overlay_colors[i % len(_overlay_colors)], width=2),
            hovertemplate='%{x:.7f}<br>%{y:.5f}<extra></extra>',
            visible='legendonly',
        )

    # ------------------------------------------------------------------
    # Reference sweep: mark the global minimum (deepest dip) with its
    # (x, y) value. Static trace appended last — no callback references it.
    # ------------------------------------------------------------------
    gmin_idx = int(np.argmin(dbm))
    gmin_x, gmin_y = float(wl[gmin_idx]), float(dbm[gmin_idx])
    if params is not None and params.sweep_type == "reference":
        initial_fig.add_scatter(
            x=[gmin_x], y=[gmin_y], mode='markers+text', name='I.L.',
            marker=dict(symbol='star', size=12, color='#C0392B', line=_border),
            # text=[f'({gmin_x:.6f}, {gmin_y:.5f})'], textposition='top center',
            hovertemplate='%{x:.7f}<br>%{y:.5f}<extra>I.L.</extra>',
        )

    initial_fig.update_layout(
        xaxis_title='Wavelength (nm)',
        yaxis_title='Power (dBm)',
        hovermode='closest',
        showlegend=True,
        height=600,
        width=1250,
        margin=dict(t=30, b=5),
        uirevision='constant',
    )

    initial_fig.update_yaxes(autorange='reversed')
    initial_fig.update_xaxes(tickformat='.3f', hoverformat='.5f')
    initial_fig.update_xaxes(showspikes=True, spikecolor="gray", spikemode="across", spikethickness=1)
    initial_fig.update_yaxes(showspikes=True, spikemode="across", spikecolor="gray", spikethickness=1)

    # ------------------------------------------------------------------
    # Dash app
    # ------------------------------------------------------------------
    # Holder so callbacks (running on the server thread) can reach the
    # pywebview window, which is only created later in this function.
    _window_holder = {}

    app = dash.Dash(__name__)
    right_sidebar = html.Div([
        html.Details([
            html.Summary("Show markers", style={'fontWeight': 'bold', 'cursor': 'pointer', 'marginBottom': '6px'}),
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
                    {'label': 'FWHM_max',  'value': 'max'},
                    {'label': 'FWHM_avg',  'value': 'avg'},
                ],
                value=['peaks', 'max', 'avg'],
                style={'marginBottom': '4px', 'marginLeft': '16px'},
                labelStyle={'display': 'block'},
            ),
        ], open=True) if pk is not None else None,
        html.Div([
            html.Label("Click Mode", style={'fontWeight': 'bold', 'marginBottom': '6px', 'display': 'block'}),
            dcc.RadioItems(
                id='click-mode',
                options=[{'label': 'Delta', 'value': 1}, {'label': 'Bandwidth', 'value': 2}],
                value=1,
                inline=True,
                labelStyle={'display': 'inline-block', 'marginRight': '16px'},
                style={'display': 'inline-block'},
            ),
            html.Div([
                html.Label("Fine tune", style={'fontSize': '11px', 'color': '#888',
                                               'marginBottom': '4px', 'display': 'block'}),
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
                html.Label("Slider range (pm)", style={'fontSize': '11px', 'color': '#888',
                                                'marginTop': '6px', 'marginBottom': '4px',
                                                'display': 'block'}),
                dcc.Input(
                    id='slider-range-input',
                    type='number', step='any', value=SLIDER_RANGE * 1000,
                    debounce=True,
                    style={'width': '100%', 'boxSizing': 'border-box'},
                ),
                html.Div(id='mode2-marker-info',
                         style={'display': 'none'}),
                html.Label("Bandwidth amplitude", style={'fontSize': '11px', 'color': '#888',
                                                      'marginTop': '12px', 'marginBottom': '4px',
                                                      'display': 'block'}),
                dcc.Input(
                    id='mode2-offset-input',
                    type='number', step='any',
                    value=1,
                    debounce=True,
                    style={'width': '100%', 'boxSizing': 'border-box'},
                ),
                html.Div(id='mode2-offset-info',
                         style={'display': 'none'}),
                html.Label("Search range (pm)", style={'fontSize': '11px', 'color': '#888',
                                                  'marginTop': '12px', 'marginBottom': '4px',
                                                  'display': 'block'}),
                dcc.Input(
                    id='mode2-search-range-input',
                    type='number', step=5,
                    value=OFFSET_RANGE,
                    debounce=True,
                    style={'width': '100%', 'boxSizing': 'border-box'},
                ),
            ], style={'marginTop': '10px', 'width': '160px'}),
        ]),
        html.Div([
            html.Button('Save raw data...', id='save-raw-btn', n_clicks=0,
                        style={'width': '100%', 'fontSize': '16px',
                               'padding': '10px 12px'}),
            html.Div(id='save-raw-info',
                     style={'fontSize': '12px', 'color': '#888', 'marginTop': '4px'}),
            html.Button('Save peak info...', id='save-peak-btn', n_clicks=0,
                        style={'width': '100%', 'fontSize': '16px',
                               'padding': '10px 12px', 'marginTop': '8px'}),
            html.Div(id='save-peak-info',
                     style={'fontSize': '12px', 'color': '#888', 'marginTop': '4px'}),
        ]),
    ], style={'padding': '20px 10px', 'display': 'flex', 'flexDirection': 'column',
              'gap': '20px', 'fontFamily': 'system-ui, sans-serif'})

    # Shared widths for the first five columns so the peak table and the
    # custom table line up. The two tables use different ids for cols 4-5
    # ("Depth (max)"/"FWHM (max)" vs "Depth"/"Width"), so map per table.
    FIRST5_WIDTHS = ['70px', '110px', '100px', '100px', '100px']

    def _col_widths(col_ids):
        return [{'if': {'column_id': c}, 'width': w, 'minWidth': w, 'maxWidth': w}
                for c, w in zip(col_ids, FIRST5_WIDTHS)]

    peak_col_widths   = _col_widths(['Peak', 'x', 'y', 'Depth (max)', 'FWHM (max)'])
    custom_col_widths = _col_widths(['Peak', 'x', 'y', 'Depth', 'Bandwidth'])

    # ------------------------------------------------------------------
    # "Save peak info" modal — choose a detected peak (or the custom one)
    # and enter a label, then append a row to the fixed Peak Analyses CSV.
    # ------------------------------------------------------------------
    if pk is not None:
        # Put the highlighted peak (max Depth_max, see line ~329) at the top.
        max_peak = int(peak_df.loc[peak_df['Depth_max'].idxmax(), 'Peak'])
        ordered_peaks = [max_peak] + [int(p) for p in peak_df['Peak'] if int(p) != max_peak]
        peak_options = [{'label': f'Peak {p}' + (' (max depth)' if p == max_peak else ''),
                         'value': f'peak:{p}'} for p in ordered_peaks]
    else:
        peak_options = []
    peak_options += [{'label': 'custom', 'value': 'custom'}]

    # Directory where peak CSVs live, and the default filename to fall back on.
    PEAKS_DIR = os.path.join("Test Results", "Peaks")
    DEFAULT_PEAK_FILENAME = '.csv'

    def _peak_file_options():
        """Dropdown options for existing CSVs in PEAKS_DIR, plus an empty item."""
        os.makedirs(PEAKS_DIR, exist_ok=True)
        files = sorted(f for f in os.listdir(PEAKS_DIR)
                       if f.lower().endswith('.csv')
                       and os.path.isfile(os.path.join(PEAKS_DIR, f)))
        opts = [{'label': f'Create a new file', 'value': ''}]
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

    peak_modal = html.Div(
        id='peak-modal',
        style=MODAL_HIDDEN,
        children=html.Div([
            html.H4('Save peak info', style={'marginTop': 0}),
            html.Label('Peak', style={'fontWeight': 'bold', 'display': 'block',
                                      'marginBottom': '4px'}),
            dcc.Dropdown(id='peak-select', options=peak_options,
                         value=peak_options[0]['value'], clearable=False,
                         style={'marginBottom': '12px'}),
            html.Label('Label', style={'fontWeight': 'bold', 'display': 'block',
                                       'marginBottom': '4px'}),
            dcc.Input(id='peak-label', type='text', value=_last_peak_label, debounce=False,
                      style={'width': '100%', 'boxSizing': 'border-box',
                             'marginBottom': '8px'}),
            html.Label('Temperature', style={'fontWeight': 'bold', 'display': 'block',
                                             'marginBottom': '4px'}),
            dcc.Input(id='peak-temperature', type='number', value=_last_temperature, debounce=False,
                      style={'width': '100%', 'boxSizing': 'border-box',
                             'marginBottom': '8px'}),
            html.Label('Choose a file', style={'fontWeight': 'bold', 'display': 'block',
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

    sweep_text = (f'Sweep type: {params.sweep_type}'
                  if params is not None and params.sweep_type else None)

    app.layout = html.Div([
        html.Div(sweep_text,
                 style={'fontWeight': 'bold', 'fontFamily': 'system-ui, sans-serif',
                        'margin': '8px 0 4px 4px'}) if sweep_text else None,
        html.Div([
            dcc.Graph(id='spectrum', figure=initial_fig, config={'scrollZoom':True}),
            right_sidebar,
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),
        dash_table.DataTable(
            data=peak_df.to_dict('records'),
            columns=[{'name': c, 'id': c} for c in peak_df.columns],
            style_cell={'fontFamily': '"Times New Roman", Times, serif', 'padding': '4px 8px', 'textAlign': 'center'},
            style_cell_conditional=peak_col_widths,
            style_as_list_view=True,
            style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'},
            style_table={'marginBottom': '10px', 'width': 'fit-content'},
            style_data_conditional=[{
                'if': {'filter_query': '{{Depth_max}} >= {}'.format(peak_df['Depth_max'].max())},
                'backgroundColor': '#FFF3B0',
                'fontWeight': 'bold',
            }] if pk is not None else [],
        ) if pk is not None else None,
        # html.P(peak_text, style={'whiteSpace': 'pre-wrap'}) if pk is not None else None,
        dash_table.DataTable(
            id='custom-table',
            columns=[{'name': c, 'id': c} for c in
                     ['Peak', 'x', 'y', 'Depth', 'Bandwidth', 'base_x', 'base_y']],
            data=[{'Peak': 'custom', 'x': '', 'y': '', 'Depth': '',
                   'Bandwidth': '', 'base_x': '', 'base_y': ''}],
            style_cell={'fontFamily': '"Times New Roman", Times, serif', 'padding': '4px 8px', 'textAlign': 'center'},
            style_cell_conditional=custom_col_widths,
            style_as_list_view=True,
            style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'},
            style_table={'marginBottom': '10px', 'width': 'fit-content'},
        ),
        html.P(f"Insertion Loss: {gmin_y:.5f}") if params is not None and params.sweep_type == "reference" else None,
        html.Button('Clear markers', id='clear-btn', n_clicks=0),
        html.Div(id='marker-info',
                 style={'marginTop': '10px', 'fontFamily': 'monospace',
                        'whiteSpace': 'pre'}),
        dcc.Store(id='markers-store', data=[]),
        dcc.Store(id='mode2-anchor-store', data=None),
        dcc.Store(id='mode2-info-store', data=None),
        peak_modal,
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

        initial_dir = os.path.join("Test Results", "Raw Data")
        os.makedirs(initial_dir, exist_ok=True)

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
        save_csv_raw(data, params, file_path=file_path)
        return "Raw data saved."

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
        Output('peak-modal', 'style', allow_duplicate=True),
        Output('save-peak-info', 'children'),
        Output('peak-modal-error', 'children'),
        Input('peak-cancel', 'n_clicks'),
        Input('peak-save-confirm', 'n_clicks'),
        State('peak-select', 'value'),
        State('peak-label', 'value'),
        State('peak-temperature', 'value'),
        State('peak-file-select', 'value'),
        State('mode2-info-store', 'data'),
        State('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def close_or_save_peak(cancel, confirm, sel, label, temperature, chosen_file, m2, markers):
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
            i = int(sel.split(':')[1])
            row = peak_df[peak_df['Peak'] == i].iloc[0]
            wl_v  = float(row['x'])
            depth = float(row['Depth_max'])
            fwhm  = float(row['FWHM_max'])

        window = _window_holder.get('window')
        if window is None:
            return dash.no_update, dash.no_update, "Window not ready."

        os.makedirs(PEAKS_DIR, exist_ok=True)
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
            
        if params is not None and params.sweep_type == "reference":
            save_csv_peak_row(label.strip(), wl_v, depth, fwhm, loss=round(gmin_y,5), file_path=file_path, temperature=temperature)
        else:    
            save_csv_peak_row(label.strip(), wl_v, depth, fwhm, file_path=file_path, temperature=temperature)
        
        global _last_peak_file, _last_peak_label, _last_temperature
        _last_peak_file   = os.path.basename(file_path)
        _last_peak_label  = label
        _last_temperature = temperature
        return MODAL_HIDDEN, "Peak data saved.", ""

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
            pt = clickData['points'][0]
            return {'x': pt['x'], 'y': pt['y']}, 0
        return dash.no_update, dash.no_update

    @app.callback(
        Output('spectrum', 'figure'),
        Output('marker-info', 'children'),
        Input('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def redraw_markers(markers):
        patched = Patch()
        patched['data'][1]['x']    = [m['x'] for m in markers]
        patched['data'][1]['y']    = [m['y'] for m in markers]
        patched['data'][1]['text'] = [f'M{i+1}' for i in range(len(markers))]

        rows = []
        for i, m in enumerate(markers):
            base = f"M{i+1}: {m['x']:.7f} nm, {m['y']:.5f} dBm"
            if i == 0:
                rows.append(html.Div(base))
                continue
            prev = markers[i - 1]
            dl = m['x'] - prev['x']
            dp = m['y'] - prev['y']
            if dl == 0:
                slope_str = "∞ (vertical)"
            else:
                slope_str = f"{(dp / dl)*-1:+.5f} dBm/nm"
            deltas = (f"  (|Δx|: {abs(dl):+.7f} nm, "
                      f"|Δy|: {abs(dp):+.5f} dBm, "
                      f"slope: {slope_str})")
            rows.append(html.Div(base + deltas))
        return patched, rows
    
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
        patched['data'][2]['text'] = ['M2']
        if y_offset:
            search_range = int(search_range_pm/(d_x*1000))
            left_nm, right_nm, width_pm = find_bandwidth(wl, dbm, idx, y_offset, search_range)
            patched['data'][3]['x'] = [float(left_nm)]
            patched['data'][3]['y'] = [max(dbm[idx - search_range], y - y_offset)]
            patched['data'][3]['text'] = ['L']
            patched['data'][4]['x'] = [float(right_nm)]
            patched['data'][4]['y'] = [max(dbm[idx + search_range], y - y_offset)]
            patched['data'][4]['text'] = ['R']
            
            width_info = f"width: {width_pm:.4f} pm\n"
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
        # return ""

    @app.callback(
        Output('custom-table', 'data'),
        Input('mode2-info-store', 'data'),
        Input('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def update_custom_table(m2, markers):
        row = {'Peak': 'custom', 'x': '', 'y': '', 'Depth': '',
               'Bandwidth': '', 'base_x': '', 'base_y': ''}
        if m2 is not None:
            row['x'] = f"{m2['x']:.6f}"
            row['y'] = f"{m2['y']:.5f}"
            if m2.get('width_pm') is not None:
                row['Bandwidth'] = f"{m2['width_pm']:.3f}"
        if markers:
            base = markers[-1]
            row['base_x'] = f"{base['x']:.6f}"
            row['base_y'] = f"{base['y']:.5f}"
        if m2 is not None and markers:
            row['Depth'] = f"{m2['y'] - markers[-1]['y']:.5f}"
        return [row]

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Input('spectrum', 'relayoutData'),
        prevent_initial_call=True,
    )
    def resample_on_zoom(relayout):
        if not relayout:
            return dash.no_update
        # (trace index, wl array, dbm array) for the primary spectrum plus
        # every overlay. data[0] is the primary; overlays live at
        # overlay_start.. (see the overlay-building block above).
        curves = [(0, wl, dbm)]
        curves += [(overlay_start + i, ov[0], ov[1])
                   for i, ov in enumerate(overlays)]
        patched = Patch()
        if relayout.get('xaxis.autorange') or relayout.get('autosize'):
            for idx, w_arr, d_arr in curves:
                w_d, d_d = lttb(w_arr, d_arr, MAX_DISPLAY)
                patched['data'][idx]['x'] = w_d
                patched['data'][idx]['y'] = d_d
            return patched
        if 'xaxis.range[0]' not in relayout:
            return dash.no_update
        x0, x1 = relayout['xaxis.range[0]'], relayout['xaxis.range[1]']
        for idx, w_arr, d_arr in curves:
            i0 = max(0, int(np.searchsorted(w_arr, x0)) - 1)
            i1 = min(len(w_arr), int(np.searchsorted(w_arr, x1)) + 1)
            w_d, d_d = lttb(w_arr[i0:i1], d_arr[i0:i1], MAX_DISPLAY)
            patched['data'][idx]['x'] = w_d
            patched['data'][idx]['y'] = d_d
        return patched

    if pk is not None:
        _ALL_MARKERS = ['peaks', 'max', 'avg']

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
            show_peaks = 'peaks' in value
            show_max = 'max' in value
            show_avg = 'avg' in value
            patched = Patch()
            # Indices shifted +3 (data[2..4] are mode-2 traces)
            patched['data'][5]['visible'] = show_peaks   # Peaks
            patched['data'][6]['visible'] = show_peaks   # Bases:Left
            patched['data'][7]['visible'] = show_peaks   # Bases:Right
            patched['data'][8]['visible'] = show_max
            patched['data'][9]['visible'] = show_max
            patched['data'][10]['visible'] = show_avg
            patched['data'][11]['visible'] = show_avg
            return patched

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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    window = webview.create_window(
        title,
        f'http://127.0.0.1:{bound_port}',
        width=width, height=height, maximized=True,
    )
    _window_holder['window'] = window
    try:
        webview.start()
    finally:
        server.shutdown()
        thread.join()


# ---------------------------------------------------------------------------
# Demo: run this file directly to test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    data = np.loadtxt("test_2026-05-11_14-44_converted.csv", skiprows=1, delimiter=',')
    params = Params()
    params.sweep_type = "single"
    while True:
        display_plot((data[:, 0], data[:, 1]), params=params)