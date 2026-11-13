# 新旧部署目录与数据库地址自动兼容

日常保持以下两项默认值即可，换环境主要修改SERVER_HOST和SSH登录信息：

```python
"backend": "auto",
"config_dir": None,
```

| 情况 | 处理方式 |
| --- | --- |
| 旧目录 /hst/meeting/IceDBProxy/，java -jar启动 | 支持db-proxy.jar及版本化JAR名称，根据启动参数或运行目录查找config |
| 新目录 /hst/meeting/dbproxy/，java -cp启动 | 支持com.hst.dbproxy.App入口，根据启动参数、工作目录或classpath查找config |
| 同时残留新旧目录 | 跟随正在运行的网关，不扫描并混合另一个旧安装的配置 |
| 特殊部署目录 | 将config_dir填为实际配置目录，例如/opt/custom-gateway/config；显式Spring启动配置位置仍优先 |
| MySQL或Kingbase单地址 | 自动读取JDBC中的地址和端口，无需主备配置 |
| Kingbase多地址 | 保留全部地址及对应端口；按targetServerType=master/primary选择可写主库连接，再执行只读查询 |

配置目录推断出现多个候选时明确报错并要求指定config_dir，避免读取错误数据库。数据库单地址/多地址与TEST_CONFIG.topology无关；topology仍只控制meeting设备数量。

验证：157条单元测试通过，覆盖新旧目录、两种启动方式、残留旧目录、显式自定义目录、目录歧义、单地址默认/自定义端口及Kingbase多地址。160新目录的Kingbase主备配置已经通过实际数据库连接、ICE和资源预检；本次未执行业务写入用例，也未重新生成Allure。
