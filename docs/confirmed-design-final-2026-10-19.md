# 已确认设计的最终断言与复测

后续：另外12条也已由开发确认保留现有设计，并完成预期更新及一轮完整349条回归：323通过、0失败。见[最新完整执行](retained-design-full-run-2026-10-19.md)。以下311通过/12失败为本次设计确认前的历史有效结果。

用户进一步明确：上次7个场景按当前已确认设计断言。此前把“仅第4项修改”理解为updateRoomRoute必须继续允许预建，造成room-065额外失败，属于测试预期理解错误，现已修正，不再作为后端问题。

room-065改为精确返回4108且完整路由范围不变；updateRoomRoute与replaceRoomRoute对不存在房间统一拒绝。其他已确认行为继续保持：null应用ID拒绝、指定ParentID写入、loginType=1用户身份查询。保留业务字段、记录归属与无关字段/记录不变校验，不只检查返回码。

100条离线测试通过。本次实时复测为原7条及3条正常路由对照，共10条，全部通过；0受阻、0清理失败，12组业务快照前后一致。

最新有效结果为349个不同场景：311通过、12失败、0契约待确认。来源是前轮完整349条＋本次10条定向复测，按稳定用例身份选取最新结果；本次没有重新执行另一轮349条，也没有将重复执行计入分母。原始完整结果、定向结果和来源映射均保留。

剩余12条仍为此前另外确认的3个问题。本次对“按设计”的确认仅用于这7个场景，未修改那12条的缺陷断言。

## 对照结果

| 场景 | 固定预期与业务核查 | 结果 |
| --- | --- | --- |
| room-062、room-069 | svrAppId=null，4108，原路由不变 | 通过 |
| room-065、room-068 | 房间不存在，4108，原路由不变 | 通过 |
| file-023 | 返回0/result=0，指定ParentID落库，原文件名等字段保留 | 通过 |
| user-020 | 缺密码仍按已确认设计查询身份，ID/昵称匹配只读DB | 通过 |
| user_permissions | 正确/错误密码的身份查询结果一致，并验证房间成员结果 | 通过 |
| room-063、room-066、route_lifecycle | 正常更新/替换及路由生命周期对照 | 通过 |

## 证据

- [本次10条复测与状态证据](../analysis/2026-10-19-152022-confirmed-design-followup/retest-evidence.json)。
- [本次快照恢复](../analysis/2026-10-19-152022-confirmed-design-followup/restoration-check.json)。
- [349条有效统计](../analysis/2026-10-19-152022-confirmed-design-followup/effective-summary.json)、[逐条来源映射](../analysis/2026-10-19-152022-confirmed-design-followup/result-sources.json)。
- [最新Allure](../allure_report/html/index.html)展示按用例身份去重后的有效结果；原始完整执行仍在analysis/2026-10-19-145918-face-retired-full。
