#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2026/9/20
# @File    : runner.py
"""
打包版一键执行入口（由 run.py 的编排逻辑改造而来）。

与 run.py 的区别：
  - 所有路径基于本文件位置推导成绝对路径，不受"从哪个目录双击"影响
  - Allure 走包内 tools\\allure-2.18.1，Java 走包内 tools\\jre8，不依赖 PATH 和系统 Java
  - 执行前先做一次 ICE 连通性检查：不通就给出端口提示直接退出，
    不再让 276 条用例全红却看不出真正原因
  - 结束后打印通过/失败汇总

run.py 保持原样不动，开发机上继续用它。
"""

import json
import logging
import os
import socket
import subprocess
import sys
import time
import shutil
from pathlib import Path

# 输出重定向到文件时，遇到 GBK 表达不了的字符不要直接崩
try:
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

PKG_DIR = Path(__file__).resolve().parent
os.chdir(PKG_DIR)

# 打包版用的是 Python 嵌入式发行版，它带 python310._pth，运行时处于"隔离模式"：
# 不会像普通 Python 那样自动把脚本所在目录放进 sys.path，于是 import common 会直接
# ModuleNotFoundError。开发机上的普通 Python 没这个问题，所以这里显式补一次。
# （conftest.py 会在 pytest 启动后自己补路径，但本文件是在那之前就要 import 配置）
if str(PKG_DIR) not in sys.path:
    sys.path.insert(0, str(PKG_DIR))

from common.config import ICE_CONFIG, EXCEL_CONFIG, ALLURE_CONFIG  # noqa: E402

RESULT_DIR = Path(ALLURE_CONFIG["output_dir"]) / "result"
HTML_DIR = Path(ALLURE_CONFIG["output_dir"]) / "html"

LINE = "=" * 66
EXIT_OK, EXIT_TEST_FAILED, EXIT_PREFLIGHT_FAILED = 0, 1, 2


def setup_logging() -> Path:
    """把框架内部的日志写进文件，控制台只保留本程序整理过的信息。

    否则连接失败时，用户最先看到的是一大段英文 traceback（logging 默认输出到
    stderr），真正有用的"端口没开"提示反而被挤到后面，容易把人带偏。
    日志仍然完整保留，只是不往控制台刷。
    """
    log_path = Path(ALLURE_CONFIG["output_dir"]) / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename=str(log_path),
        filemode="w",
        encoding="utf-8",
    )
    return log_path


def banner():
    print(LINE)
    print("  ICE 接口自动化测试 —— 一键执行")
    print(LINE)
    print(f"  配置来源   : {PKG_DIR / 'common' / 'config.py'}")
    print(f"  ICE 服务   : {ICE_CONFIG['locator']}")
    print(f"  用例文件   : {EXCEL_CONFIG['file_path']}")
    print(f"  报告输出   : {ALLURE_CONFIG['output_dir']}")
    print(LINE)
    print("  提示：若连接失败，请先确认 IceDBProxy 服务器已开通")
    print("        20801/tcp 和 22000/tcp 两个端口")
    print(LINE)
    print()


def preflight(profile=None) -> bool:
    """执行前检查数据库、ICE及环境资源。

    返回 False 时调用方直接退出 —— 否则 276 条用例会因为连不上而全红，
    真正的原因（端口不通）反而被淹没在失败信息里。
    """
    print("[预检] 正在检查数据库、ICE 服务及环境资源 ...")

    try:
        from common.ice_client import IceClient, CONNECT_FAIL_HINT
    except Exception as e:
        print("\n[预检失败] 无法加载 ICE 运行库（Ice / IcePy）。")
        print(f"  原因: {e}")
        print("  可能的情况：")
        print("    1) runtime 目录不完整（被解压软件漏掉文件）")
        print("    2) 缺少 VC++ 运行库（msvcp140.dll / vcruntime140.dll）")
        print("    3) 目标机是 32 位系统 —— 本包只支持 64 位 Win10/Win11")
        return False

    from common.runtime import GatewayRuntime, load_profile
    profile = profile if profile is not None else load_profile()
    runtime = GatewayRuntime(profile)
    try:
        details = runtime.preflight(profile.get("scope", "global"))
        profile["database"]["_resolved"] = runtime.database.resolve()
        print("[preflight] Database: " + json.dumps(details, ensure_ascii=False))
        print("[preflight] ICE, database and configured resources are ready.\n")
        return True
    except Exception as exc:
        print("[preflight failed] " + str(exc))
        if "gateway" in str(exc).lower():
            print(CONNECT_FAIL_HINT)
        return False
    finally:
        runtime.close()


def pick_free_port(preferred: int = 5050) -> int:
    """挑一个空闲端口。

    Allure 默认用 5050，上一次没退干净就会 "Address already in use"，
    而浏览器此时仍旧展示旧报告 —— 很容易让人以为新报告没生成。
    """
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def run_pytest(profile=None) -> int:
    print("[1/3] 执行测试用例 ...")
    t0 = time.time()

    import pytest

    sys._pytest_running = True
    args = [
        "-sv",
        "test_api_all.py",
        "tests/integration",
        "--gateway-run",
        f"--alluredir={RESULT_DIR}",
        "--clean-alluredir",
    ]
    args.extend(sys.argv[1:])
    print(f"      pytest {' '.join(str(a) for a in args)}")
    plugins = []
    if profile is not None:
        class EffectiveProfile:
            def pytest_configure(self, config):
                config._gateway_effective_profile = profile
        plugins.append(EffectiveProfile())
    code = pytest.main(args, plugins=plugins)
    print(f"      耗时 {time.time() - t0:.2f}s")
    return int(code)


def summarize() -> dict:
    """从 allure 结果文件统计，保证打印的汇总和报告里看到的一致。"""
    counts = {}
    for f in RESULT_DIR.glob("*-result.json"):
        try:
            status = json.loads(f.read_text(encoding="utf-8")).get("status", "unknown")
        except Exception:
            continue
        counts[status] = counts.get(status, 0) + 1
    return counts


def generate_report() -> bool:
    print("\n[2/3] 生成 Allure 报告 ...")
    t0 = time.time()

    allure_bat = Path(ALLURE_CONFIG["cli"])
    java_home = Path(ALLURE_CONFIG["java_home"])

    if not allure_bat.is_file():
        fallback = shutil.which("allure")
        if not fallback:
            print(f"      [跳过] 找不到 Allure: {allure_bat}")
            return False
        allure_bat = Path(fallback)

    # 让 allure.bat 用包内自带的 JRE，目标机不需要装 Java
    if java_home.is_dir():
        os.environ["JAVA_HOME"] = str(java_home)
        os.environ["PATH"] = str(java_home / "bin") + os.pathsep + os.environ.get("PATH", "")
        print(f"      JAVA_HOME = {java_home}")
    else:
        print(f"      [注意] 未找到自带 JRE（{java_home}），将尝试使用系统 Java")

    os.environ.pop("JAVA_OPTS", None)
    os.environ["JAVA_OPTS"] = "-Xmx512m"

    cmd = f'"{allure_bat}" generate "{RESULT_DIR}" -o "{HTML_DIR}" --clean'
    rc = subprocess.call(cmd, shell=True)
    print(f"      耗时 {time.time() - t0:.2f}s")

    if rc != 0:
        print(f"      [失败] Allure 生成返回码 {rc}")
        return False
    return True


def start_report_server():
    """启动 Allure 报告服务，返回子进程句柄；失败返回 None。

    这里刻意**不做进程脱离**，而是让服务作为本程序的子进程存在，退出时统一收掉。
    原因是脱离的写法都有坑：
      - start /B   与服务共用控制台，本程序一退出控制台关闭，java 被一起杀掉，
                   表现成"刚提示完地址、报告就没了"
      - start /MIN 会另开一个控制台窗口，在无交互桌面/重定向环境下会直接卡住
    让服务随本程序生命周期走，反而最干净：窗口在报告就在，窗口关服务自动结束，
    也不会留下一堆孤儿 java 进程。
    """
    print("\n[3/3] 启动 Allure 报告服务 ...")

    allure_bat = Path(ALLURE_CONFIG["cli"])
    html_dir = HTML_DIR

    if not allure_bat.is_file():
        fallback = shutil.which("allure")
        if not fallback:
            print(f"      [跳过] 找不到 Allure，可执行 python -m http.server 5050 --bind 127.0.0.1 --directory \"{html_dir}\"")
            return None
        allure_bat = Path(fallback)
    if not (html_dir / "index.html").is_file():
        print("      [跳过] 报告没有生成，无法打开")
        return None

    port = pick_free_port(5050)
    if port != 5050:
        print(f"      [注意] 5050 被占用，改用 {port}")

    # allure 是 .bat，必须经 cmd 才能启动
    proc = subprocess.Popen(
        ["cmd", "/c", str(allure_bat), "open", str(html_dir), "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 探活：确认服务真的起来了再报地址。
    # 不探活就直接打印地址，会出现"提示了地址但浏览器打不开"的情况，比直接报错更难排查。
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):  # 最多等 30 秒
        if proc.poll() is not None:
            print(f"      [失败] 报告服务启动后立刻退出了（返回码 {proc.returncode}）")
            return None
        time.sleep(0.5)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print(f"      报告地址: {url}")
                print("      浏览器会自动打开该地址。")
                return proc

    print("      [失败] 等了 30 秒服务仍未就绪。")
    print("             可以手动执行：")
    print(f'               set JAVA_HOME={ALLURE_CONFIG["java_home"]}')
    print(f'               "{allure_bat}" open "{html_dir}"')
    stop_report_server(proc)
    return None


def stop_report_server(proc) -> None:
    """收掉报告服务。

    必须用 /T 结束整棵进程树：cmd 下面还挂着一个 java，只杀 cmd 杀不掉 java，
    会留下孤儿进程继续占着端口。
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def print_summary(counts: dict) -> None:
    print(f"\n{LINE}")
    print("  执行结果汇总")
    print(LINE)
    if counts:
        labels = {"passed": "通过", "failed": "失败", "broken": "异常", "skipped": "跳过"}
        for status in ("passed", "failed", "broken", "skipped", "unknown"):
            if status in counts:
                print(f"    {labels.get(status, status):<4} {counts[status]}")
        print(f"    {'合计':<4} {sum(counts.values())}")
    else:
        print("    没有读到用例结果，请检查上面的输出")
    if counts:
        from common.reporting import write_summary
        summary = write_summary(RESULT_DIR, RESULT_DIR.parent / "outcomes.json")
        print("  场景分类（阻塞、不支持、契约待明确不计入通过）：")
        names = {"passed": "通过", "backend_defect": "后端回归失败", "compatibility_gap": "兼容性差异",
                 "assertion_failure": "其他断言失败", "prerequisite_blocked": "前置阻塞",
                 "version_unsupported": "版本不支持", "contract_review": "契约待明确（已执行）",
                 "not_applicable": "场景不适用", "infrastructure_error": "执行异常", "cleanup_failure": "清理失败"}
        for category, number in summary["counts"].items():
            print(f"    {names.get(category, category)}: {number}")
    print(LINE)


def wait_for_report() -> None:
    """等用户看完报告再结束。

    报告服务是本程序的子进程，所以这里必须停住 —— 否则本程序一退出，
    服务就被收掉，用户还没看清报告地址就打不开了。
    """
    print()
    print(LINE)
    print("  报告服务已就绪，可以先去看报告。")
    print("  看完后回到本窗口按回车结束（报告服务会随之停止）。")
    print(LINE)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        # 无交互环境（例如重定向运行）下读不到输入，直接继续
        pass


def main() -> int:
    # Apply explicit profile identity to both preflight and the pytest runtime.
    import argparse
    from common.runtime import load_profile
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--gateway-profile")
    parser.add_argument("--gateway-host")
    parser.add_argument("--gateway-topology")
    parser.add_argument("--gateway-scope")
    options, _ = parser.parse_known_args()
    profile = load_profile(options.gateway_profile, options.gateway_topology, options.gateway_host)
    if options.gateway_scope:
        profile["scope"] = options.gateway_scope
    if profile.get("host"):
        from common.config import build_ice_locator
        ICE_CONFIG["locator"] = build_ice_locator(profile["host"], profile.get("locator_port", 22000), profile.get("protocol", "tcp"))
        ICE_CONFIG["service"] = profile["service"]
        ICE_CONFIG["adapter"] = profile["adapter"]
    log_path = setup_logging()

    banner()

    if not preflight(profile):
        print("\n[中止] 环境预检未通过，未执行任何用例。")
        print("       请按上面的错误检查网络、数据库与 common/config.py 后重试。")
        # 上一轮生成的报告还在磁盘上，必须说清楚。
        # 预检失败时 pytest 没跑，--clean-alluredir 自然不会执行，旧报告会原样留着，
        # 不知情的人打开会以为那就是本次结果。
        if (HTML_DIR / "index.html").is_file():
            print()
            print(f"       注意：{HTML_DIR}")
            print("       里面还是【上一次】运行生成的报告，本次没有更新它。")
        print(f"\n       详细日志: {log_path}")
        return EXIT_PREFLIGHT_FAILED

    pytest_code = run_pytest(profile)
    counts = summarize()
    print_summary(counts)

    server = None
    if generate_report():
        server = start_report_server()

    if server is not None:
        wait_for_report()

    stop_report_server(server)

    print(f"\n完成。pytest 返回码 = {pytest_code}")
    print(f"详细日志: {log_path}")
    failed = counts.get("failed", 0) + counts.get("broken", 0)
    return EXIT_TEST_FAILED if (failed or pytest_code != 0) else EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消执行。")
        sys.exit(130)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n[异常] 执行过程中出错: {e}")
        sys.exit(1)
