import threading
# import contextlib
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, dash_table, Input, Output, State, Patch, callback_context
import webview
from structs import PeakInfo

def plot_plotly(data, pk : PeakInfo = None, *, title="Absorption Spectrum",
                  width=1200, height=1000, port=8050):
    """
    Parameters
    ----------
    width, height : int, optional
        Initial dimensions of the desktop window in pixels.
    port : int, optional
        Local TCP port for the Dash server (default 8050).

    Notes
    -----
    This call is BLOCKING — control does not return to the caller until
    the user closes the window. It must be called from the main thread
    (a pywebview requirement).
    """
    wl  = data[:, 0]
    dbm = data[:, 1]
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

    def lttb(x, y, n_out):
        """Largest-Triangle-Three-Buckets downsampling (pure numpy, no deps)."""
        n = len(x)
        if n <= n_out:
            return x, y
        buckets = np.array_split(np.arange(1, n - 1), n_out - 2)
        out = [0]
        for i, bucket in enumerate(buckets):
            next_b = buckets[i + 1] if i + 1 < len(buckets) else np.array([n - 1])
            a = out[-1]
            c_x = x[next_b].mean()
            c_y = y[next_b].mean()
            areas = np.abs((x[a] - c_x) * (y[bucket] - y[a]) -
                           (x[a] - x[bucket]) * (c_y - y[a]))
            out.append(bucket[np.argmax(areas)])
        out.append(n - 1)
        idx = np.array(out)
        return x[idx], y[idx]

    # ------------------------------------------------------------------
    # Initial figure (built once, captures the data)
    # ------------------------------------------------------------------
    wl_init, dbm_init = lttb(wl, dbm, MAX_DISPLAY)
    initial_fig = go.Figure()
    initial_fig.add_scattergl(
        x=wl_init, y=dbm_init, mode='lines', name='Spectrum',
        line=dict(color='#378ADD', width=2),
        hovertemplate='%{x:.7f}<br>%{y:.5f}<extra></extra>',
    )
    # initial_fig.add_scattergl(
    #     x=wl, y=dbm, mode='lines', name='Spectrum',
    #     line=dict(color='#378ADD', width=2),
    #     hovertemplate='%{x:.7f}<br>%{y:.5f}<extra></extra>',
    # )
    _border = dict(width=1, color='#333')
    # data[1] — mode-1 accumulated markers
    initial_fig.add_scattergl(
        x=[], y=[], mode='markers+text', name='Markers',
        marker=dict(symbol='diamond', size=7, color='#D85A30', line=_border),
        text=[], textposition='top center',
    )
    # data[2] — mode-2 single marker (always replaced)
    initial_fig.add_scattergl(
        x=[], y=[], mode='markers', name='Mode2 Marker',
        marker=dict(symbol='x', size=11, color='#E8A020', line=_border),
        text=[], textposition='top left',
    )
    # data[3] — mode-2 left offset marker
    initial_fig.add_scattergl(
        x=[], y=[], mode='markers', name='Mode2 Left',
        marker=dict(symbol='triangle-right', size=10, color='#50C878', line=_border),
        text=[], textposition='top center',
    )
    # data[4] — mode-2 right offset marker
    initial_fig.add_scattergl(
        x=[], y=[], mode='markers', name='Mode2 Right',
        marker=dict(symbol='triangle-left', size=10, color='#50C878', line=_border),
        text=[], textposition='top center',
    )
    if pk is not None:

        # data[3..9] — peak annotation traces (shifted +1 due to mode-2 trace)
        initial_fig.add_scatter(x=pk.peaks.wl, y=dbm[pk.peaks.idx], mode='markers+text', name='Peaks', marker=dict(size=8, color='#E63946', symbol='circle', line=_border))
        
        initial_fig.add_scatter(x=wl[pk.peaks.lt_idx], y=dbm[pk.peaks.lt_idx], mode='markers', name='Peak bases_Left', marker=dict(size=8, color='#2A9D8F', symbol='triangle-up', line=_border))
        
        initial_fig.add_scatter(x=wl[pk.peaks.rt_idx], y=dbm[pk.peaks.rt_idx], mode='markers', name='Peak bases_Right', marker=dict(size=8, color='#2A9D8F', symbol='triangle-down', line=_border))
        
        initial_fig.add_scatter(x=pk.max_fwhm.lt, y=pk.max_fwhm.dbm, mode='markers', name="FWHM_max_left", visible=True, marker=dict(size=8, color='#F4A261', symbol='square', line=_border))
        
        initial_fig.add_scatter(x=pk.max_fwhm.rt, y=pk.max_fwhm.dbm, mode='markers', name="FWHM_max_right", visible=True, marker=dict(size=8, color='#F4A261', symbol='square', line=_border))
        
        initial_fig.add_scatter(x=pk.avg_fwhm.lt, y=pk.avg_fwhm.dbm, mode='markers', name="FWHM_avg_left", visible=True, marker=dict(size=8, color='#457B9D', symbol='diamond', line=_border))
        
        initial_fig.add_scatter(x=pk.avg_fwhm.rt, y=pk.avg_fwhm.dbm, mode='markers', name="FWHM_avg_right", visible=True, marker=dict(size=8, color='#457B9D', symbol='diamond', line=_border))

        
        peak_dict = {
            "x"               : np.round(pk.peaks.wl, decimals=6),
            "y"               : np.round(dbm[pk.peaks.idx], decimals=6),
            "Depth (max)"     : np.round(pk.peaks.max_depths, decimals=6),
            "Depth (avg)"     : np.round(pk.peaks.avg_depths, decimals=6),
            "Base (left) (x)" : np.round(wl[pk.peaks.lt_idx], decimals=6),
            "Base (left) (y)" : np.round(dbm[pk.peaks.lt_idx], decimals=6),
            "Base (right) (x)": np.round(wl[pk.peaks.rt_idx], decimals=6),
            "Base (right) (y)": np.round(dbm[pk.peaks.rt_idx], decimals=6),
            "FWHM (max)"      : [round(w, 6) for w in pk.max_fwhm.width],
            "FWHM (avg)"      : [round(w, 6) for w in pk.avg_fwhm.width]
                     }
        
        peak_df = pd.DataFrame(peak_dict)
        peak_df.insert(0, "Peak", [i+1 for i in range(len(peak_df))])

    initial_fig.update_layout(
        xaxis_title='Wavelength (nm)',
        yaxis_title='Power (dBm)',
        hovermode='closest',
        showlegend=True,
        height=600,
        width=1200,
        uirevision='constant',
    )

    initial_fig.update_yaxes(autorange='reversed')
    initial_fig.update_xaxes(tickformat='.3f', hoverformat='.5f')
    initial_fig.update_xaxes(showspikes=True, spikecolor="gray", spikemode="across", spikethickness=1)
    initial_fig.update_yaxes(showspikes=True, spikemode="across", spikecolor="gray", spikethickness=1)

    # ------------------------------------------------------------------
    # Dash app
    # ------------------------------------------------------------------
    app = dash.Dash(__name__)
    right_sidebar = html.Div([
        html.Div([
            html.Label("Show FWHM", style={'fontWeight': 'bold', 'marginBottom': '6px', 'display': 'block'}),
            dcc.RadioItems(
                id='fwhm-dropdown',
                options=[
                    {'label': ' off',  'value': 'off'},
                    {'label': ' max',  'value': 'max'},
                    {'label': ' avg',  'value': 'avg'},
                    {'label': ' both', 'value': 'both'},
                ],
                value='both',
                labelStyle={'display': 'block', 'marginBottom': '4px'},
            ),
        ]) if pk is not None else None,
        html.Div([
            html.Label("Click Mode", style={'fontWeight': 'bold', 'marginBottom': '6px', 'display': 'block'}),
            dcc.RadioItems(
                id='click-mode',
                options=[{'label': ' 1', 'value': 1}, {'label': ' 2', 'value': 2}],
                value=1,
                labelStyle={'display': 'block', 'marginBottom': '4px'},
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
                         style={'fontSize': '11px',
                                'marginTop': '8px', 'color': '#E8A020',
                                'whiteSpace': 'pre'}),
                html.Label("Offset in Y-axis", style={'fontSize': '11px', 'color': '#888',
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
                         style={'fontSize': '13px',
                                'marginTop': '6px', 'color': 'black',
                                'whiteSpace': 'pre'}),
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
    ], style={'padding': '20px 10px', 'display': 'flex', 'flexDirection': 'column',
              'gap': '20px', 'fontFamily': 'system-ui, sans-serif'})

    app.layout = html.Div([
        html.Div([
            dcc.Graph(id='spectrum', figure=initial_fig, config={'scrollZoom':True}),
            right_sidebar,
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),
        dash_table.DataTable(
            data=peak_df.to_dict('records'),
            columns=[{'name': c, 'id': c} for c in peak_df.columns],
            style_cell={'fontFamily': '"Times New Roman", Times, serif', 'padding': '4px 8px', 'textAlign': 'left'},
            style_header={'fontWeight': 'bold', 'backgroundColor': '#f0f0f0'},
            style_table={'marginBottom': '10px'},
        ) if pk is not None else None,
        # html.P(peak_text, style={'whiteSpace': 'pre-wrap'}) if pk is not None else None,
        html.Button('Clear markers', id='clear-btn', n_clicks=0),
        html.Div(id='marker-info',
                 style={'marginTop': '10px', 'fontFamily': 'monospace',
                        'whiteSpace': 'pre'}),
        dcc.Store(id='markers-store', data=[]),
        dcc.Store(id='mode2-anchor-store', data=None),
    ])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @app.callback(
        Output('markers-store', 'data'),
        Input('spectrum', 'clickData'),
        Input('clear-btn', 'n_clicks'),
        State('markers-store', 'data'),
        State('click-mode', 'value'),
        prevent_initial_call=True,
    )
    def update_markers(clickData, n_clicks, markers, click_mode):
        triggered = callback_context.triggered[0]['prop_id']
        if 'clear-btn' in triggered:
            return []
        if clickData and click_mode == 1:
            pt = clickData['points'][0]
            markers.append({'x': pt['x'], 'y': pt['y']})
        return markers

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
    
    def find_width_offset(idx, y_offset, search_range):
        height = float(dbm[idx]) - y_offset
        i_min = max(0, idx - search_range)
        i_max = min(len(wl), idx + search_range)
        
        # left side
        i = idx
        while i_min < i and height < float(dbm[i]):
            i -= 1
        left_ip = i
        if dbm[i] < height:
            if dbm[i + 1] != dbm[i]:
                left_ip += (height - dbm[i]) / (dbm[i + 1] - dbm[i])
                
        # right side
        i = idx
        while i < i_max and height < float(dbm[i]):
            i += 1
        right_ip = i
        if dbm[i] < height:
            if dbm[i - 1] != dbm[i]:
                right_ip -= (height - dbm[i]) / (dbm[i - 1] - dbm[i])
        
        width_ip = right_ip - left_ip
        d_x      = round(wl[1] - wl[0], 7)
        
        left_nm  = wl[int(left_ip)] + (left_ip % 1.0) * d_x
        right_nm = wl[int(right_ip)] + (right_ip % 1.0) * d_x
        width_pm = width_ip * d_x * 1000
        
        return left_nm, right_nm, width_pm
    
    @app.callback(
        Output('mode2-slider', 'min'),
        Output('mode2-slider', 'max'),
        Output('mode2-slider', 'value'),
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
            return patched, "", ""
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
            left_nm, right_nm, width_pm = find_width_offset(idx, y_offset, search_range)
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
        offset = slider_val or 0
        return patched, f"Marker:{x:.7f} nm\n       {y:.5f} dBm\n", width_info

    @app.callback(
        Output('spectrum', 'figure', allow_duplicate=True),
        Input('spectrum', 'relayoutData'),
        prevent_initial_call=True,
    )
    def resample_on_zoom(relayout):
        if not relayout:
            return dash.no_update
        patched = Patch()
        if relayout.get('xaxis.autorange') or relayout.get('autosize'):
            wl_d, dbm_d = lttb(wl, dbm, MAX_DISPLAY)
            patched['data'][0]['x'] = wl_d
            patched['data'][0]['y'] = dbm_d
            return patched
        if 'xaxis.range[0]' not in relayout:
            return dash.no_update
        x0, x1 = relayout['xaxis.range[0]'], relayout['xaxis.range[1]']
        i0 = max(0, int(np.searchsorted(wl, x0)) - 1)
        i1 = min(len(wl), int(np.searchsorted(wl, x1)) + 1)
        wl_v, dbm_v = wl[i0:i1], dbm[i0:i1]
        wl_d, dbm_d = lttb(wl_v, dbm_v, MAX_DISPLAY)
        patched['data'][0]['x'] = wl_d
        patched['data'][0]['y'] = dbm_d
        return patched

    if pk is not None:
        @app.callback(
            Output('spectrum', 'figure', allow_duplicate=True),
            Input('fwhm-dropdown', 'value'),
            prevent_initial_call=True,
        )
        def update_fwhm_visibility(value):
            show_max = value in ('max', 'both')
            show_avg = value in ('avg', 'both')
            patched = Patch()
            # Indices shifted +3 (data[2..4] are mode-2 traces)
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

    server = make_server('127.0.0.1', port, app.server, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    webview.create_window(
        title,
        f'http://127.0.0.1:{port}',
        width=width, height=height,
    )
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
    plot_plotly(data)
