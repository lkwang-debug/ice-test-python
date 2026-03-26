#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 下午12:38
# @Author  : hzk
# @File    : test_api2.py
# @Software: PyCharm
# test_import.py
# test_import.py
# test_import.py
# test_import.py

from com.hst.proxy.model.CommonModel import Request, Response
from com.hst.proxy.service.common.CommonService import CommonService, CommonServicePrx

def test_structs():
    req = Request(className="TestClass", method="testMethod", version="1.0", params=b"1234")
    print("Request:", req)

    res = Response(resultCode=200, result=b"response_data")
    print("Response:", res)

def test_proxy_methods():
    # 创建一个 CommonServicePrx 的模拟对象（非真实远程调用，仅测试导入）
    try:
        proxy = CommonServicePrx()  # 实际运行中应使用 communicator.stringToProxy(...) 获取
        print("CommonServicePrx loaded successfully.")
    except Exception as e:
        print("CommonServicePrx creation failed (expected if not connected):", e)

if __name__ == "__main__":
    test_structs()
    test_proxy_methods()



