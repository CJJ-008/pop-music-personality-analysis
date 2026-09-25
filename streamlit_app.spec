# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（单文件模式）。

构建命令（项目根目录执行）：
    pyinstaller --clean -y streamlit_app.spec

产物：dist/性格歌手推荐器.exe（约 150~300MB，双击运行）。
注意：构建产物 build/ 与 dist/ 已被 .gitignore 排除，exe 本身也超过
GitHub 单文件 100MB 限制，不能也不应提交进仓库。
"""
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = [
    # 应用本体与认证模块：streamlit 运行时以脚本方式执行 app.py，故作为数据文件携带
    ("app.py", "."),
    ("auth.py", "."),
    # 仪表盘唯一的数据源：分析结果表
    ("outputs/tables", "outputs/tables"),
    # 凭据配置模板（真实的 secrets.toml 绝不打包——exe 可被解包，嵌凭据等于泄露）
    (".streamlit/secrets.toml.example", ".streamlit"),
]
# streamlit 运行必需：包元数据 + 静态前端资源（约 500 个文件）
datas += copy_metadata("streamlit")
datas += collect_data_files("streamlit")
datas += collect_data_files("streamlit_authenticator")
# 认证库依赖的 Cookie 组件在导入时声明 frontend/build 目录，字体库同理需要字体文件
# ——只打包代码不打包这些数据文件会在运行时报 No such component directory
datas += collect_data_files("extra_streamlit_components")
datas += collect_data_files("captcha")

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "auth",
        # Streamlit 脚本执行器在运行时动态 import 此模块，静态分析看不到，必须显式声明
        "streamlit.runtime.scriptrunner.magic_funcs",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="性格歌手推荐器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 不加壳：降低杀毒软件误报概率
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 保留控制台：展示服务日志，关闭窗口即退出服务
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
