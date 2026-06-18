# -*- mode: python ; coding: utf-8 -*-
# Builds both apps into a single dist/Sweeps/ folder that shares ONE
# _internal directory. Each .exe embeds its own Python bytecode, while the
# heavy shared runtime (Python DLL, dash, plotly, pythonnet, numpy, scipy, ...)
# is collected once by the single COLLECT below.

from PyInstaller.utils.hooks import collect_all

# Packages whose data/binaries/hidden imports we want fully collected.
_collect_pkgs = ["dash", "plotly", "pythonnet", "clr_loader"]

datas, binaries, hiddenimports = [], [], []
for _pkg in _collect_pkgs:
    d, b, h = collect_all(_pkg)
    datas += d
    binaries += b
    hiddenimports += h


def make_analysis(script):
    return Analysis(
        [script],
        pathex=[],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
    )


a_sweep = make_analysis("main_sweep.py")
a_plot = make_analysis("plot_csv.py")

pyz_sweep = PYZ(a_sweep.pure)
pyz_plot = PYZ(a_plot.pure)

exe_sweep = EXE(
    pyz_sweep,
    a_sweep.scripts,
    [],
    exclude_binaries=True,
    name="WavelengthSweep",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon="icon.ico",
)

exe_plot = EXE(
    pyz_plot,
    a_plot.scripts,
    [],
    exclude_binaries=True,
    name="PlotSweep",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon="icon.ico",
)

# A single COLLECT bundles both exes and the union of their binaries/datas
# into one folder with one shared _internal directory.
coll = COLLECT(
    exe_sweep,
    a_sweep.binaries,
    a_sweep.datas,
    exe_plot,
    a_plot.binaries,
    a_plot.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Sweeps",
)
