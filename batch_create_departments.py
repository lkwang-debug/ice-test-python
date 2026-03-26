#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/7/26 上午10:56
# @Author  : hzk
# @File    : batch_create_departments.py
# @Software: PyCharm




import requests
import random
import string

# ========== 配置 ==========
API_URL = "https://XJ.haoshitong.com:28443/api/v1/department/add"
AUTHORIZATION = "eyJhbGciOiAiU0hBMjU2In0=.eyJrZXkiOiAiYmY0YjgyMTMiLCAidGltZXN0YW1wIjogMS43NjI5MjcxNTA5MWUrMTJ9.55f4d653e33a22bc29f570b5b0e11b1ffecdc8b82c3357b0f76c02caeb604882"
PARENT_DEPART_ID = 5
PARENT_DEPART_CODE = str(PARENT_DEPART_ID)
CREATE_COUNT = 5000

# 使用会话复用连接，减少TCP握手
session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "Authorization": AUTHORIZATION,
    "parentDepartCode": PARENT_DEPART_CODE
})

# ========== 工具函数 ==========
def generate_depart_name(prefix="Dept组织"):
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=11))
    return f"{prefix}_{suffix}"

def generate_initial_depart_code():
    while True:
        code = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        if any(c.isalpha() for c in code) and any(c.isdigit() for c in code):
            return code

def create_department(depart_name, parent_id, parent_code, depart_code):
    headers = {"departCode": str(depart_code)}
    body = {"departName": depart_name, "parentDepartId": parent_id}
    try:
        resp = session.post(API_URL, json=body, headers=headers, timeout=3)
        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {"error": str(e)}

def batch_create_departments(count):
    last_depart_code = generate_initial_depart_code()

    for i in range(count):
        depart_name = generate_depart_name()

        status_code, result = create_department(
            depart_name,
            PARENT_DEPART_ID,
            PARENT_DEPART_CODE,
            last_depart_code
        )

        print(f"[{i+1}/{count}] 创建部门: {depart_name}, departCode: {last_depart_code}, 状态码: {status_code}")
        print("响应内容:", result)

        if status_code == 200 and result.get("code") == "0":
            last_depart_code = result["data"]["departId"]
        else:
            print("创建失败，终止后续创建。")
            break

# ========== 执行 ==========
if __name__ == "__main__":
    batch_create_departments(CREATE_COUNT)



