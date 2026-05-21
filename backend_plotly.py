import threading
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import dcc, html, Input, Output, State, Patch, callback_context
import webview

# TODO: add peak_info in the plot
def plot_plotly(df, peak_info=None, *, title="Absorption Spectrum",
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
    wl = np.asarray(df["Wavelength"])
    dbm = np.asarray(df["Power"])
    peak_text = ""

    # ------------------------------------------------------------------
    # Initial figure (built once, captures the data)
    # ------------------------------------------------------------------
    initial_fig = go.Figure()
    initial_fig.add_scattergl(
        x=wl, y=dbm, mode='lines', name='Spectrum',
        line=dict(color='#378ADD', width=2),
        hovertemplate='%{x:.7f}<br>%{y:.5f}<extra></extra>',
    )
    initial_fig.add_scatter(
        x=[], y=[], mode='markers+text', name='Markers',
        marker=dict(symbol='diamond', size=7, color='#D85A30'),
        text=[], textposition='top center',
    )
    if peak_info != None:
        peak_indices        = peak_info["peak_indices"]
        peak_depths         = peak_info["peak_depths"]
        peak_left_bases     = peak_info["left_bases"]
        peak_right_bases    = peak_info["right_bases"]
        fwhm_heights        = peak_info["fwhm_heights"]
        fwhm_left_xs        = peak_info["fwhm_left_xs"]
        fwhm_right_xs       = peak_info["fwhm_right_xs"]
        fwhm_widths         = peak_info["fwhm_widths"]
        
        peak_wl = np.take(wl, peak_indices)
        peak_left_wl = np.take(wl, peak_left_bases)
        peak_left_dbm = np.take(dbm, peak_left_bases)
        peak_right_wl = np.take(wl, peak_right_bases)
        peak_right_dbm = np.take(dbm, peak_right_bases)
        
        fwhm_depths = [max(h-l, h-r) for h, l, r in zip(fwhm_heights, peak_left_dbm, peak_right_dbm)]

        initial_fig.add_scatter(x=peak_wl, y=np.take(dbm, peak_indices), mode='markers', name='Peaks')
        initial_fig.add_scatter(x=peak_left_wl, y=peak_left_dbm, mode='markers', name='Peak bases_Left')
        initial_fig.add_scatter(x=peak_right_wl, y=peak_right_dbm, mode='markers', name='Peak bases_Right')
        initial_fig.add_scatter(x=fwhm_left_xs, y=fwhm_heights, mode='markers', name="FWHM_Left")
        initial_fig.add_scatter(x=fwhm_right_xs, y=fwhm_heights, mode='markers', name="FWHM_Right")

        for n, (pw, pd, plw, pld, prw, prd, fw, fd) in enumerate(zip(peak_wl, peak_depths, peak_left_wl, peak_left_dbm, peak_right_wl, peak_right_dbm, fwhm_widths, fwhm_depths), start=1):
            peak_text += f"Peak {n}: Wavelength={pw:.7f} nm, Depth={pd:.4f}, Bases=(left=({plw:.7f}, {pld:.4f}), right=({prw:.7f}, {prd:.4f})) FWHM={fw:.4f} pm (depth={fd:.4f})\n"

    initial_fig.update_layout(
        xaxis_title='Wavelength (nm)',
        yaxis_title='Power (dBm)',
        hovermode='closest',
        showlegend=False,
        height=700,
        width=1200,
    )

    initial_fig.update_yaxes(autorange='reversed')
    initial_fig.update_xaxes(tickformat='.3f', hoverformat='.5f')
    initial_fig.update_xaxes(showspikes=True, spikecolor="gray", spikemode="across", spikethickness=1)
    initial_fig.update_yaxes(showspikes=True, spikemode="across", spikecolor="gray", spikethickness=1)

    # ------------------------------------------------------------------
    # Dash app
    # ------------------------------------------------------------------
    app = dash.Dash(__name__)
    app.layout = html.Div([
        # html.H3(title),
        dcc.Graph(id='spectrum', figure=initial_fig, config={'scrollZoom':True}),
        html.P(peak_text, style={'whiteSpace': 'pre-wrap'}) if peak_info != None else None,
        html.Button('Clear markers', id='clear-btn', n_clicks=0),
        html.Div(id='marker-info',
                 style={'marginTop': '10px', 'fontFamily': 'monospace',
                        'whiteSpace': 'pre'}),
        dcc.Store(id='markers-store', data=[]),
    ])

    @app.callback(
        Output('markers-store', 'data'),
        Input('spectrum', 'clickData'),
        Input('clear-btn', 'n_clicks'),
        State('markers-store', 'data'),
        prevent_initial_call=True,
    )
    def update_markers(clickData, n_clicks, markers):
        triggered = callback_context.triggered[0]['prop_id']
        if 'clear-btn' in triggered:
            return []
        if clickData:
            pt = clickData['points'][0]
            markers.append({'x': pt['x'], 'y': pt['y']})
        return markers

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

    # ------------------------------------------------------------------
    # Launch — Dash in a background thread, webview in main thread
    # ------------------------------------------------------------------
    def _run_dash():
        app.run(host='127.0.0.1', port=port,
                debug=False, use_reloader=False)

    threading.Thread(target=_run_dash, daemon=True).start()
    webview.create_window(
        title,
        f'http://127.0.0.1:{port}',
        width=width, height=height,
    )
    webview.start()


# ---------------------------------------------------------------------------
# Demo: run this file directly to test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    df = pd.read_csv("test_2026-05-11_14-44_converted.csv")
    plot_plotly(df)