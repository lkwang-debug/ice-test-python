#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/10/20 下午6:19
# @Author  : hzk
# @File    : terminal_create_biaopin.py
# @Software: PyCharm


import requests
import random
import string
import time
import concurrent.futures


def create_batch_terminals():
    """批量创建终端，确保序列号不重复"""
    base_url = "http://118.145.212.178:28080/serv/v1/terminal/add"
    token = "5617d4d4mcl98damcl488dmcl949fmclbacba9d93d9a1761030715524"

    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'Token': token,
        "Referer": "http://118.145.212.178:28080/"
    }

    # 预生成所有终端数据，确保序列号不重复
    print("正在生成终端数据...")
    used_seq_nums = set()
    terminals_data = []

    for i in range(5000):
        # 生成唯一序列号
        while True:
            seq_num = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            if seq_num not in used_seq_nums:
                used_seq_nums.add(seq_num)
                break

        # 生成随机名称
        random_letters = ''.join(random.choices(string.ascii_letters, k=4))
        random_digits = ''.join(random.choices(string.digits, k=4))
        name = f"终端_{random_letters}{random_digits}"

        terminal_data = {
            "name": name,
            "seqNum": seq_num,
            "departId": 1,
            "position": "",
            "remark": "",
            "logLevel": 10,
            "external": 0
        }
        terminals_data.append(terminal_data)

    print("终端数据生成完成，开始批量创建...")

    def create_single_terminal(terminal_data, index):
        """创建单个终端"""
        try:
            response = requests.post(base_url, headers=headers, json=terminal_data, timeout=10)

            if response.status_code == 200:
                print(f"成功创建第 {index + 1} 个终端: {terminal_data['name']}")
                return True
            else:
                print(f"失败第 {index + 1} 个终端: {response.status_code}")
                return False
        except Exception as e:
            print(f"异常第 {index + 1} 个终端: {str(e)}")
            return False

    success_count = 0
    failed_count = 0

    # 使用线程池并发执行，50个并发线程
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        # 提交所有任务
        futures = []
        for i, terminal_data in enumerate(terminals_data):
            future = executor.submit(create_single_terminal, terminal_data, i)
            futures.append(future)

        # 收集结果
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1
            else:
                failed_count += 1

    end_time = time.time()

    print(f"\n批量创建完成!")
    print(f"总耗时: {end_time - start_time:.2f} 秒")
    print(f"成功: {success_count}, 失败: {failed_count}")


# 执行批量创建
if __name__ == "__main__":
    create_batch_terminals()