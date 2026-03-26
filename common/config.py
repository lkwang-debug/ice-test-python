#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 上午11:38
# @Author  : hzk
# @File    : config.py
# @Software: PyCharm

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

"""
开放端口
tcp/20801  22000
firewall-cmd --zone=public --add-port=20801/tcp --permanent
firewall-cmd --zone=public --add-port=22000/tcp --permanent
firewall-cmd --reload
"""
# ICE服务配置
ICE_CONFIG = {
    "locator": "IceGrid/Locator:default -h 192.168.6.132 -p 22000",
    "service": "commonService",
    "adapter": "dbProxy-1.dbProxyAdapter"
}

# Excel配置
EXCEL_CONFIG = {
    "file_path": str(BASE_DIR / "data/test_cases.xlsx"),
    "sheet_name": "TestCases"
}

# Allure配置
ALLURE_CONFIG = {
    "report_dir": str(BASE_DIR / "allure-results"),
    "history_dir": str(BASE_DIR / "allure-report/history")
}

# 日志配置
LOG_CONFIG = {
    "level": "DEBUG",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
}