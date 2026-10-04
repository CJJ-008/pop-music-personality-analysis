# -*- coding: utf-8 -*-
"""建库建表：为「用户管理系统」准备 MySQL 数据库。

用法：
    python scripts/init_db.py            # 建库 + 建表（可重复执行，幂等）
    python scripts/init_db.py --check    # 只检查连接与表是否就绪，不做任何改动

前置条件：在 .streamlit/secrets.toml 里配好 [mysql] 段（模板见
.streamlit/secrets.toml.example）。**凭据只从那里读**——本脚本不接受命令行传密码，
因为命令行会被留在 shell 历史里，而 secrets.toml 已被 .gitignore 排除。

建完表还要把 [storage] backend 设成 "mysql"，应用才会真正走数据库；
不设或设成 "json" 时应用读写 data/users.json（云端与 exe 场景就该如此）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from user_store import (  # noqa: E402
    DEFAULT_MYSQL,
    MySqlUserStore,
    StoreConfigError,
    StoreUnavailableError,
    init_schema,
)


def _params() -> dict:
    """从 secrets 取 MySQL 连接参数（校验逻辑复用存储层，避免两处不一致）。"""
    try:
        return MySqlUserStore.from_secrets().params
    except StoreConfigError as exc:
        print(f"[失败] {exc}")
        print()
        print("请在 .streamlit/secrets.toml 里补上 [mysql] 段，例如：")
        print()
        print("  [mysql]")
        print(f'  host = "{DEFAULT_MYSQL["host"]}"')
        print(f'  port = {DEFAULT_MYSQL["port"]}')
        print(f'  user = "{DEFAULT_MYSQL["user"]}"')
        print('  password = "你的 MySQL 密码"')
        print(f'  database = "{DEFAULT_MYSQL["database"]}"')
        raise SystemExit(2) from exc


def _describe(params: dict) -> str:
    return f'{params["user"]}@{params["host"]}:{params["port"]}/{params["database"]}'


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    params = _params()
    print(f"目标数据库：{_describe(params)}")

    if check_only:
        store = MySqlUserStore(params)
        ok, message = store.ping()
        print(f"[{'通过' if ok else '失败'}] {message}")
        return 0 if ok else 1

    try:
        steps = init_schema(params)
    except StoreUnavailableError as exc:
        print(f"[失败] 连不上 MySQL：{exc}")
        print()
        print("排查顺序：")
        print("  1. MySQL 服务是否在运行（Windows：服务里看 MySQL80）")
        print("  2. secrets 里的 user / password 是否正确")
        print("  3. host / port 是否与实际一致（默认 127.0.0.1:3306）")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] 建表出错：{exc}")
        return 1

    for step in steps:
        print(f"[完成] {step}")

    store = MySqlUserStore(params)
    ok, message = store.ping()
    print(f"[{'通过' if ok else '失败'}] 建库后自检：{message}")
    if not ok:
        return 1

    print()
    print("接下来：把 .streamlit/secrets.toml 里的")
    print('  [storage] backend = "mysql"')
    print("设好后重启应用，登录页与管理页就会走数据库。")
    print()
    print("注意：库里的 users 表为空也不影响登录——secrets 里的预置账号（带")
    print('roles = ["admin"]）始终可用，它就是你的第一个管理员。')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
