"""Run with: python -m knowflow.web [--refresh] [--port 8765]."""

import argparse
import webbrowser
from pathlib import Path

from knowflow.web.auth import (
    DEFAULT_PASSWORD,
    AuthStore,
    default_users_path,
    read_policy_thresholds,
)
from knowflow.web.data import load_dashboard, prepare
from knowflow.web.server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="KnowFlow 本机教师与学生工作台")
    parser.add_argument("--refresh", action="store_true", help="在新的本机目录重建所有成果")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--users", type=Path, help="账号文件路径（默认 data/auth/users.json）")
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="跳过登录直接以教师身份进入（仅本机排障用，不要用于演示）",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--llm",
        dest="llm",
        action="store_true",
        default=None,
        help="rebuild with the optional language layer; later starts reuse that mode",
    )
    mode.add_argument(
        "--no-llm",
        dest="llm",
        action="store_false",
        help="rebuild with rule templates only",
    )
    parser.add_argument("--run", type=Path, help="复用 artifacts/web 中已有的整套运行目录")
    args = parser.parse_args()
    auth = None
    try:
        users_path = args.users or default_users_path()
        thresholds = None if args.no_auth else read_policy_thresholds(users_path)
        run = args.run or prepare(refresh=args.refresh, llm=args.llm, thresholds=thresholds)
        snapshot = load_dashboard(run)
        if not args.no_auth:
            student_id = snapshot["students"][0]["student_id"] if snapshot["students"] else "S001"
            auth = AuthStore(users_path, student_id)
            if auth.created:
                print(f"已生成本机账号文件：{auth.path}", flush=True)
                print(
                    f"  教师 teacher / {DEFAULT_PASSWORD}　　"
                    f"学生 {student_id} / {DEFAULT_PASSWORD}",
                    flush=True,
                )
        print(f"Validated dashboard data: {run}", flush=True)
        if args.prepare_only:
            return 0
        server = create_server(
            run,
            snapshot,
            args.port,
            auth=auth,
            thresholds_provider=(auth.policy_thresholds if auth is not None else None),
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) == 98:
            print(
                f"Dashboard could not start: 端口 {args.port} 已被占用。"
                "请先关闭旧的启动窗口（可能有多个），或用 --port 8766 换一个端口。",
                flush=True,
            )
        else:
            print(f"Dashboard could not start: {exc}", flush=True)
        return 1
    except ValueError as exc:
        print(f"Dashboard could not start: {exc}", flush=True)
        return 1
    entry = "/login" if auth is not None else "/teacher"
    url = f"http://127.0.0.1:{server.server_port}{entry}"
    print(f"KnowFlow: {url}\nPress Ctrl+C to stop.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Dashboard stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
