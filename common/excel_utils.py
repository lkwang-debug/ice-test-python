#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 上午11:38
# @Author  : hzk
# @File    : excel_utils.py
# @Software: PyCharm
import allure
from openpyxl import load_workbook
import json
from pathlib import Path
import logging
from common.config import EXCEL_CONFIG
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ExcelUtils:
    """Excel操作工具类，支持按类名分sheet的测试用例读取"""

    def __init__(self):
        self.file_path = Path(EXCEL_CONFIG["file_path"])
        self.wb = None
        self._validate_file()
        self._open_workbook()
        self.skipped_count = 0  # 新增：记录跳过的用例数
        self.error_count = 0  # 新增：记录出错的用例数

    def _validate_file(self) -> None:
        """验证Excel文件是否存在且格式正确"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Excel文件不存在: {self.file_path}")
        if self.file_path.suffix not in ('.xlsx', '.xlsm'):
            raise ValueError("只支持.xlsx或.xlsm格式的Excel文件")

    def _open_workbook(self) -> None:
        """打开工作簿"""
        try:
            self.wb = load_workbook(self.file_path, read_only=False, data_only=True)
            logger.info(f"成功打开Excel文件: {self.file_path}")
        except Exception as e:
            logger.error(f"打开Excel文件失败: {e}")
            raise

    def get_test_cases(self) -> List[Dict[str, Any]]:
        """
        获取所有测试用例（从所有class_name对应的sheet中）
        返回: 测试用例列表，每个用例为字典格式
        """
        print("\n=== 开始读取Excel用例 ===")

        cases = []
        total_rows = 0  # 新增：记录总行数

        for sheet_name in self.wb.sheetnames:
            if sheet_name.lower() in ['summary', 'config', '说明']:
                continue  # 跳过非测试用例sheet

            sheet = self.wb[sheet_name]

            try:
                headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]

                for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                    total_rows += 1
                    if not any(row):
                        continue  # 跳过空行

                    try:
                        case = {headers[i]: val for i, val in enumerate(row) if i < len(headers)}
                        case['class_name'] = sheet_name  # 使用sheet名作为class_name

                        # 处理auto字段
                        auto_val = str(case.get('auto', '')).lower().strip()
                        if auto_val == 'false':
                            self.skipped_count += 1

                            continue

                        # 处理JSON字段（增强容错）
                        case["params"] = self._safe_parse_json(case.get("params"), "params", row_num)
                        case["expected"] = self._safe_parse_json(case.get("expected"), "expected", row_num)

                        # 检查必要字段
                        self._validate_case_fields(case, row_num)

                        cases.append(case)


                    except Exception as e:
                        self.error_count += 1
                        print(f"行{row_num}处理失败: {str(e)}")
                        continue  # 继续处理下一行

            except Exception as e:
                print(f"工作表 {sheet_name} 处理出错: {str(e)}")
                continue  # 继续处理下一个工作表

        print(f"\n=== 统计 ===")
        print(f"有效用例: {len(cases)}")
        print(f"跳过用例(auto=false): {self.skipped_count}")
        print(f"错误用例: {self.error_count}")
        print(f"=== 共读取到{len(cases)}条有效用例 ===")
        return cases

    def _validate_case_fields(self, case: Dict[str, Any], row_num: int) -> None:

        """验证用例必填字段，允许params为null或空字典"""
        required_fields = ['method', 'case_name', 'expected']  # 移除了params
        for field in required_fields:
            if field not in case or case[field] is None:
                raise ValueError(f"行{row_num}缺少必要字段'{field}'")

        # 特殊处理params字段
        if 'params' not in case:
            case['params'] = {}  # 如果完全不存在，赋默认值空字典


    def _safe_parse_json(self, value: Any, field_name: str, row_num: int) -> Any:
        """
        安全解析JSON字段（新增方法）
        1. 空值处理
        2. 已经是dict/list直接返回
        3. 字符串尝试解析
        4. 其他类型转为字符串
        5. 允许params字段传null或空字符串时自动转为{}
        """
        if value is None or value == "":
            return {} if field_name == "params" else None  # 关键修改：处理空字符串

        if isinstance(value, (dict, list)):
            return value

        try:
            if isinstance(value, str):
                return json.loads(value.strip())
            return str(value)
        except json.JSONDecodeError as e:
            error_msg = f"行{row_num} {field_name} JSON解析错误: {str(e)} | 原始内容: {str(value)[:100]}"
            print(f"{error_msg}")
            allure.attach(error_msg, name="JSON解析错误", attachment_type=allure.attachment_type.TEXT)
            return value



    # 保留其他原有方法...
    def write_result(self, row_num: int, result: str, status: str = None) -> None:
        """写入测试结果（保持不变）"""
        pass

    def close(self) -> None:
        """关闭工作簿（保持不变）"""
        if self.wb:
            self.wb.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    with ExcelUtils() as excel:
        cases = excel.get_test_cases()
        print(f"\n前3条用例示例:")
        for case in cases[:3]:
            print(case)


# from openpyxl import load_workbook
# import json
# from pathlib import Path
# import logging
# from common.config import EXCEL_CONFIG
# from typing import List, Dict, Any, Optional
#
# logger = logging.getLogger(__name__)
#
#
# class ExcelUtils:
#     """Excel操作工具类，支持按类名分sheet的测试用例读取"""
#
#     def __init__(self):
#         self.file_path = Path(EXCEL_CONFIG["file_path"])
#         self.wb = None
#         self._validate_file()
#         self._open_workbook()
#
#     def _validate_file(self) -> None:
#         """验证Excel文件是否存在且格式正确"""
#         if not self.file_path.exists():
#             raise FileNotFoundError(f"Excel文件不存在: {self.file_path}")
#         if self.file_path.suffix not in ('.xlsx', '.xlsm'):
#             raise ValueError("只支持.xlsx或.xlsm格式的Excel文件")
#
#     def _open_workbook(self) -> None:
#         """打开工作簿"""
#         try:
#             self.wb = load_workbook(self.file_path, read_only=False, data_only=True)
#             logger.info(f"成功打开Excel文件: {self.file_path}")
#         except Exception as e:
#             logger.error(f"打开Excel文件失败: {e}")
#             raise
#
#     def get_test_cases(self) -> List[Dict[str, Any]]:
#         """
#         获取所有测试用例（从所有class_name对应的sheet中）
#         返回: 测试用例列表，每个用例为字典格式
#         """
#         print("\n=== 开始读取Excel用例 ===")
#         print(f"可用工作表: {self.wb.sheetnames}")
#
#         cases = []
#         for sheet_name in self.wb.sheetnames:
#             if sheet_name.lower() in ['summary', 'config', '说明']:
#                 continue  # 跳过非测试用例sheet
#
#             sheet = self.wb[sheet_name]
#             print(f"\n正在读取工作表: {sheet_name}")
#
#             try:
#                 headers = [cell.value for cell in sheet[1]]
#                 print(f"表头: {headers}")
#
#                 for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
#                     if not any(row):
#                         continue  # 跳过空行
#
#                     case = dict(zip(headers, row))
#                     case['class_name'] = sheet_name  # 使用sheet名作为class_name
#
#                     auto_value = str(case.get('auto', '')).strip().lower()
#                     if auto_value == 'false':
#                         print(f"跳过用例（auto=false）: {case.get('case_name')}")
#                         continue
#
#                     self._process_case(case, row_num)
#                     cases.append(case)
#                     print(f"添加用例: {case['case_name']}")
#
#             except Exception as e:
#                 print(f"读取工作表 {sheet_name} 出错: {str(e)}")
#                 continue
#
#         print(f"\n=== 共读取到{len(cases)}条用例 ===")
#         return cases
#
#     def _process_case(self, case: Dict[str, Any], row_num: int) -> None:
#         """处理单个测试用例的数据（保持不变）"""
#         # 检查必要字段
#         required_fields = ['method', 'case_name', 'params', 'expected']
#         for field in required_fields:
#             if field not in case:
#                 raise ValueError(f"行{row_num}缺少必要字段'{field}'")
#
#         # 处理JSON字段
#         case["params"] = self._parse_json_field(case["params"], "params", row_num)
#         case["expected"] = self._parse_json_field(case["expected"], "expected", row_num)
#
#         # 处理部分验证标记
#         if isinstance(case["expected"], dict) and "partial_validation" in case["expected"]:
#             case["partial_validation"] = case["expected"].pop("partial_validation")
#
#         # 清理字符串字段
#         for key in ['method', 'case_name']:
#             if case.get(key):
#                 case[key] = str(case[key]).strip()
#
#         if 'auto' in case:
#             case['auto'] = str(case['auto']).lower() == 'true'
#
#     def _parse_json_field(self, value: Any, field_name: str, row_num: int) -> Any:
#         """解析JSON格式的字段（保持不变）"""
#         if not value:
#             return {} if field_name == "params" else None
#
#         try:
#             if isinstance(value, str):
#                 return json.loads(value)
#             elif isinstance(value, (dict, list)):
#                 return value
#             else:
#                 raise ValueError(f"行{row_num} {field_name}字段格式不支持")
#         except json.JSONDecodeError as e:
#             raise ValueError(f"行{row_num} {field_name} JSON解析错误: {e}")




