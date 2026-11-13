#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2026/9/20
# @File    : launcher.py
"""
启动器源码 —— 用 PyInstaller 打包成「启动测试.exe」。

只做三件事：定位包根目录、把执行转交给包内自带的 Python 去跑 runner.py、
结束后暂停等按键（否则双击运行时窗口会一闪而过）。

刻意只用标准库，不含任何第三方依赖，所以 PyInstaller 打包它几乎没有风险。
真正的执行逻辑在 runner.py 里，那里是可读可调的普通 Python 代码。
"""

import subprocess
import sys
from pathlib import Path

LINE = "=" * 66


def pkg_dir() -> Path:
    """包根目录。

    PyInstaller onefile 模式下 __file__ 指向 %TEMP% 里的临时解包目录，
    必须改用 exe 自身的位置，否则找不到旁边的 runtime/ 和 common/config.py。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    base = pkg_dir()
    python_exe = base / "runtime" / "python.exe"
    runner = base / "runner.py"
    config = base / "common" / "config.py"

    print(LINE)
    print("  ICE 接口自动化测试")
    print(LINE)
    print(f"  程序目录: {base}")
    print()

    missing = [p for p in (python_exe, runner, config) if not p.is_file()]
    if missing:
        print("[错误] 包不完整，缺少以下文件：")
        for p in missing:
            print(f"    {p}")
        print()
        print("  请重新完整解压压缩包，注意别漏掉 runtime 目录。")
        print("  （从压缩包内直接双击运行也会出现这个错误，请先解压）")
        return 2

    print(f"  配置文件: {config}")

    print("  提示：若连接失败，请先确认 IceDBProxy 服务器已开通")
    print("        20801/tcp 和 22000/tcp 两个端口。")
    print(LINE)
    print()

    try:
        rc = subprocess.call([str(python_exe), str(runner)], cwd=str(base))
    except KeyboardInterrupt:
        print("\n[中断] 用户取消执行。")
        return 130

    print()
    print(LINE)
    print(f"  执行结束（返回码 {rc}）")
    print(LINE)
    return rc


if __name__ == "__main__":
    code = main()
    try:
        input("\n  按回车键关闭本窗口 ...")
    except (EOFError, KeyboardInterrupt):
        pass
    sys.exit(code)
