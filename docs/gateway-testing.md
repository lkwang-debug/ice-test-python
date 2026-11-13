# 网关测试：只在 common/config.py 配置

2026-11-11最新确认：address非必填按0/0断言；省略parentId按4107且位置不变断言；room-065/068按4.40.1.2允许不存在房间预建路由，断言0/0并核对落库及原路由不变。前两类12条、路由4条分别定向复测全部通过。本轮未重新执行全量，下文为历史记录。见[已确认断言](confirmed-address-parentid-2026-11-11.md)。

2026-11-06最新修复：本地脚本及房间前置8条已全部通过，191条单元测试通过；最后一轮完整349条为333通过、7失败、0异常、9跳过。测试房间为已关联当前用户的空闲标准房间10013，录制开关及扩展标记独立查库。剩余7条对应address校验及省略parentId两类服务端差异，见[修复与回归结果](local-fixture-fixes-2026-11-06.md)。

2026-11-06：`database.config_dir` 默认None，自动跟随运行中网关的启动参数、工作目录及JAR/classpath定位配置，兼容旧目录 `/hst/meeting/IceDBProxy/` 和新目录 `/hst/meeting/dbproxy/`。MySQL/Kingbase单地址及Kingbase主备地址从服务端JDBC配置自动识别，无需额外单双库开关，详见[新旧部署兼容说明](deployment-compatibility-2026-11-06.md)。

2026-11-02：数据库默认使用 `backend="auto"`，根据运行中 IceDBProxy 的有效配置自动识别 MySQL/Kingbase、连接信息和可用查询客户端。启动预检验证 ICE、数据库和测试编号；失败时不执行用例，已有报告保持原样。历史执行记录见下文，当前修复验证见 [数据库自动适配与回归](database-auto-fix-2026-11-02.md)。

最新完整执行：[开发保留设计后的全量回归](retained-design-full-run-2026-10-19.md)，349条中323通过、26按既定范围排除，0失败、0受阻、0清理失败、0契约待确认。这是原12条按用户转述的开发设计结论调整后，重新执行的完整一轮；下面较早统计保留历史。

当前补充回归会核实delDir仅删除目录记录、原文件记录精确保留；开关指定字符串转换后的真实0/1；数字0/1选择节点与只读数据匹配。缺参/null等原有拒绝边界继续测试。完整文件树清理或上层认证流程不据此宣称已覆盖。

最终澄清与复测：[7条按已确认设计的最终断言](confirmed-design-final-2026-10-19.md)。原7条＋3条正常路由对照全部通过；当前有效349条为311通过、12失败，0契约待确认，来源是上一轮完整执行与本次10条定向复测按用例身份取最新。本次不是新一轮349条全量。room-065额外失败已修正，不再要求开发重复确认。

上一轮：[开发确认后的协议落地与全量回归](developer-contract-resolution-verification-2026-10-19.md)。当时349条为310通过、13失败；其中room-065已由上述最终澄清和定向复测更新，不能继续按13条失败理解当前结果。

最新全量：[2026-10-19脚本/数据修正后重跑](full-rerun-after-test-fixes-2026-10-19.md)，349条中304通过、12失败（3个后端问题）、0受阻、0清理失败，另26不适用、7契约观察。

2026-10-19脚本/数据修正：资料修改用例默认通过同环境用户API创建临时账号，准备完整非空资料，网关测试后恢复并API删除；不再因配置用户的电话/邮箱为NULL而阻塞。5条旧参数成功预期已同步为4108；user-015验证局部更新保留昵称，避免非法性别掩盖测试目的。执行方式和Excel的auto开关不变。

历史全量及定向复测：[2026-10-16全量结果](full-run-2026-10-16.md)，289条中250通过、5断言失败、1清理失败、26不适用、7契约观察。清理失败的用户字段已按一次性授权恢复；历史用例状态仍保留，不改计通过。

最新定向验证：[2026-10-16修复验证](fix-verification-2026-10-16.md)，原10条全部通过，另5条正向/幂等检查通过，0失败、0受阻、0清理失败。本轮报告独立保存，不与旧全量结果混合。

2026-10-19最新专项：[原5条及扩展修复验证](fix-verification-2026-10-19.md)。原5条通过；总63条中53通过、10失败，剩余为isLocal数字及开关字符串的JSON类型校验缺口，0清理失败。

## 运行

日常直接执行：

```powershell
python run.py
```

唯一配置文件为 `common/config.py`，服务器地址只改顶部 `SERVER_HOST`，ICE和SSH核查自动共用；端口、设备、房间、用户和路径配置都在 `TEST_CONFIG`。旧INI文件及读取逻辑已删除。不需要 JSON、环境变量或独占环境开关。当前地址192.168.6.160、双meeting，房间10013；旧网关人脸接口停用，CDN和电话网关关闭。上述旧执行统计保留为历史记录。

离线框架测试：`python -m pytest tests/unit -q`。

直接运行实时测试并指定报告目录：

```powershell
python -m pytest test_api_all.py tests/integration --gateway-run --alluredir=allure_report/result --clean-alluredir
```

测试范围默认全部；只想查询时，可指定 `--gateway-scope=read`。JSON profile 入口仅为兼容旧命令保留，正常运行不使用。

## 必要参数

| TEST_CONFIG字段 | 配置说明 |
| --- | --- |
| SERVER_HOST / locator_port | 网关和SSH共享SERVER_HOST，换服务器只改一处；当前160和22000 |
| topology | single或dual；不是主备/父子节点开关 |
| primary_device_id | 实际主设备ID，如MainDev |
| secondary_device_id | 仅dual使用，填写实际第二台设备ID |
| room_id | 测试房间；会议生命周期开始前必须空闲 |
| user_id / username / user_password | 对应测试用户；用户需属于测试房间 |
| user_update_mode | 当前nonempty_fields表示接口忽略null/空串；原资料为空且拟写非空值时fixture会阻塞，避免无法通过接口恢复 |
| user_fixture_mode | 默认temporary_api：仅资料修改场景使用每条独立临时账号，原配置用户仍用于登录/房间身份。configured_user仅供有完整可恢复资料的专用账号；NULL恢复保护仍生效 |
| user_fixture_api_scheme / user_fixture_api_port | 临时账号前置API，当前http/28080，自动共用SERVER_HOST；不增加第二处IP。API只负责用户创建/删除，测试目标仍是ICE网关 |
| user_fixture_api_account | 默认None，SELECT读取同环境t_api_power唯一启用默认应用的凭据，不落盘/不写报告；默认应用不唯一时指定实际account。前置API不可用时报告阻塞，不回退修改原用户 |
| database | 默认auto、config_dir=None；自动识别新旧部署目录、MySQL/Kingbase及查询客户端，特殊路径可指定config_dir；兼容原mysql、ssh_mysql、ssh_kingbase手动配置 |
| record_global_switch | 默认None，独立读取数据库中的房间录制开关，无房间配置时读全局配置；显式0/1覆盖自动预期 |
| test_service_app_id / test_route_app_id / test_master_server_type | 默认54011/54012/54013，供测试使用；预检拒绝覆盖真实服务、未知路由或主从身份 |
| face_enabled / face_id | 默认False：人脸已迁出本网关；旧接口和Python补充检查默认不执行。face_id仅供明确复测历史版本时使用 |
| cdn_enabled / phone_gateway_enabled | 默认False，不执行对应功能 |
| protocol / service / adapter | 原INI的连接协议、服务名和适配器名，已合入TEST_CONFIG |
| excel_path / report_output | 用例文件、报告目录；相对路径以项目或解压包根目录解析 |
| allure_cli / java_home | Allure命令及Java运行环境路径，同样在TEST_CONFIG配置 |

单/双 meeting只改变两台设备间的测试适用性。单meeting可以测试设备注册、服务管理、节点状态、授权和业务流程，没有“独占环境才允许运行”的总开关。修改数据的用例通过SELECT保存快照，通过网关接口恢复。

## 已退役的人脸接口

用户已确认人脸功能不再使用这套数据库网关。旧表`t_faceinfo`为空不能据此判断当前人脸服务异常，也不再作为当前回归的阻塞或兼容性缺陷。6个文档人脸接口标记retired，保留历史用例和证据，不计入当前有效接口的覆盖缺口。

优化前Excel中，insertIntoFaceRollCall的8条auto=False；addFaceRollCallUser和getFaceUserInfo的6条auto=True。现在这14条统一设为False；Python中5条旧人脸补充检查由face_enabled=False停用。新的人脸接口需要另行按其实际契约建套件。

## 用例与断言

Excel保留五个sheet、290条历史记录，其中270条auto=True、20条False。A列auto为逐条执行开关，并提供True/False下拉和冻结显示；True参与收集，False不加载，也不校验已停用的历史请求。空白沿用旧版默认True；错误拼写会在预校验报错。编辑后保存并重新启动测试，已开始的一轮不会动态刷新开关。正常运行只读取Excel，不会自动迁移或覆盖手工开关。

case_id是稳定标识。topology决定设备数量适用性。requires用于CDN、电话网关等功能选择；exclusive和contract_pending不再作为跳过条件。auto=True仍需符合这些场景适用条件；auto只控制Excel参数用例，Python业务流程按config.py和自身前置执行。

assertions支持精确路径、类型、空值、长度、范围和同记录匹配。verification声明调用契约、响应、接口回查、数据库回查或状态校验。没有业务返回字段的接口不伪造字段，通过状态回查或明确说明只验证调用契约。

expected_outcome=rejected表示负向输入应被明确拒绝，不再全局禁止某个错误码。当前版本行为基线使用精确预期码和状态回查；已定位SQL缺陷的用例有显式错误码限制，并由合法输入正向用例交叉验证。文档没有定义具体错误码时，不捏造-9等值。

test_group区分普通回归、behavior_baseline、backend_defect和contract_review；issue_id用于将多个失败用例合并为一个问题。契约观察会实际调用并记录差异，再以XFAIL单列，不算业务通过；数据库或运行错误仍报告异常，不被契约标签吞掉。

参数引用只允许`${env.xxx}`、`${fixture.xxx}`和`${case.xxx}`，不使用跨用例缓存和数组位置。配置错误在收集时集中报出，故意非法的请求实际发送到服务端。

## 恢复与报告

只读事务中的SELECT用于核实，数据库不写测试数据。服务、节点、授权、设备、系统参数、用户、路由等有独立快照和恢复动作。恢复失败作为teardown error，不能算通过。

会议和点名日志无删除接口，以唯一groupId和标题标识并保留；专用测试服务注册记录以停用状态保留，不宣称这两类记录已删除回滚。授权字段4KCount按Gson SerializedName发送，不按Java内部字段名fourKCount发送。

开发已确认4个旧方法在4.39重构中删除，当前版本不再探测，也不保留COMPAT-DOCUMENTED-METHODS汇总失败。devUpdate2、getRoomDeptList2及delRoomRoute按各自真实契约测试；updateService无等价后继，不映射到注册/注销。92个文档接口保留追踪，其中6个旧人脸接口及4个此次确认的旧方法退出当前范围，当前有效82个。新旧接口关系见common/interface_catalog.py，不是运行时别名配置。

roomId取值规则按接口区分：getRoomSettings、updateRoomRoute、replaceRoomRoute不允许0号房间；delRoomRoute的roomId=0则是按svrAppId+svrNodeId批量删除的正式特例，不能对全网关统一套用roomId>0。

若明确需要复测历史人脸网关，需同时启用face_enabled及相应Excel行。此时仍只接受`t_faceinfo`中真实存在的face_id，不能拿`t_face_library.source_id`替代；这是历史版本复测条件，不是当前环境必须补齐的数据。

runner汇总和`allure_report/outcomes.json`分别列出通过、后端回归失败、兼容性差异、前置阻塞、版本不支持、契约观察和场景不适用。Allure原生仅有passed/failed/broken/skipped等状态，其中blocked原生显示broken、XFAIL和不支持原生显示skipped，应结合上述分类阅读。当前处理记录见`docs/outcome-classification-validation.md`。
