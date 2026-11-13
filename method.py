#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2025/6/19 上午11:38
# @Author  : hzk
# @File    : method.py
# @Software: PyCharm

import allure
import logging
from common.ice_client import IceClient

from common.config import ICE_CONFIG

logger = logging.getLogger(__name__)


class BaseMethods:
    """基础方法类"""

    def __init__(self):
        self.client = IceClient()
        self.client.connect()

    def close(self):
        """关闭ICE连接"""
        self.client.disconnect()

    def _invoke(self, class_name, method_name, params):
        """统一调用方法"""
        return self.client.invoke(class_name, method_name, params)


class CompanyMethods(BaseMethods):
    """公司相关接口"""

    @allure.step("检查会议日志")
    def check_meeting_log(self, params):
        return self._invoke("company", "checkMeetingLog", params)

    @allure.step("获取公司业务信息")
    def get_company_business(self, params):
        return self._invoke("company", "getCompanyBusiness", params)


class DeviceMethods(BaseMethods):
    """设备相关接口"""

    def update_service(self, params):
        return self._invoke("device", "updateService", params)

    def update_dev_info_status_by_dev_id(self, params):
        return self._invoke("device", "updateDevInfoStatusByDevId", params)

    @allure.step("切换为从设备")
    def change_to_slave(self, params):
        return self._invoke("device", "changeToSlave", params)

    @allure.step("检查设备列表")
    def check_dev_list(self, params):
        return self._invoke("device", "checkDevList", params)

    @allure.step("删除定时路由")
    def del_room_route_by_timer(self, params):
        return self._invoke("device", "delRoomRouteByTimer", params)

    @allure.step("设备注册")
    def dev_register(self, params):
        return self._invoke("device", "devRegister", params)

    @allure.step("设备注销")
    def dev_unregister(self, params):
        return self._invoke("device", "devUnRegister", params)

    @allure.step("更新设备信息")
    def dev_update(self, params):
        return self._invoke("device", "devUpdate", params)

    @allure.step("更新设备信息2")
    def dev_update2(self, params):
        return self._invoke("device", "devUpdate2", params)

    @allure.step("获取父节点信息")
    def front_get_parent_node_info(self, params):
        return self._invoke("device", "frontGetParentNodeInfo", params)

    @allure.step("前端节点注册")
    def front_node_register(self, params):
        return self._invoke("device", "frontNodeRegister", params)

    @allure.step("前端节点注销")
    def front_node_unregister(self, params):
        return self._invoke("device", "frontNodeUnregister", params)

    @allure.step("启动前端节点")
    def front_start(self, params):
        return self._invoke("device", "frontStart", params)

    @allure.step("获取所有电话网关信息")
    def get_all_phone_gw_info(self, params):
        return self._invoke("device", "getAllPhoneGwInfo", params)

    @allure.step("获取应用服务器列表")
    def get_app_srv_list(self, params):
        return self._invoke("device", "getAppSrvList", params)

    @allure.step("获取设备文件列表")
    def get_dev_file_list(self, params):
        return self._invoke("device", "getDevFileList", params)

    @allure.step("通过房间ID获取设备ID")
    def get_dev_id_by_room_id(self, params):
        return self._invoke("device", "getDevIdByRoomId", params)

    @allure.step("通过类型获取设备信息")
    def get_dev_info_by_type(self, params):
        return self._invoke("device", "getDevInfoByType", params)

    @allure.step("获取设备SIP电话列表")
    def get_dev_sip_phone_list(self, params):
        return self._invoke("device", "getDevSipPhoneList", params)

    @allure.step("获取设备验证码")
    def get_dev_verify_code(self, params):
        return self._invoke("device", "getDevVerifyCode", params)

    @allure.step("获取前端地址")
    def get_front_address(self, params):
        return self._invoke("device", "getFrontAddress", params)

    @allure.step("获取前端IP")
    def get_front_ip(self, params):
        return self._invoke("device", "getFrontIp", params)

    @allure.step("获取最后许可时间")
    def get_last_license_time(self, params):
        return self._invoke("device", "getLastLicenseTime", params)

    @allure.step("通过本地获取节点ID")
    def get_node_id_by_local(self, params):
        return self._invoke("device", "getNodeIdByLocal", params)

    @allure.step("获取节点列表")
    def get_node_list(self, params):
        return self._invoke("device", "getNodeList", params)

    @allure.step("获取在线设备数量")
    def get_online_dev_count(self, params):
        return self._invoke("device", "getOnlineDevCount", params)

    @allure.step("获取房间默认设备ID")
    def get_room_def_dev_id(self, params):
        return self._invoke("device", "getRoomDefDevID", params)

    @allure.step("获取服务列表")
    def get_service_list(self, params):
        return self._invoke("device", "getServiceList", params)

    @allure.step("获取子节点列表")
    def get_sub_node_list(self, params):
        return self._invoke("device", "getSubNodeList", params)

    @allure.step("获取系统参数")
    def get_system_param(self, params):
        return self._invoke("device", "getSystemParam", params)

    @allure.step("获取VGW地址")
    def get_vgw_addr(self, params):
        return self._invoke("device", "getVgwAddr", params)

    @allure.step("通过SN查询")
    def query_by_sn(self, params):
        return self._invoke("device", "queryBySn", params)

    @allure.step("注册服务")
    def register_service(self, params):
        return self._invoke("device", "registerService", params)

    @allure.step("注销服务")
    def service_unregister(self, params):
        return self._invoke("device", "serviceUnregister", params)

    @allure.step("设置文档转换开关")
    def set_document_conversion_switch(self, params):
        return self._invoke("device", "setDocumentConversionSwitch", params)

    @allure.step("设置节点状态")
    def set_node_status(self, params):
        return self._invoke("device", "setNodeStatus", params)

    @allure.step("启动本地节点")
    def start_local_node(self, params):
        return self._invoke("device", "startLocalNode", params)

    @allure.step("停止本地节点")
    def stop_local_node(self, params):
        return self._invoke("device", "stopLocalNode", params)

    @allure.step("尝试切换为主设备")
    def try_change_to_master(self, params):
        return self._invoke("device", "tryChangeToMaster", params)

    @allure.step("更新许可信息")
    def update_license_info(self, params):
        return self._invoke("device", "updateLicenseInfo", params)

    @allure.step("更新许可状态")
    def update_license_state(self, params):
        return self._invoke("device", "updateLicenseState", params)

    @allure.step("更新会议日志信息")
    def update_meeting_log_info(self, params):
        return self._invoke("device", "updateMeetingLogInfo", params)

    @allure.step("更新系统参数")
    def update_system_param(self, params):
        return self._invoke("device", "updateSystemParam", params)


class FileMethods(BaseMethods):
    """文件相关接口"""

    @allure.step("添加文件")
    def add_file(self, params):
        return self._invoke("file", "addFile", params)

    @allure.step("删除目录")
    def del_dir(self, params):
        return self._invoke("file", "delDir", params)

    @allure.step("删除文件")
    def del_file(self, params):
        return self._invoke("file", "delFile", params)

    @allure.step("获取房间文件列表")
    def get_room_file_list(self, params):
        return self._invoke("file", "getRoomFileList", params)

    @allure.step("获取根目录列表")
    def get_root_dir_list(self, params):
        return self._invoke("file", "getRootDirList", params)

    @allure.step("获取无用文件")
    def get_useless_file(self, params):
        return self._invoke("file", "getUselessFile", params)

    @allure.step("移动文档文件")
    def move_doc_file(self, params):
        return self._invoke("file", "moveDocFile", params)

    @allure.step("重命名文件")
    def rename_file(self, params):
        return self._invoke("file", "renameFile", params)


class RoomMethods(BaseMethods):
    """房间相关接口"""

    def delete_room_route_info(self, params):
        return self._invoke("room", "deleteRoomRouteInfo", params)

    def get_room_dept_list(self, params):
        return self._invoke("room", "getRoomDeptList", params)

    @allure.step("检查房间剩余时间")
    def check_room_remain_time(self, params):
        return self._invoke("room", "checkRoomRemainTime", params)

    @allure.step("会议日志")
    def conf_log(self, params):
        return self._invoke("room", "confLog", params)

    @allure.step("会议房间开始")
    def conf_room_start(self, params):
        return self._invoke("room", "confRoomStart", params)

    @allure.step("会议房间停止")
    def conf_room_stop(self, params):
        return self._invoke("room", "confRoomStop", params)

    @allure.step("会议用户登录2")
    def conf_user_login2(self, params):
        return self._invoke("room", "confUserLogin2", params)

    @allure.step("删除房间路由")
    def del_room_route(self, params):
        return self._invoke("room", "delRoomRoute", params)

    @allure.step("获取CDN信息")
    def get_cdn_info(self, params):
        return self._invoke("room", "getCDNInfo", params)

    @allure.step("获取RCS地址")
    def get_rcs_address(self, params):
        return self._invoke("room", "getRcsAddress", params)

    @allure.step("获取真实房间ID")
    def get_real_room_id(self, params):
        return self._invoke("room", "getRealRoomId", params)

    @allure.step("获取录制房间配置")
    def get_record_room_cfg(self, params):
        return self._invoke("room", "getRecordRoomCfg", params)

    @allure.step("获取录制用户ID")
    def get_record_user_id(self, params):
        return self._invoke("room", "getRecordUserId", params)

    @allure.step("获取房间公司ID")
    def get_room_company_id(self, params):
        return self._invoke("room", "getRoomCompanyId", params)

    @allure.step("获取房间当前设备ID")
    def get_room_cur_dev_id(self, params):
        return self._invoke("room", "getRoomCurDevId", params)

    @allure.step("获取房间部门列表2")
    def get_room_dept_list2(self, params):
        return self._invoke("room", "getRoomDeptList2", params)

    @allure.step("获取房间信息")
    def get_room_info(self, params):
        return self._invoke("room", "getRoomInfo", params)

    @allure.step("获取房间邀请码")
    def get_room_invite_code(self, params):
        return self._invoke("room", "getRoomInviteCode", params)

    @allure.step("获取房间路由信息")
    def get_room_route_info(self, params):
        return self._invoke("room", "getRoomRouteInfo", params)

    @allure.step("获取房间设置")
    def get_room_settings(self, params):
        return self._invoke("room", "getRoomSettings", params)

    @allure.step("获取房间用户列表")
    def get_room_user_list(self, params):
        return self._invoke("room", "getRoomUserList", params)

    @allure.step("通过房间路由获取服务器节点ID")
    def get_svr_node_id_by_room_route(self, params):
        return self._invoke("room", "getSvrNodeIdByRoomRoute", params)

    @allure.step("获取用户房间列表")
    def get_user_room_list(self, params):
        return self._invoke("room", "getUserRoomList", params)

    @allure.step("会议日志")
    def meeting_log(self, params):
        return self._invoke("room", "meetingLog", params)

    @allure.step("替换房间路由")
    def replace_room_route(self, params):
        return self._invoke("room", "replaceRoomRoute", params)

    @allure.step("请求主席权限")
    def request_chair_right(self, params):
        return self._invoke("room", "requestChairRight", params)

    @allure.step("通过房间ID更新房间信息")
    def update_room_info_by_room_id(self, params):
        return self._invoke("room", "updateRoomInfoByRoomId", params)

    @allure.step("更新房间路由")
    def update_room_route(self, params):
        return self._invoke("room", "updateRoomRoute", params)

    @allure.step("更新房间路由时间")
    def update_room_route_time(self, params):
        return self._invoke("room", "updateRoomRouteTime", params)

    @allure.step("更新房间用户状态")
    def update_room_user_state(self, params):
        return self._invoke("room", "updateRoomUserState", params)

    @allure.step("验证房间用户")
    def verify_room_user(self, params):
        return self._invoke("room", "verifyRoomUser", params)

    def get_room_h323_settings_info(self,params):
        return self._invoke("room", "getRoomH323SettingsInfo", params)


class UserMethods(BaseMethods):
    """用户相关接口"""

    def update_face_info_by_face_id(self, params):
        return self._invoke("user", "updateFaceInfoByFaceId", params)

    def get_face_info_by_face_id(self, params):
        return self._invoke("user", "getFaceInfoByFaceId", params)

    def get_face_info_list(self, params):
        return self._invoke("user", "getFaceInfoList", params)

    @allure.step("添加人脸点名用户")
    def add_face_roll_call_user(self, params):
        return self._invoke("user", "addFaceRollCallUser", params)

    @allure.step("获取人脸用户信息")
    def get_face_user_info(self, params):
        return self._invoke("user", "getFaceUserInfo", params)

    @allure.step("获取录制用户名")
    def get_record_user_name(self, params):
        return self._invoke("user", "getRecordUserName", params)

    @allure.step("获取用户角色")
    def get_user_role(self, params):
        return self._invoke("user", "getUserRole", params)

    @allure.step("插入人脸点名")
    def insert_into_face_roll_call(self, params):
        return self._invoke("user", "insertIntoFaceRollCall", params)

    @allure.step("更新用户信息")
    def update_user_info(self, params):
        return self._invoke("user", "updateUserInfo", params)

    @allure.step("验证用户")
    def verify_user(self, params):
        return self._invoke("user", "verifyUser", params)
