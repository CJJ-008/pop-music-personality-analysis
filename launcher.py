# -*- coding: utf-8 -*-
"""exe 启动器：双击后启动本地 Streamlit 服务并自动打开浏览器。

原理说明（对使用者的预期管理很重要）：Streamlit 是"本地起服务器 + 浏览器访问"
的网页应用。exe 只是把 Python 运行环境、代码与数据封进一个文件，
双击后会弹出一个控制台窗口（显示服务日志，关掉它即退出服务）并自动打开浏览器。

打包命令（项目根目录执行）：
    pyinstaller --clean -y streamlit_app.spec
"""
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def resource_dir() -> Path:
    """只读资源目录（app.py、结果表）。打包后是解包临时目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def base_dir() -> Path:
    """可写基准目录（.streamlit/secrets.toml、data/users.json）。打包后是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def free_port(start: int = 8501, tries: int = 50) -> int:
    """从 start 起找一个空闲端口，避免 8501 被占用时直接失败。"""
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main() -> None:
    import multiprocessing

    multiprocessing.freeze_support()  # Windows 打包程序的标准要求

    # 确保这些模块被打包：joblib.load 反序列化流行度模型时需要它们，
    # 但 PyInstaller 的静态分析看不到 pickle 文件内部的依赖链，必须显式导入
    import sklearn.ensemble  # noqa: F401
    import sklearn.tree  # noqa: F401
    import scipy.sparse  # noqa: F401

    base = base_dir()
    os.chdir(base)  # 让 st.secrets 读到 exe 旁边的 .streamlit/secrets.toml

    secrets_path = base / ".streamlit" / "secrets.toml"
    print("=" * 60)
    print("[启动器] 工作目录 :", base)
    print("[启动器] 资源目录 :", resource_dir())
    print(f"[启动器] 登录凭据 : {'已找到' if secrets_path.exists() else '未找到（将显示配置指引页）'}")
    print("=" * 60)

    port = free_port(8501)
    url = f"http://localhost:{port}"

    # 延迟打开浏览器，等服务就绪；headless 交给这里的 webbrowser 控制，确定性更好
    threading.Timer(2.5, lambda: webbrowser.open(url)).start()

    import streamlit.web.cli as stcli

    sys.argv = [
        "streamlit", "run", str(resource_dir() / "app.py"),
        f"--server.port={port}",
        "--server.address=localhost",
        "--server.fileWatcherType=none",  # 打包环境无源码变化可监听，禁用监视器
        "--server.headless=true",
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
