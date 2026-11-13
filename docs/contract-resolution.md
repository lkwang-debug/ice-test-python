# 原“待确认”项的处理结果

不再使用 contract_pending 统一跳过。根据PDF、服务器处理器和真实调用逐项处理，具体结果进入Allure。

| 原因 | 处理方式 |
| --- | --- |
| replaceRoomRoute旧预期含data字段 | PDF第48、70页写无业务返回，改成返回码加数据库回查；缺必填字段按第48页做拒绝及状态不变检查。 |
| getRoomSettings校验固定等待室默认值 | 改为PDF第65–66页的roomId、enableRecord、enableFile、roomContext、layoutData等字段；不再绑定某个环境的等待室配置。缺必填roomId验证拒绝，不存在房间检查空结果身份。 |
| getNodeIdByLocal将字符串当成非法int | PDF第22页声明String。字符串不匹配时检查空结果，不再预期整数转换异常4107。 |
| confRoomStart缺serviceId的错误码未知 | PDF明确必填，改为明确拒绝；不编造固定业务错误码。SQL异常不当成正常的参数拒绝。 |
| devUpdate、updateService、deleteRoomRouteInfo、getRoomDeptList | 实际发送文档方法名；本服务器返回4108，处理器核查也未找到对应实现，报告当前版本不支持，不能标成通过或跳过。 |
| insertIntoFaceRollCall | 已确认支持，使用本轮meetingId创建点名日志，校验返回的rollCallId。 |
| updateFaceInfoByFaceId | 已确认存在处理器，但当前新后台记录在t_face_library，旧接口读取的t_faceinfo为空。报告数据源兼容问题，不判成人脸服务未部署。 |
| getFaceInfoByFaceId方法名 | 当前处理器对外注册的是getFaceInfo，已添加明确的同语义方法映射；与getRoomDefDevID的大小写差异一样，不要求用户写JSON配置。 |
| confLog日志查询不到 | 该环境按年写t_roomlog2026，原核查只查了t_roomlog。改为自动发现年度分表并对异步落库进行有限轮询。 |

原13条失败中的用例调整：

- 路由缺节点/地址/认证码：拒绝且原路由不变；SQL非空异常、先删后插导致数据丢失仍失败。
- 用户昵称缺失：按文档必填验证拒绝和原值不变；性别超长作为实际存储边界回归，要求明确拒绝，不能以SQL长度异常冒充正常验证。
- delDir四条负向：检查明确拒绝且原测试目录不变；命名SQL占位符错误仍为接口缺陷，不改成预期4107。
- moveDocFile缺parentId、renameFile缺docName：改为参数拒绝及原记录不变，不再要求文档未规定的固定业务码；SQL非空异常仍失败。
- moveDocFile父目录不存在：取消臆定的-9，明确作为数据完整性回归；文档没有定义父目录存在性规则，该检查不冒充文档明确条款。
- getUserRoomList：请求字段按文档使用localUserId；服务端SQL的localUserID属性绑定错误不能靠客户端改请求字段修复，保留失败。

这些改动修复的是用例依据、关联和核查方式，不意味着服务端问题会随用例修改消失。
