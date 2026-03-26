#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/8/21 上午10:44
# @Author  : hzk
# @File    : edit_station_data.py
# @Software: PyCharm


import requests
import random
import time
import json
import os


class StationCreator:
    def __init__(self, base_url, auth_token, id_file="last_station_id.json"):
        self.base_url = base_url
        self.auth_token = auth_token
        self.id_file = id_file
        self.last_station_id = self.load_last_id()

    def load_last_id(self):
        """从文件加载最后使用的stationId"""
        if os.path.exists(self.id_file):
            try:
                with open(self.id_file, 'r') as f:
                    data = json.load(f)
                    return data.get('last_station_id', 0)
            except:
                return 0
        return 0

    def save_last_id(self):
        """保存最后使用的stationId到文件"""
        data = {'last_station_id': self.last_station_id}
        with open(self.id_file, 'w') as f:
            json.dump(data, f)

    def generate_station_data(self, depart_code, count):
        """生成指定数量的站点数据"""
        stations = []
        for i in range(count):
            self.last_station_id += 1
            station_id = self.last_station_id

            # 根据stationId范围设置不同的名称格式
            if 3000 <= station_id <= 4000:
                name = f"交付{station_id}"
            else:
                name = f"武汉站点数据{random.randint(1000000, 9999999)}"

            station = {
                "stationId": str(station_id),
                "name": name,
                "type": 3,
                "departCode": str(depart_code)
            }
            stations.append(station)
        return stations

    def send_station_data(self, stations):
        """发送站点数据到API"""
        url = f"{self.base_url}/api/v1/data/sync"
        headers = {
            "Content-Type": "application/json",
            "Authorization": self.auth_token
        }

        payload = {
            "object": "STATION",
            "method": "UPSERT",
            "data": stations
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()
            print(f"✓ 成功发送 {len(stations)} 个站点数据")
            print(f"  ID范围: {stations[0]['stationId']}-{stations[-1]['stationId']}")

            # 显示特殊命名的站点信息
            special_named = [s for s in stations if 3000 <= int(s['stationId']) <= 4000]
            if special_named:
                print(f"  特殊命名站点: {len(special_named)} 个 (交付3000-交付4000格式)")

            return True
        except requests.exceptions.RequestException as e:
            print(f"✗ 发送数据失败: {e}")
            return False

    def batch_create_stations(self, depart_code, total_count, batch_size=50):
        """为指定部门批量创建站点"""
        print(f"开始为部门 {depart_code} 创建 {total_count} 个站点...")
        print(f"当前起始ID: {self.last_station_id + 1}")

        for batch_num in range(0, total_count, batch_size):
            current_batch_size = min(batch_size, total_count - batch_num)

            # 生成当前批次的站点数据
            stations = self.generate_station_data(depart_code, current_batch_size)

            # 显示进度
            progress = min(batch_num + batch_size, total_count)
            print(f"\n[{progress}/{total_count}] 发送第 {batch_num // batch_size + 1} 批数据...")

            # 发送当前批次的数据
            success = self.send_station_data(stations)

            if not success:
                print("发送失败，停止执行")
                break

            # 保存当前ID状态
            self.save_last_id()

            # 添加延迟
            time.sleep(0.5)

        print(f"\n部门 {depart_code} 的站点创建完成！")
        print(f"最后使用的ID: {self.last_station_id}")


def main():
    # 配置参数
    BASE_URL = "http://192.168.6.150:28080"
    AUTH_TOKEN = "eyJhbGciOiAiU0hBMjU2In0=.eyJrZXkiOiAiYmY0YjgyMTMiLCAidGltZXN0YW1wIjogMS43NTU3NjYxOTQxZSsxMn0=.350c938c5bb4072ef4442788b804fe7a9c48e368b12b7d734648c151ad7738cc"

    # 创建站点生成器实例
    creator = StationCreator(BASE_URL, AUTH_TOKEN, "station_ids.json")

    # 第一次请求：部门1，1000个站点
    creator.batch_create_stations(depart_code=2, total_count=500, batch_size=100)

    # 第二次请求：部门2，1000个站点
    # creator.batch_create_stations(depart_code=11, total_count=1000, batch_size=100)


if __name__ == "__main__":
    main()