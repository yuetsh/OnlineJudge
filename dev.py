#!/usr/bin/env python
"""
开发服务器启动脚本
使用 uvicorn 统一处理 HTTP 和 WebSocket
"""

import subprocess
import sys
from pathlib import Path


def main():
    base_dir = Path(__file__).resolve().parent
    venv_python = base_dir / ".venv" / "bin" / "python"
    python_exec = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [
        python_exec,
        "-m",
        "uvicorn",
        "oj.asgi:application",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload",
    ]

    print("启动 uvicorn 开发服务器 (端口 8000)...")
    try:
        subprocess.run(cmd, cwd=base_dir)
    except KeyboardInterrupt:
        print("\n服务器已停止")


if __name__ == "__main__":
    main()
