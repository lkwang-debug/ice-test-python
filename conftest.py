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
