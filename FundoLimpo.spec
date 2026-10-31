# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_submodules

binaries = []
hiddenimports = []
binaries += collect_dynamic_libs('onnxruntime')
hiddenimports += collect_submodules('onnxruntime.capi')
hiddenimports += collect_submodules('pygrabber')


a = Analysis(
    ['fundolimpo/__main__.py'],
    pathex=['.'],
    binaries=binaries,
    datas=[('modelo', 'modelo'), ('camera/x64', 'camera/x64'), ('camera/x86', 'camera/x86'), ('instalador/icone.png', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['onnxruntime.quantization', 'onnxruntime.tools', 'onnxruntime.transformers', 'pyvirtualcam'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FundoLimpo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['instalador/icone.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FundoLimpo',
)
