"""Run with: python -m knowflow.web [--refresh] [--port 8765]."""

import argparse
import webbrowser
from pathlib import Path

from knowflow.web.data import load_dashboard, prepare
from knowflow.web.server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="KnowFlow 本机教师与学生工作台")
    parser.add_argument("--refresh", action="store_true", help="在新的本机目录重建所有成果")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run", type=Path, help="复用 artifacts/web 中已有的整套运行目录")
    args = parser.parse_args()
    try:
        run = args.run or prepare(refresh=args.refresh)
        snapshot = load_dashboard(run)
        print(f"Validated dashboard data: {run}", flush=True)
        if args.prepare_only:
            return 0
        server = create_server(run, snapshot, args.port)
    except (ValueError, OSError) as exc:
        print(f"Dashboard could not start: {exc}", flush=True)
        return 1
    url = f"http://127.0.0.1:{server.server_port}/teacher"
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
