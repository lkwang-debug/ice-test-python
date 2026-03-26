#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/20 下午4:48
# @Author  : hzk
# @File    : run.py
# @Software: PyCharm
import inspect

import os
import subprocess

import pytest
import time
import sys

start_total = time.time()

def main():
    sys._pytest_running = True
    print("开始执行测试用例...")

    # 不再需要从 test_api_all.py 导入生成器，这里只运行 pytest 即可
    print(f"[阶段1] 初始化用例生成器和加载用例由 test_api_all.py 动态完成")
    print(f"[阶段2] 已在 test_api_all.py 中完成注册，无需重复注册")
    print(f"[阶段3] 用例准备总耗时: {time.time() - start_total:.2f}s\n")

    t3 = time.time()
    pytest_args = [
        "-sv",
        "test_api_all.py",
        "--alluredir=allure_report/result",
        "--clean-alluredir"
    ]
    print(f"运行 pytest: {' '.join(pytest_args)}")
    pytest.main(pytest_args)
    print(f"[阶段4] pytest 执行耗时: {time.time() - t3:.2f}s")

    t4 = time.time()
    print("\n开始生成 Allure 报告...")
    # 设置 JVM 内存限制，避免环境污染
    os.environ.pop("JAVA_OPTS", None)
    os.environ["JAVA_OPTS"] = "-Xmx512m"


    # 用 os.system 直接调用 Allure
    os.system("allure generate allure_report/result -o allure_report/html --clean")
    print(f"[阶段5] Allure 报告生成耗时: {time.time() - t4:.2f}s")

    t5 = time.time()
    print("打开 Allure 报告...")
    #os.system("allure open allure_report/html")
    # 启动 Allure 服务器，并在后台运行，不阻塞 Jenkins
    subprocess.Popen("start /B allure open allure_report/html", shell=True)
    print(f"[阶段6] Allure 报告打开耗时: {time.time() - t5:.2f}s")

if __name__ == '__main__':
    main()

# import os
# import pytest
# import time
# import sys
#
# start_total = time.time()
#
# from test_api_all import TestCaseGenerator
#
#
# def main():
#     sys._pytest_running = True
#     print("开始执行测试用例...")
#
#     t1 = time.time()
#     generator = TestCaseGenerator()
#     print(f"[阶段1] 初始化 TestCaseGenerator 耗时: {time.time() - t1:.2f}s")
#     print(f"[阶段2] 已在 test_api_all.py 中完成注册，无需重复注册")
#     # t2 = time.time()
#     # test_count = 0
#     # for test_func in generator.generate_tests():
#     #     test_count += 1
#     #     setattr(sys.modules[__name__], test_func.__name__, test_func)
#     # print(f"[阶段2] 注册 {test_count} 条测试用例耗时: {time.time() - t2:.2f}s")
#     #
#     print(f"[阶段3] 用例准备总耗时: {time.time() - start_total:.2f}s\n")
#
#     t3 = time.time()
#     pytest_args = [
#         "-sv",
#         "test_api_all.py",
#         "--alluredir=allure_report/result",
#         "--clean-alluredir"
#
#     ]
#     print(f"运行 pytest: {' '.join(pytest_args)}")
#     pytest.main(pytest_args)
#     print(f"[阶段4] pytest 执行耗时: {time.time() - t3:.2f}s")
#
#     t4 = time.time()
#     print("\n开始生成 Allure 报告...")
#     os.system("allure generate allure_report/result -o allure_report/html --clean")
#     print(f"[阶段5] Allure 报告生成耗时: {time.time() - t4:.2f}s")
#
#     t5 = time.time()
#     print("打开 Allure 报告...")
#     os.system("allure open allure_report/html")
#     print(f"[阶段6] Allure 报告打开耗时: {time.time() - t5:.2f}s")
#
# if __name__ == '__main__':
#     main()

