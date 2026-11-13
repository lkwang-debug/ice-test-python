# 四个旧方法退役确认与后继接口验证

2026-10-15，用户提供开发对4.39.7所在代码线的确认：存储过程改造commit 3c58815、达梦适配commit a0cbc09删除了以下Processor。因此本轮历史COMPAT-DOCUMENTED-METHODS不是待修复的“漏实现”问题，应调整当前版本测试范围。

## 当前版本映射

| 旧方法 | 开发确认 | 后继及差异 |
| --- | --- | --- |
| device.devUpdate | 已改名升级，a0cbc09 | device.devUpdate2；包含memLoad，updateTime由服务端处理，不作为客户端入参 |
| device.updateService | 已废弃，3c58815 | 无等价后继；registerService/serviceUnregister不是原状态更新契约，不能自动平替 |
| room.deleteRoomRouteInfo | 功能合并，3c58815 | room.delRoomRoute，使用roomId/svrAppId/svrNodeId；不是原roomSrvNodeId单字段请求的简单别名 |
| room.getRoomDeptList | 已改名升级，a0cbc09 | room.getRoomDeptList2，roomId不变；列表字段为getRoomDeptList2，房间部门来源有t_roominfo→t_roomruninfo回退 |

room.delRoomRoute在roomId=0时按svrAppId+svrNodeId批量删除。此语义不能推广到getRoomSettings/updateRoomRoute/replaceRoomRoute；后三者的0号ID缺陷依然保留。新接口的批量删除专项尚未补做实时验证，不因为普通路由删除通过就宣称该分支已覆盖。

定时清理变体的className另需按实际注册核对：当前项目PDF矩阵及device-009为device.delRoomRouteByTimer，并非room.delRoomRouteByTimer；本次不据回复中的简称新增room域调用或自动映射。

## 已完成的测试调整

- 从Python当前套件移除4条旧方法探测，取消1条COMPAT-DOCUMENTED-METHODS汇总失败；不再持续发送已确认移除的请求。
- 保留旧Allure和2026-10-14兼容性失败证据；退出范围不算旧接口通过或后端修复。
- common/interface_catalog.py登记来源、删除commit和替代关系。没有设置自动调用别名，避免参数/语义不同的接口被悄悄替换；无需用户增加JSON配置。
- 覆盖矩阵仍保留92个文档接口，其中旧人脸6个、此次旧方法4个退出当前版本范围；有效82个。
- 原Excel只有device-007对devUpdate2的双meeting场景，单meeting会跳过。新增primary_device_update_current_version，使用当前主设备的完整合法状态上报（包含memLoad），检查响应及只读数据库对应字段，并通过已有fixture恢复。
- 原room-030/031/032触达getRoomDeptList2但只检查返回码。新增test_room_department_list_current_version，核对departId、getRoomDeptList2列表、同记录字段类型及数据库部门记录内容，允许实际部门列表为空，不统一要求非空。
- delRoomRoute的独立流程已覆盖按真实路由键删除及重复删除后的最终状态，继续使用；没有把旧接口参数原样传入新接口。

## 验证结果

- 离线：`python -m pytest tests/unit -q`，80 passed。
- 收集：当前全量289条，270条Excel及19条Python。由旧292条减去4条旧探测、1条汇总，再增加2条后继接口检查。
- 155定向实时验证：新增的主设备devUpdate2状态上报、getRoomDeptList2数据库对照均通过，2 passed；fixture未报告清理失败。证据位于analysis/2026-10-15-interface-successors/result。
- 此次未全量实时重跑，allure_report仍保留2026-10-14的292条历史结果。不能把取消1条汇总直接当作新一轮“13失败”的实测统计。

## 后续验收范围

不再要求开发恢复上述旧Processor。开发维护当前接口文档并标注退役/替代即可；旧版本如确需回归，需要单独明确版本支持范围，不能在当前套件继续把这些方法列为缺陷。

getRoomDeptList2的t_roomruninfo回退分支、delRoomRoute的roomId=0批量删除及隔离边界均仍需独立前置和状态验证。新增的两条实测不能当作这些分支已完成覆盖。
