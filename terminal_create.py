#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/8/20 下午6:33
# @Author  : hzk
# @File    : terminal_create.py.py
# @Software: PyCharm

import requests
import random
import string
import json


def generate_random_terminal_data(count):
    """生成随机终端数据"""
    terminals = []
    for i in range(1, count + 1):
        # 生成5位随机数字
        random_digits = ''.join(random.choices(string.digits, k=5))
        name = f"hunan终端-{random_digits}"

        # 生成11位随机字符串（小写字母+数字）
        seq_num_chars = string.ascii_lowercase + string.digits
        seq_num = ''.join(random.choices(seq_num_chars, k=11))

        terminals.append({
            "name": name,
            "seqNum": seq_num,
            "stationId": "2022"  # 默认填0
        })

    return terminals


def send_terminal_data(terminals):
    """发送终端数据到接口"""
    url = "https://XJ.haoshitong.com:28443/api/v1/data/sync"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "eyJhbGciOiAiU0hBMjU2In0=.eyJrZXkiOiAiYmY0YjgyMTMiLCAidGltZXN0YW1wIjogMS43NjI5MjcxNTA5MWUrMTJ9.55f4d653e33a22bc29f570b5b0e11b1ffecdc8b82c3357b0f76c02caeb604882"
    }

    payload = {
        "object": "TERMINAL",
        "method": "UPSERT",
        "data": terminals
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()

        print(f"请求成功！状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误响应: {e.response.text}")
        return False


def main():
    """主函数"""
    try:
        # 获取要创建的终端数量
        count = int(input("请输入要创建的终端数量: "))
        if count <= 0:
            print("数量必须大于0")
            return

        # 生成终端数据
        print(f"正在生成 {count} 个终端数据...")
        terminals = generate_random_terminal_data(count)

        # 显示部分生成的终端数据（前5个）
        print("\n生成的终端数据示例（前5个）:")
        for i, terminal in enumerate(terminals[:5], 1):
            print(f"{i}. 名称: {terminal['name']}, 序列号: {terminal['seqNum']}, 站点ID: {terminal['stationId']}")

        if count > 5:
            print("...（其余省略）")

        # 确认是否发送
        confirm = input("\n是否发送这些数据？(y/n): ").lower()
        if confirm != 'y':
            print("操作已取消")
            return

        # 发送数据
        print("正在发送数据...")
        success = send_terminal_data(terminals)

        if success:
            print(f"成功发送 {count} 个终端数据！")
        else:
            print("发送失败，请检查网络连接或服务器状态")

    except ValueError:
        print("请输入有效的数字！")
    except KeyboardInterrupt:
        print("\n操作被用户中断")
    except Exception as e:
        print(f"发生未知错误: {e}")


if __name__ == "__main__":
    main()
