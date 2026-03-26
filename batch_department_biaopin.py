#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/10/20 下午5:39
# @Author  : hzk
# @File    : batch_department_biaopin.py
# @Software: PyCharm




import requests
import random
import string

# ========== 配置 ==========
API_URL = "https://sztest.haoshitong.com:28443/api/v1/department/add"
AUTHORIZATION = "eyJhbGciOiAiU0hBMjU2In0=.eyJrZXkiOiAiYmY0YjgyMTMiLCAidGltZXN0YW1wIjogMS43NjM2MzI2MTQxMmUrMTJ9.e71d82d3e69d47e4ba9d8071104417d193e655be8383d26a4900efa0e675bb7c"
PARENT_DEPART_ID = 4
CREATE_COUNT = 5000

# 使用会话复用连接，减少TCP握手
session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "Authorization": AUTHORIZATION
})

# ========== 工具函数 ==========
def generate_depart_name(prefix="Dept组织"):
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=11))
    return f"{prefix}_{suffix}"


def create_department(depart_name, parent_id):
    headers = {"Content-Type": "application/json", "Authorization": AUTHORIZATION}
    body = {"departName": depart_name, "parentDepartId": parent_id}
    try:
        resp = session.post(API_URL, json=body, headers=headers, timeout=3)
        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {"error": str(e)}

def batch_create_departments(count):

    for i in range(count):
        depart_name = generate_depart_name()

        status_code, result = create_department(
            depart_name,
            PARENT_DEPART_ID
        )

        print(f"[{i+1}/{count}] 创建部门: {depart_name},  状态码: {status_code}")
        print("响应内容:", result)

        if status_code == 200 and result.get("code") == "0":
            last_depart_code = result["data"]["departId"]
        else:
            print("创建失败，终止后续创建。")
            break

# ========== 执行 ==========
if __name__ == "__main__":
    batch_create_departments(CREATE_COUNT)



