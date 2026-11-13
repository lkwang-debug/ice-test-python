#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19
# @Author  : hzk
# @File    : ice_client.py
import os
import sys
import json
import time
import logging
import Ice
import allure
from pathlib import Path
from typing import Dict, Any

# Ensure generated ICE packages are importable outside pytest/conftest too.
project_root = Path(__file__).parent.parent.resolve()
generated_dir = project_root / "generated"
for path in (str(project_root), str(generated_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from generated.com.hst.proxy.service.common import CommonService as common_service
#print("DEBUG: CommonService 是否有 _op_invoke：", hasattr(common_service.CommonService, "_op_invoke"))





from common.config import ICE_CONFIG
from common.gateway_response import GatewayResult, decode_response
from common.evidence import redact


# 设置路径：插入 generated 的上一级目录（项目根目录）
project_root = Path(__file__).parent.parent.resolve()
#print("冰路径插入前 sys.path[0]:", sys.path[0])
sys.path.insert(0, str(project_root))
#print("项目根路径已插入:", project_root)

# 打印前几项验证效果
#print("当前 sys.path[0:3]:", sys.path[0], sys.path[1], sys.path[2])


#print("==== DEBUG: sys.path ====")
# for p in sys.path:
#     print(p)
#print("=========================")

common_model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../generated/com/hst/proxy/model/CommonModel.py"))
#print(f"==== DEBUG: Checking CommonModel.py at: {common_model_path}")
#print("Exists:", os.path.exists(common_model_path))

# 导入 ICE 编译生成的模块
try:
    from generated.com.hst.proxy.service.common.CommonService import CommonServicePrx
    from generated.com.hst.proxy.model.CommonModel import Request, Response

except ImportError as e:
    raise ImportError(
        "ICE类型导入失败，请确认：\n"
        "1. 已运行 compile_ice.py 编译 ICE 文件\n"
        "2. generated 目录结构完整，并包含 __init__.py\n"
        "3. sys.path 中包含项目根目录\n"
        f"原始错误: {e}"
    )

logger = logging.getLogger(__name__)


CONNECT_FAIL_HINT = """
============================================================
 ICE 连接失败。请依次确认：
   1) IceDBProxy 服务器是否已开通端口 20801/tcp 与 22000/tcp：
        firewall-cmd --zone=public --add-port=20801/tcp --permanent
        firewall-cmd --zone=public --add-port=22000/tcp --permanent
        firewall-cmd --reload
   2) common/config.py 的 host / locator_port 是否指向正确的服务器
   3) 本机到该服务器的网络是否可达
 注意：端口不通不会报"端口"相关的错，只表现为连接失败，
       很容易被误判成接口本身有问题。
============================================================"""


class IceClient:
    """ICE客户端封装类"""

    def __init__(self):
        self.locator = ICE_CONFIG["locator"]
        self.service = ICE_CONFIG["service"]
        self.adapter = ICE_CONFIG["adapter"]
        self.communicator = None
        self.proxy = None
        self._connected = False

    def connect(self) -> bool:
        """建立连接"""

        """建立ICE连接

            移除原有的业务接口测试调用，改为基础连接验证
            确保不会触发服务端的NullPointerException

            Returns:
                bool: 连接是否成功建立
            """
        if self._connected:
            logger.debug("ICE连接已存在，跳过重复连接")
            return True

        try:
            # 1. 初始化通信器
            logger.info("正在初始化ICE通信器...")
            props = Ice.createProperties()
            props.setProperty("Ice.Default.Locator", self.locator)
            props.setProperty("Ice.MessageSizeMax", "20480")  # 保持原有配置



            init_data = Ice.InitializationData()
            init_data.properties = props

            self.communicator = Ice.initialize(init_data)
            logger.debug("ICE通信器初始化完成，版本: %s", Ice.stringVersion())

            # 2. 创建代理对象
            proxy_str = f"{self.service}@{self.adapter}"
            logger.debug("正在创建代理: %s", proxy_str)

            base = self.communicator.stringToProxy(proxy_str)
            self.proxy = CommonServicePrx.checkedCast(base)

            if not self.proxy:
                logger.error("代理转换失败，checkedCast返回None")
                raise RuntimeError("无法获取有效服务代理")

            # 3. 基础验证（不再调用_test_connection）
            logger.debug("执行基础代理验证...")
            if self.proxy.ice_isA("::Ice::Object"):  # 最基础的类型检查
                self._connected = True
                logger.info("ICE连接建立成功")
                return True

            logger.error("代理类型验证失败")
            return False

        except Ice.Exception as e:
            logger.error("ICE连接异常: %s", e, exc_info=True)
            self._log_ice_error(e)
            self._log_connect_hint()
            self._cleanup()
            return False
        except Exception as e:
            logger.error("连接发生未知异常: %s", e, exc_info=True)
            self._log_connect_hint()
            self._cleanup()
            return False

    def _log_connect_hint(self):
        """连接失败时补一条可操作的排查指引。

        原行为是连接失败只记一行日志、返回 False，下游每条用例变成
        resultCode: -999 —— 用例全红却看不出真正原因是端口不通。
        这里只把提示补进日志和报告，connect() 的返回值契约保持不变
        （method.py 里所有 BaseMethods.__init__ 都依赖它返回 bool）。
        """
        msg = f"{CONNECT_FAIL_HINT}\n  当前 locator: {self.locator}"
        logger.error(msg)
        allure.attach(msg, name="连接失败排查指引",
                      attachment_type=allure.attachment_type.TEXT)



    def _cleanup(self):
        """Release partial ICE connection state after a failed connect."""
        self.disconnect()

    def _test_connection(self):
        """发送 ping 请求测试连接"""
        """安全的基础连接测试（使用ICE内置ping机制）

           不再调用可能触发服务端异常的业务接口，改为使用ICE协议层的ping机制
           仅验证网络连通性和代理有效性，不会触发服务端业务逻辑

           Raises:
               ConnectionError: 当基础连接测试失败时抛出
           """
        try:
            start_time = time.time()

            logger.debug("开始基础连接测试（ice_ping）...")
            # ice_ping() 是ICE内置方法，所有代理对象都支持
            # timeout参数确保不会长时间阻塞（单位：毫秒）
            self.proxy.ice_ping(Ice.Unset)  # 或指定超时如 self.proxy.ice_ping(3000)

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"基础连接测试成功，耗时 {elapsed:.2f}ms")
            return True

        except Ice.ConnectionTimeoutException as e:
            error_msg = f"连接超时：{e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)
        except Ice.UnknownException as e:
            error_msg = f"未知协议错误：{e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)
        except Ice.Exception as e:
            error_msg = f"ICE通信异常：{e}"
            logger.error(error_msg)
            raise ConnectionError(error_msg)
        except Exception as e:
            error_msg = f"未知测试错误：{e}"
            logger.error(error_msg, exc_info=True)
            raise ConnectionError(error_msg)



    def invoke(self, class_name: str, method_name: str, params: Dict[str, Any], version: str = "1.0") -> Dict[str, Any]:
        """Compatibility dictionary API; new tests consume invoke_result."""
        return self.invoke_result(class_name, method_name, params, version).legacy()

    def invoke_result(self, class_name, method_name, params, version="1.0"):
        """Preserve both envelope codes, raw bytes, payload and request evidence."""
        if not self._connected:
            raise RuntimeError("ICE服务未连接")

        start_time = time.time()
        import uuid
        request_id = f"{class_name}.{method_name}-{uuid.uuid4().hex}"

        try:
            self._log_request(request_id, class_name, method_name, params)
            req = self._create_request(class_name, method_name, params, version)
            # 修改调用方式
            result_code, res = self.proxy.invoke(req, {})  # res作为返回值
            result = decode_response(result_code, res, request_id, (time.time() - start_time) * 1000)
        except Ice.Exception as e:
            result = GatewayResult(None, None, None, b"", request_id,
                                   (time.time() - start_time) * 1000, "ICE exception: " + str(e))
        except Exception as e:
            result = GatewayResult(None, None, None, b"", request_id,
                                   (time.time() - start_time) * 1000, "Client exception: " + str(e))
        self.last_call = result
        allure.attach(json.dumps(result.evidence(), ensure_ascii=False, indent=2),
                      name="ICE Response Envelope", attachment_type=allure.attachment_type.JSON)
        logger.log(logging.ERROR if result.error or result.invoke_code or result.response_code else logging.INFO,
                   "[%s] invoke_code=%r response_code=%r elapsed_ms=%.2f error=%r",
                   request_id, result.invoke_code, result.response_code, result.elapsed_ms, result.error)
        return result


    def _create_request(self, class_name, method_name, params, version) -> Request:
        req = Request()
        req.className = class_name
        req.method = method_name
        req.version = version
        try:
            req.params = json.dumps(params, ensure_ascii=False).encode('utf-8')
        except Exception as e:
            raise ValueError(f"参数序列化失败: {e}")
        return req

    def _process_response(self, request_id, res: Response, code: int, start_time):
        """Retained for older callers; decode_response is the single decoder."""
        return decode_response(code, res, request_id, (time.time() - start_time) * 1000).legacy()

    def _log_request(self, request_id, class_name, method_name, params):
        params = redact(params)
        msg = f"[{request_id}] 调用: {class_name}.{method_name}\n参数: {json.dumps(params, indent=2, ensure_ascii=False)}"
        logger.info(msg)
        allure.attach(
            json.dumps({
                "requestId": request_id,
                "className": class_name,
                "methodName": method_name,
                "params": params,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }, ensure_ascii=False, indent=2),
            name="ICE Request",
            attachment_type=allure.attachment_type.JSON
        )

    def _log_success(self, request_id, data, elapsed_ms):
        msg = (
            f"[{request_id}] 成功\n返回码: {data.get('resultCode')}\n"
            f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}\n耗时: {elapsed_ms:.2f}ms"
        )
        logger.info(msg)
        allure.attach(
            json.dumps({
                "requestId": request_id,
                "data": data,
                "elapsedMs": elapsed_ms,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }, indent=2, ensure_ascii=False),
            name="ICE Response",
            attachment_type=allure.attachment_type.JSON
        )

    def _log_ice_error(self, err: Ice.Exception):
        msg = f"ICE异常: {err}"
        logger.error(msg)
        allure.attach(msg, name="ICE Exception", attachment_type=allure.attachment_type.TEXT)

    def _handle_ice_exception(self, err, request_id, start_time):
        elapsed = (time.time() - start_time) * 1000
        self._log_ice_error(err)
        logger.error(f"[{request_id}] ICE异常，耗时: {elapsed:.2f}ms")
        return {"resultCode": -1, "message": str(err)}

    def _handle_generic_exception(self, err, request_id, start_time):
        elapsed = (time.time() - start_time) * 1000
        msg = f"系统异常: {err}"
        logger.error(f"[{request_id}] {msg}", exc_info=True)
        allure.attach(msg, name="System Exception", attachment_type=allure.attachment_type.TEXT)
        return {"resultCode": -3, "message": msg}

    def disconnect(self):
        """安全断开ICE连接"""
        if getattr(self, 'communicator', None):
            try:
                self.communicator.destroy()
                # 关键：解除Python和C++层的引用
                del self.communicator
            except:
                pass
        self._connected = False
        self.proxy = None



    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文退出时确保资源释放"""
        self.disconnect()
        # 确保立即回收内存
        import gc
        gc.collect()
        #self.disconnect()

    def __del__(self):
        """最后的安全网"""
        if getattr(self, 'communicator', None):
            try:
                self.communicator.destroy()
            except:
                pass


if __name__ == '__main__':
    from generated.com.hst.proxy.service.common.CommonService import CommonService
    print("DEBUG: 正确的 CommonService 是否有 _op_invoke：", hasattr(CommonService, "_op_invoke"))
    client = IceClient()
    success = client.connect()
    print("连接结果：", success)
    if client.proxy:
        print("代理类型：", type(client.proxy))


