#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 上午11:42
# @Author  : hzk
# @File    : conftest.py
# @Software: PyCharm


import setup_path
import sys
from pathlib import Path

# 获取项目根目录和 generated 目录路径
project_root = Path(__file__).parent.resolve()
generated_dir = project_root / "generated"

# 添加项目根目录（如 E:\python_project\ice_test_pythonProject）到 sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 添加 generated（包含 com 包）到 sys.path
if str(generated_dir) not in sys.path:
    sys.path.insert(0, str(generated_dir))

#print("==== sys.path (conftest.py) ====")
# for i in sys.path[:5]:
#     print(i)
print("===============================")

import pytest
import sys
from pathlib import Path
import Ice

from method import (
    CompanyMethods,
    DeviceMethods,
    FileMethods,
    RoomMethods,
    UserMethods
)

# 项目根目录路径
project_root = Path(__file__).parent.resolve()

# ice文件目录路径（假设在根目录下的 ice_files 文件夹）
ice_files_dir = project_root / "ice_files"



@pytest.fixture(scope="session")
def company_methods():
    methods = CompanyMethods()
    yield methods
    methods.close()

@pytest.fixture(scope="session")
def device_methods():
    methods = DeviceMethods()
    yield methods
    methods.close()

@pytest.fixture(scope="session")
def file_methods():
    methods = FileMethods()
    yield methods
    methods.close()

@pytest.fixture(scope="session")
def room_methods():
    methods = RoomMethods()
    yield methods
    methods.close()

@pytest.fixture(scope="session")
def user_methods():
    methods = UserMethods()
    yield methods
    methods.close()

@pytest.fixture
def get_methods(request):
    """根据类名动态获取对应的方法类"""
    class_mapping = {
        "company": request.getfixturevalue("company_methods"),
        "device": request.getfixturevalue("device_methods"),
        "file": request.getfixturevalue("file_methods"),
        "room": request.getfixturevalue("room_methods"),
        "user": request.getfixturevalue("user_methods")
    }
    return lambda class_name: class_mapping.get(class_name.lower())


def pytest_addoption(parser):
    group = parser.getgroup("gateway")
    group.addoption("--gateway-run", action="store_true", help="Execute live gateway tests")
    group.addoption("--gateway-profile", help="Environment/resource profile JSON")
    group.addoption("--gateway-host", help="Explicitly override the gateway host")
    group.addoption("--gateway-topology", choices=["single", "dual"])
    from common.config import TEST_CONFIG
    group.addoption("--gateway-scope", choices=["read", "resource", "global"], default=TEST_CONFIG.get("scope", "global"))


@pytest.fixture(scope="session")
def gateway_runtime(request):
    from common.runtime import GatewayRuntime, load_profile
    if not request.config.getoption("--gateway-run"):
        pytest.skip("Live tests are opt-in: python run.py; settings are in common/config.py")
    profile = getattr(request.config, "_gateway_effective_profile", None) or load_profile(request.config.getoption("--gateway-profile"),
                           request.config.getoption("--gateway-topology"),
                           request.config.getoption("--gateway-host"))
    runtime = GatewayRuntime(profile)
    try:
        details = runtime.preflight(request.config.getoption("--gateway-scope"))
        from common.executor import attach
        attach("Database environment", details)
        report_dir = request.config.getoption("allure_report_dir", default=None)
        if report_dir:
            import json
            output = Path(report_dir)
            output.mkdir(parents=True, exist_ok=True)
            values = {"Database": details["backend"], "Database.config": ", ".join(details.get("config_files", [])),
                      "Database.client": str(details.get("container") or "host"), "Topology": runtime.topology}
            output.joinpath("environment.properties").write_text(
                "\n".join(key + "=" + value for key, value in values.items()) + "\n", encoding="utf-8")
        yield runtime
    finally:
        runtime.close()


@pytest.fixture
def gateway_case(request, gateway_runtime):
    from common.scenarios import Scenario
    from common.executor import attach
    case = request.param
    gateway_runtime.check_case_applicability(case, request.config.getoption("--gateway-scope"))
    scenario = Scenario(gateway_runtime, case)
    try:
        scenario.prepare()
        yield scenario
    finally:
        try:
            scenario.close()
        except Exception as exc:
            from common.outcomes import label_outcome
            label_outcome("cleanup_failure", str(exc), {"case_id": case["case_id"]})
            attach("Cleanup failure", {"case_id": case["case_id"], "error": str(exc)})
            raise
