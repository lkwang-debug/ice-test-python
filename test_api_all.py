#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 上午11:38
# @Author  : hzk
# @File    : test_api_all.py
# @Software: PyCharm


import inspect
import string
import random

import pytest
import allure
import json
import time
import sys
import types
import re
from typing import Dict, Any
from common.excel_utils import ExcelUtils
from method import (
    CompanyMethods,
    DeviceMethods,
    FileMethods,
    RoomMethods,
    UserMethods
)

# 新增：全局变量存储接口返回值，用于参数关联
GLOBAL_RESPONSE_CACHE = {}


class CaseGenerator:
    CLASS_MAPPING = {
        "company": CompanyMethods,
        "device": DeviceMethods,
        "file": FileMethods,
        "room": RoomMethods,
        "user": UserMethods
    }

    def __init__(self):
        self.excel_utils = ExcelUtils()
        print("\n=== 开始读取Excel用例 ===")
        self.test_cases = self.excel_utils.get_test_cases()
        self.method_instance_map = {}

    def generate_tests(self):
        for case in self.test_cases:
            func = self._create_test_function(case)
            print(f"生成测试函数: {func.__name__}")
            yield func

    def _create_test_function(self, case: Dict[str, Any]):
        def make_test_body():
            def real_func():
                methods = self._init_methods(case['class_name'])
                self._log_test_info(case)

                # 新增：处理参数关联
                processed_params = self._process_parameter_references(case.get('params', {}))
                case['params'] = processed_params

                result, elapsed = self._execute_api_call(methods, case)
                self._validate_result(case, result, elapsed)

                # 新增：缓存响应结果
                if 'save_response' in case:
                    self._cache_response(case['save_response'], result)

            return real_func

        func_name = self._generate_test_name(case)
        test_body = make_test_body()

        new_func = types.FunctionType(
            test_body.__code__,
            test_body.__globals__,
            name=func_name,
            argdefs=test_body.__defaults__,
            closure=test_body.__closure__
        )
        new_func.__dict__.update(test_body.__dict__)
        new_func.__module__ = __name__
        print(f"创建测试函数对象: {func_name}")
        return allure.title(f"{case['class_name']}.{case['method']} - {case['case_name']}")(new_func)

    """
    新增了GLOBAL_RESPONSE_CACHE全局变量，用于存储接口返回值
    新增了_process_parameter_references方法，用于处理参数中的变量引用
    新增了_replace_references_in_string方法，用于替换字符串中的变量引用
    新增了_cache_response方法，用于缓存接口响应结果
    在_create_test_function方法中增加了参数处理和结果缓存的逻辑
    
    使用说明：
    在Excel中新增一列save_response，用于指定要缓存的响应结果，格式为"class_name_method"或"lass_name_method as alias",如device_devRegister
    
    在参数中使用${class_name_method.response.field}格式引用缓存的值，例如：
    
    ${device_devRegister.response.devNodeId} 引用device_devRegister接口返回的devNodeId字段
    
    ${device_getNodeList.response.data.0.nodeId} 引用device_list接口返回的data数组第一个元素的deviceId字段
    """


    # 新增：处理参数关联
    def _process_parameter_references(self, params: Any) -> Any:
        """处理参数中的变量引用，格式为 ${previous_api.response.field}"""
        if isinstance(params, str):
            # 处理字符串中的变量引用
            return self._replace_references_in_string(params)
        elif isinstance(params, dict):
            # 递归处理字典
            return {k: self._process_parameter_references(v) for k, v in params.items()}
        elif isinstance(params, list):
            # 递归处理列表
            return [self._process_parameter_references(item) for item in params]
        return params

    # 新增：替换字符串中的变量引用
    def _replace_references_in_string(self, param_str: str) -> Any:
        """替换字符串中的变量引用，格式为 ${previous_api.response.field}"""

        if not isinstance(param_str, str) or '${' not in param_str:
            return param_str

            # 先处理随机字符串 ${RANDOM_STR[10]} 或 ${RANDOM_STR}
        """
        支持两种格式：
        ${RANDOM_STR}：默认生成8位随机字符串
        ${RANDOM_STR[10]}：生成指定长度的随机字符串
        使用示例：
        Excel中填写：{"token": "${RANDOM_STR}"}
        或：{"code": "TEST_${RANDOM_STR[6]}"}
        """

        def generate_random_str(match):
            length = int(match.group(1)) if match.group(1) else 8
            chars = string.ascii_letters + string.digits
            return ''.join(random.choices(chars, k=length))

        param_str = re.sub(
            r'\$\{RANDOM_STR(?:\[(\d+)\])?\}',
            generate_random_str,
            param_str
        )

        # 原有变量引用处理逻辑保持不变
        pattern = r'\$\{(.*?)\}'
        matches = re.findall(pattern, param_str)

        if not matches:
            return param_str

        for match in matches:
            try:
                parts = match.split('.')
                if len(parts) < 3 or parts[1] != 'response':
                    continue  # 跳过随机字符串标记

                api_name = parts[0]
                field_path = parts[2:]
                cached_value = GLOBAL_RESPONSE_CACHE.get(api_name)
                if cached_value is None:
                    raise ValueError(f"No cached response found for API: {api_name}")

                value = cached_value
                for field in field_path:
                    if isinstance(value, dict) and field in value:
                        value = value[field]
                    elif isinstance(value, list) and field.isdigit() and int(field) < len(value):
                        value = value[int(field)]
                    else:
                        raise ValueError(f"Field '{field}' not found in response from {api_name}")

                param_str = param_str.replace(f'${{{match}}}', str(value))
            except Exception as e:
                raise ValueError(f"Failed to process parameter reference '${{{match}}}': {str(e)}")

        try:
            return json.loads(param_str)
        except json.JSONDecodeError:
            return param_str




    # 新增：缓存响应结果
    def _cache_response(self, save_config: str, response: Dict[str, Any]):
        """缓存响应结果，供后续用例使用"""

        if not save_config:
            return

        try:

            parts = [p.strip() for p in save_config.split('as')]
            api_name = parts[0]
            GLOBAL_RESPONSE_CACHE[api_name] = response
            print(f"Cached response for API: {api_name}")
        except Exception as e:
            print(f"Failed to cache response: {str(e)}")

    # 其余原有方法保持不变...
    def _init_methods(self, class_name: str):
        class_name = class_name.lower()
        if class_name not in self.method_instance_map:
            method_class = self.CLASS_MAPPING.get(class_name)
            if not method_class:
                pytest.skip(f"未找到对应的测试类: {class_name}")
            self.method_instance_map[class_name] = method_class()
        return self.method_instance_map[class_name]

    def _log_test_info(self, case: Dict[str, Any]):
        with allure.step("测试信息"):
            allure.dynamic.description(f"测试类: {case['class_name']}\n测试方法: {case['method']}")
            allure.attach(json.dumps(case['params'], indent=2, ensure_ascii=False),
                          name="请求参数", attachment_type=allure.attachment_type.JSON)
            allure.attach(json.dumps(case['expected'], indent=2, ensure_ascii=False),
                          name="预期结果", attachment_type=allure.attachment_type.JSON)

    def _execute_api_call(self, methods, case):

        import json
        import time

        start_time = time.time()
        method_name = self._convert_method_name(case['method'])

        # 参数处理
        params = case.get('params', {})
        if params is None:
            params_obj = {}
        elif isinstance(params, str):
            try:
                params_obj = json.loads(params)
            except json.JSONDecodeError as e:
                print(f"[WARNING] params JSON解析失败: {e}, 原始内容: {params}")
                params_obj = params  # 保持原样传入接口
        elif isinstance(params, dict):
            params_obj = params
        else:
            raise TypeError(f"params类型异常，期望str或dict或None，实际是: {type(params)}")

        # 调用方法
        try:
            method = getattr(methods, method_name)
            result = method(params_obj)
        except Exception as e:
            print(f"[ERROR] 接口调用异常: {e}")
            result = {"resultCode": -999, "message": str(e)}

        # 调试信息（新增）
        print(f"\n[DEBUG] {case['class_name']}.{case['method']} 响应: {result}")

        elapsed = (time.time() - start_time) * 1000  # 毫秒
        allure.attach(json.dumps({
            "actual_result": result,
            "elapsed_ms": elapsed,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }, indent=2, ensure_ascii=False), name="实际结果", attachment_type=allure.attachment_type.JSON)

        return result, elapsed

    def _validate_result(self, case, result, elapsed):
        with allure.step("结果验证"):
            expected_code = case['expected'].get('resultCode', 0)
            actual_code = result.get('resultCode', -1)

            assert actual_code == expected_code, f"预期 resultCode: {expected_code}, 实际: {actual_code}"

            if case.get('partial_validation', False):
                expected_without_code = {k: v for k, v in case['expected'].items() if k != 'resultCode'}
                actual_without_code = {k: v for k, v in result.items() if k != 'resultCode'}
                self._validate_partial_data(expected_without_code, actual_without_code)
            elif 'data' in case['expected']:
                expected_without_code = {k: v for k, v in case['expected'].items() if k != 'resultCode'}
                actual_without_code = {k: v for k, v in result.items() if k != 'resultCode'}
                self._assert_full_data(expected_without_code, actual_without_code)

    def _validate_partial_data(self, expected: Dict[str, Any], actual: Dict[str, Any]):
        """
        宽松字段匹配，只校验 expected 中 key=value 是否在实际返回中任意位置存在。
        """
        for key, expected_value in expected.items():
            found = self._search_key_value(actual, key, expected_value)
            assert found, f"未找到字段 {key}={expected_value} 的匹配"

    def _search_key_value(self, obj: Any, key: str, value: Any) -> bool:
        """
            递归搜索目标字段 key 是否存在，并且：
            - 如果 value == "!null"，则检查字段存在且非空
            - 否则检查字段值是否匹配
            """
        if isinstance(obj, dict):
            if key in obj:
                if value == "!null":
                    # 检查字段存在且非空（非None、非空字符串、非空列表等）
                    return obj[key] is not None and obj[key] != ""
                else:
                    return obj[key] == value
            return any(self._search_key_value(v, key, value) for v in obj.values())
        elif isinstance(obj, list):
            return any(self._search_key_value(item, key, value) for item in obj)
        return False

        # """
        # 递归搜索目标字段 key 是否存在，并且值等于 value
        # """
        # if isinstance(obj, dict):
        #     if key in obj and obj[key] == value:
        #         return True
        #     return any(self._search_key_value(v, key, value) for v in obj.values())
        # elif isinstance(obj, list):
        #     return any(self._search_key_value(item, key, value) for item in obj)
        # return False

    def _assert_full_data(self, expected, actual):
        assert actual == expected, (
            f"数据验证失败\n预期:\n{json.dumps(expected, indent=2, ensure_ascii=False)}\n"
            f"实际:\n{json.dumps(actual, indent=2, ensure_ascii=False)}"
        )

    def _convert_method_name(self, method):
        """
            将驼峰转为蛇形，同时提供自定义映射修正
            """
        # 1. 去除首尾空格
        method = str(method).strip()

        # 2. 自定义修正映射
        manual_map = {
            "devUnRegister": "dev_unregister",
            "getCDNInfo": "get_cdn_info",  # 明确指定特殊转换
            "getRcsAddress": "get_rcs_address",
            # 其他特殊映射...
        }
        if method in manual_map:
            return manual_map[method]

        # 3. 改进的驼峰转蛇形逻辑
        # 处理连续大写字母（如CDN）
        s1 = re.sub('([A-Z]+)([A-Z][a-z])', r'\1_\2', method)
        # 处理普通驼峰
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()


        # # 1. 首先去除首尾空格
        # method = str(method).strip()
        #
        # # 自定义修正映射（比如 devUnRegister → dev_unregister）
        # manual_map = {
        #     "devUnRegister": "dev_unregister",
        #     # 如有其他接口也不规范，可继续在这里补充
        # }
        # if method in manual_map:
        #     return manual_map[method]
        #
        # # 默认驼峰转蛇形
        # return ''.join(['_' + c.lower() if c.isupper() else c for c in method]).lstrip('_')

    def _generate_test_name(self, case):
        base = f"test_{case['class_name'].lower()}_{case['method'].lower()}"
        name = case['case_name'].replace(" ", "_").replace("-", "_")
        return f"{base}_{name}"[:120]


# === 清理全局残留 test_ 函数（含 test_func） ===
print("=== 清理全局残留 test_ 函数（含 test_func） ===")
for name in list(globals().keys()):
    if name.startswith("test_") and callable(globals()[name]):
        print(f"→ 移除旧函数: {name}")
        del globals()[name]

# === 注册动态生成的测试函数 ===
generator = CaseGenerator()
for dyn_func in generator.generate_tests():  # 使用非 test_ 前缀变量名
    dyn_func_name = dyn_func.__name__
    setattr(sys.modules[__name__], dyn_func_name, dyn_func)

# === 最终模块 test_ 函数检查 ===
print("=== 模块最终包含的 test_ 函数 ===")
for name in sorted(globals()):
    if name.startswith("test_") and callable(globals()[name]):
        print(f"pytest 将收集: {name} → 类型: {type(globals()[name])}")

# import inspect
# import pytest
# import allure
# import json
# import time
# import sys
# import types
# from typing import Dict, Any
# from common.excel_utils import ExcelUtils
# from method import (
#     CompanyMethods,
#     DeviceMethods,
#     FileMethods,
#     RoomMethods,
#     UserMethods
# )
#
#
# class CaseGenerator:
#     CLASS_MAPPING = {
#         "company": CompanyMethods,
#         "device": DeviceMethods,
#         "file": FileMethods,
#         "room": RoomMethods,
#         "user": UserMethods
#     }
#
#     def __init__(self):
#         self.excel_utils = ExcelUtils()
#         print("\n=== 开始读取Excel用例 ===")
#         self.test_cases = self.excel_utils.get_test_cases()
#         self.method_instance_map = {}
#
#     def generate_tests(self):
#         for case in self.test_cases:
#             func = self._create_test_function(case)
#             print(f"生成测试函数: {func.__name__}")
#             yield func
#
#     def _create_test_function(self, case: Dict[str, Any]):
#         def make_test_body():
#             def real_func():
#                 methods = self._init_methods(case['class_name'])
#                 self._log_test_info(case)
#                 result, elapsed = self._execute_api_call(methods, case)
#                 self._validate_result(case, result, elapsed)
#             return real_func
#
#         func_name = self._generate_test_name(case)
#         test_body = make_test_body()
#
#         new_func = types.FunctionType(
#             test_body.__code__,
#             test_body.__globals__,
#             name=func_name,
#             argdefs=test_body.__defaults__,
#             closure=test_body.__closure__
#         )
#         new_func.__dict__.update(test_body.__dict__)
#         new_func.__module__ = __name__
#         print(f"创建测试函数对象: {func_name}")
#         return allure.title(f"{case['class_name']}.{case['method']} - {case['case_name']}")(new_func)
#
#     def _init_methods(self, class_name: str):
#         class_name = class_name.lower()
#         if class_name not in self.method_instance_map:
#             method_class = self.CLASS_MAPPING.get(class_name)
#             if not method_class:
#                 pytest.skip(f"未找到对应的测试类: {class_name}")
#             self.method_instance_map[class_name] = method_class()
#         return self.method_instance_map[class_name]
#
#     def _log_test_info(self, case: Dict[str, Any]):
#         with allure.step("测试信息"):
#             allure.dynamic.description(f"测试类: {case['class_name']}\n测试方法: {case['method']}")
#             allure.attach(json.dumps(case['params'], indent=2, ensure_ascii=False),
#                           name="请求参数", attachment_type=allure.attachment_type.JSON)
#             allure.attach(json.dumps(case['expected'], indent=2, ensure_ascii=False),
#                           name="预期结果", attachment_type=allure.attachment_type.JSON)
#
#     def _execute_api_call(self, methods, case):
#
#         import json
#         import time
#
#         start_time = time.time()
#         method_name = self._convert_method_name(case['method'])
#
#         # 参数处理
#         params = case.get('params', {})
#         if params is None:
#             params_obj = {}
#         elif isinstance(params, str):
#             try:
#                 params_obj = json.loads(params)
#             except json.JSONDecodeError as e:
#                 print(f"[WARNING] params JSON解析失败: {e}, 原始内容: {params}")
#                 params_obj = params  # 保持原样传入接口
#         elif isinstance(params, dict):
#             params_obj = params
#         else:
#             raise TypeError(f"params类型异常，期望str或dict或None，实际是: {type(params)}")
#
#         # 调用方法
#         try:
#             method = getattr(methods, method_name)
#             result = method(params_obj)
#         except Exception as e:
#             print(f"[ERROR] 接口调用异常: {e}")
#             result = {"resultCode": -999, "message": str(e)}
#
#         # 调试信息（新增）
#         print(f"\n[DEBUG] {case['class_name']}.{case['method']} 响应: {result}")
#
#         elapsed = (time.time() - start_time) * 1000  # 毫秒
#         allure.attach(json.dumps({
#             "actual_result": result,
#             "elapsed_ms": elapsed,
#             "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
#         }, indent=2, ensure_ascii=False), name="实际结果", attachment_type=allure.attachment_type.JSON)
#
#         return result, elapsed
#
#
#
#     def _validate_result(self, case, result, elapsed):
#
#
#         with allure.step("结果验证"):
#             expected_code = case['expected'].get('resultCode', 0)
#             actual_code = result.get('resultCode', -1)
#
#             assert actual_code == expected_code, f"预期 resultCode: {expected_code}, 实际: {actual_code}"
#
#             if case.get('partial_validation', False):
#                 expected_without_code = {k: v for k, v in case['expected'].items() if k != 'resultCode'}
#                 actual_without_code = {k: v for k, v in result.items() if k != 'resultCode'}
#                 self._validate_partial_data(expected_without_code, actual_without_code)
#             elif 'data' in case['expected']:
#                 expected_without_code = {k: v for k, v in case['expected'].items() if k != 'resultCode'}
#                 actual_without_code = {k: v for k, v in result.items() if k != 'resultCode'}
#                 self._assert_full_data(expected_without_code, actual_without_code)
#
#
#     def _validate_partial_data(self, expected: Dict[str, Any], actual: Dict[str, Any]):
#         """
#         宽松字段匹配，只校验 expected 中 key=value 是否在实际返回中任意位置存在。
#         """
#         for key, expected_value in expected.items():
#             found = self._search_key_value(actual, key, expected_value)
#             assert found, f"未找到字段 {key}={expected_value} 的匹配"
#
#     def _search_key_value(self, obj: Any, key: str, value: Any) -> bool:
#         """
#         递归搜索目标字段 key 是否存在，并且值等于 value
#         """
#         if isinstance(obj, dict):
#             if key in obj and obj[key] == value:
#                 return True
#             return any(self._search_key_value(v, key, value) for v in obj.values())
#         elif isinstance(obj, list):
#             return any(self._search_key_value(item, key, value) for item in obj)
#         return False
#
#     def _assert_full_data(self, expected, actual):
#         assert actual == expected, (
#             f"数据验证失败\n预期:\n{json.dumps(expected, indent=2, ensure_ascii=False)}\n"
#             f"实际:\n{json.dumps(actual, indent=2, ensure_ascii=False)}"
#         )
#
#     def _convert_method_name(self, method):
#         """
#             将驼峰转为蛇形，同时提供自定义映射修正
#             """
#         # 自定义修正映射（比如 devUnRegister → dev_unregister）
#         manual_map = {
#             "devUnRegister": "dev_unregister",
#             # 如有其他接口也不规范，可继续在这里补充
#         }
#         if method in manual_map:
#             return manual_map[method]
#
#         # 默认驼峰转蛇形
#         return ''.join(['_' + c.lower() if c.isupper() else c for c in method]).lstrip('_')
#         #return ''.join(['_' + c.lower() if c.isupper() else c for c in method]).lstrip('_')
#
#     def _generate_test_name(self, case):
#         base = f"test_{case['class_name'].lower()}_{case['method'].lower()}"
#         name = case['case_name'].replace(" ", "_").replace("-", "_")
#         return f"{base}_{name}"[:120]
#
#
# # === 清理全局残留 test_ 函数（含 test_func） ===
# print("=== 清理全局残留 test_ 函数（含 test_func） ===")
# for name in list(globals().keys()):
#     if name.startswith("test_") and callable(globals()[name]):
#         print(f"→ 移除旧函数: {name}")
#         del globals()[name]
#
# # === 注册动态生成的测试函数 ===
# #print("=== 注册动态生成的测试函数 ===")
# generator = CaseGenerator()
# for dyn_func in generator.generate_tests():  # 使用非 test_ 前缀变量名
#     dyn_func_name = dyn_func.__name__
#     #print(f"注册函数: {dyn_func_name}")
#     setattr(sys.modules[__name__], dyn_func_name, dyn_func)
#
# # === 最终模块 test_ 函数检查 ===
# print("=== 模块最终包含的 test_ 函数 ===")
# for name in sorted(globals()):
#     if name.startswith("test_") and callable(globals()[name]):
#         print(f"pytest 将收集: {name} → 类型: {type(globals()[name])}")









