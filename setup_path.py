#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 下午4:01
# @Author  : hzk
# @File    : setup_path.py
# @Software: PyCharm

# setup_path.py



import sys
from pathlib import Path

# 假设 setup_path.py 在项目根目录，获取根目录绝对路径
project_root = Path(__file__).parent.parent.resolve()

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


if __name__ == '__main__':
    print("sys.path[0]:", sys.path[0])