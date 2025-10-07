#!/usr/bin/env python
"""
WebSocket 开发服务器启动脚本
同时启动 Daphne (WebSocket) 和 Django runserver (开发服务器)
支持 Windows 和 Linux
"""

import os
import sys
import subprocess
import platform
import signal
from pathlib import Path
from threading import Thread
import time


def main():
    # 获取项目根目录
    base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)

    print("=" * 70)
    print("启动 Django 开发服务器 + WebSocket 服务器")
    print("=" * 70)
    print()

    # 检测操作系统
    is_windows = platform.system() == "Windows"

    # 检查虚拟环境（跨平台）
    if is_windows:
        # Windows: .venv/Scripts/python.exe
        venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    else:
        # Linux/Mac: .venv/bin/python
        venv_python = base_dir / ".venv" / "bin" / "python"

    if venv_python.exists():
        print("[✓] 使用虚拟环境: .venv")
        python_exec = str(venv_python)
    else:
        print("[!] 未找到 .venv 虚拟环境，使用全局 Python")
        print("[!] 建议创建虚拟环境: python -m venv .venv")
        python_exec = sys.executable

    # 检查 daphne 是否安装
    try:
        result = subprocess.run(
            [python_exec, "-m", "daphne", "--version"], capture_output=True, text=True
        )
        if result.returncode != 0 and result.returncode != 2:
            print("[✗] 错误: Daphne 未安装")
            print("请运行: pip install daphne channels channels-redis")
            sys.exit(1)
    except FileNotFoundError:
        print("[✗] 错误: 无法找到 Python 解释器")
        sys.exit(1)
    # 进程列表
    processes = []

    # 启动两个服务器
    try:
        # 启动 Django runserver (端口 8000)
        print("[*] 启动 Django 开发服务器 (端口 8000)...")
        runserver_cmd = ["uv", "run", "manage.py", "runserver", "0.0.0.0:8000"]
        runserver_process = subprocess.Popen(
            runserver_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        processes.append(("Django Runserver", runserver_process))

        # 等待一下，让 runserver 先启动
        time.sleep(1)

        # 启动 Daphne (端口 8001)
        print("[*] 启动 Daphne WebSocket 服务器 (端口 8001)...")
        daphne_cmd = [
            python_exec,
            "-m",
            "daphne",
            "-b",
            "0.0.0.0",
            "-p",
            "8001",
            "oj.asgi:application",
        ]
        daphne_process = subprocess.Popen(
            daphne_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        processes.append(("Daphne", daphne_process))

        print()
        print("[✓] 所有服务器已启动")
        print()

        # 创建输出线程
        def print_output(name, process):
            """打印进程输出"""
            for line in process.stdout:
                print(f"[{name}] {line}", end="")

        # 启动输出线程
        threads = []
        for name, process in processes:
            thread = Thread(target=print_output, args=(name, process), daemon=True)
            thread.start()
            threads.append(thread)

        # 等待进程（任意一个退出就退出）
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"\n[!] {name} 已退出")
                    raise KeyboardInterrupt
            time.sleep(0.5)

    except KeyboardInterrupt:
        print()
        print()
        print("[*] 正在停止所有服务器...")

        # 终止所有进程
        for name, process in processes:
            try:
                if process.poll() is None:  # 如果进程还在运行
                    print(f"[*] 停止 {name}...")
                    if is_windows:
                        # Windows 使用 CTRL_C_EVENT
                        process.send_signal(signal.CTRL_C_EVENT)
                    else:
                        # Unix 使用 SIGTERM
                        process.terminate()

                    # 等待进程结束（最多 5 秒）
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print(f"[!] {name} 未响应，强制终止...")
                        process.kill()
                        process.wait()
            except Exception as e:
                print(f"[!] 停止 {name} 时出错: {e}")

        print()
        print("[✓] 所有服务器已停止")

    except Exception as e:
        print(f"[✗] 错误: {e}")

        # 清理所有进程
        for name, process in processes:
            try:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            except Exception:
                pass

        sys.exit(1)


if __name__ == "__main__":
    main()
