**# ICE自动化测试框架 README**


# 框架介绍
这是一个基于Python的ICE服务自动化测试框架，主要特点包括：
1、使用Excel管理测试用例，支持多sheet分类
2、动态生成测试用例，无需手动编写测试代码 
3、集成Allure生成美观的测试报告
4、支持ICE服务调用和结果验证
5、提供参数关联和随机参数生成功能
6、支持多种断言方式
## 主要技术

ICE通信：基于ZeroC ICE 3.7+实现分布式服务调用
动态测试：利用Python元编程动态生成测试用例
数据驱动：Excel作为测试数据源，支持复杂数据结构
异步报告：Allure + pytest异步报告生成机制


## 实现功能

1、ICE服务连接管理 - 自动连接ICE服务并管理生命周期
2、Excel用例管理 - 从Excel读取测试用例，支持按类名分sheet
3、动态测试生成 - 根据Excel自动生成测试函数
4、参数处理 - 支持JSON参数、随机参数生成、参数关联 
5、结果验证 - 多种断言方式，包括全量匹配和部分匹配
6、测试报告 - 集成Allure生成详细测试报告
7、接口关联 - 支持接口返回值缓存和引用

# 架构设计
本框架采用分层架构设计，各层职责明确：

## 驱动层：

ice_client.py：封装ICE客户端核心通信能力
method.py：业务接口方法封装
compile_ice.py：ICE文件编译工具

## 数据层：

excel_utils.py：Excel测试数据读取与处理
config.py：全局配置管理

## 执行层：

test_api_all.py：动态测试用例生成器
conftest.py：pytest夹具管理

## 报告层：

Allure集成：可视化测试报告生成
run.py：执行流水线控制




# 框架结构

project/
├── allure_report/  
    ├── html             # 测试报告存放
│   ├── result           # 测试结果临时存放
├── common/              # 公共模块
│   ├── config.py        # 配置文件
│   ├── excel_utils.py   # Excel用例读写封装
│   └── ice_client.py    # ICE客户端初始化和调用封装
├── generated/           # ICE生成代码
├── ice_files/           # ICE定义文件
├── method.py            # 接口方法封装
├── test_api_all.py      # 测试用例自动生成
├── run.py               # 执行入口
├── conftest.py          # pytest配置
└── setup_path.py        # 路径设置


# 依赖库
absl-py==2.1.0
allure-pytest==2.13.2
allure-python-commons==2.13.2
altgraph==0.17.4
astunparse==1.6.3
async-generator==1.10
attrs==22.1.0
bcrypt==4.0.1
beautifulsoup4==4.13.3
blinker==1.9.0
certifi==2022.9.24
cffi==1.15.1
chardet==5.2.0
charset-normalizer==2.1.1
click==8.1.8
colorama==0.4.6
cryptography==41.0.1
ddt==1.6.0
deepface==0.0.93
et-xmlfile==1.1.0
exceptiongroup==1.0.4
execnet==2.1.1
Faker==37.3.0
filelock==3.17.0
fire==0.7.0
Flask==3.1.0
flask-cors==5.0.1
flatbuffers==25.2.10
gast==0.6.0
gdown==5.2.0
gevent==23.9.1
google-pasta==0.2.0
greenlet==3.0.1
grpcio==1.71.0
gunicorn==23.0.0
h11==0.14.0
h5py==3.13.0
html-test-report==1.0.1
HTMLTestReport==1.0.1
ice==0.0.2
idna==3.4
iniconfig==2.0.0
itsdangerous==2.2.0
Jinja2==3.1.2
joblib==1.4.2
jsonpath==0.82
keras==3.9.0
libclang==18.1.1
login==0.0.6
lz4==4.4.3
Markdown==3.7
markdown-it-py==3.0.0
MarkupSafe==2.1.2
mdurl==0.1.2
ml_dtypes==0.5.1
mtcnn==1.0.0
multi-key-dict==2.0.3
namex==0.0.8
numpy==2.1.3
opencv-python==4.11.0.86
openpyxl==3.1.2
opt_einsum==3.4.0
optree==0.14.1
outcome==1.2.0
packaging==25.0
pandas==2.2.3
parameterized==0.9.0
parametrizer==0.0.3
paramiko==3.2.0
pbr==6.1.1
pefile==2023.2.7
pillow==11.1.0
pluggy==1.0.0
protobuf==5.29.3
py==1.11.0
pyasn1==0.5.0
pycparser==2.21
pycryptodome==3.18.0
pyDes==2.0.1
Pygments==2.15.1
pyinstaller==6.13.0
pyinstaller-hooks-contrib==2025.4
PyMySQL==1.0.3
PyNaCl==1.5.0
pyparsing==3.0.9
PySocks==1.7.1
pytest==7.3.1
pytest-html==3.2.0
pytest-metadata==3.0.0
pytest-ordering==0.6
pytest-rerunfailures==11.1.2
pytest-win32consoletitle==0.1.2
pytest-xdist==3.7.0
python-dateutil==2.9.0.post0
python-dotenv==0.21.0
python-jenkins==1.8.2
pytz==2023.3
pywin32==310
pywin32-ctypes==0.2.3
PyYAML==6.0
requests==2.28.1
retina-face==0.0.17
rich==13.9.4
robot==20071211
robotframework==6.0.2
rsa==4.9
selenium==4.6.0
six==1.16.0
sniffio==1.3.0
sortedcontainers==2.4.0
soupsieve==2.6
spark-parser==1.8.9
sshtunnel==0.4.0
tensorboard==2.19.0
tensorboard-data-server==0.7.2
tensorflow==2.19.0
tensorflow-io-gcs-filesystem==0.31.0
termcolor==2.5.0
tomli==2.0.1
tqdm==4.64.1
trio==0.22.0
trio-websocket==0.9.2
typing_extensions==4.12.2
tzdata==2023.3
uncompyle6==3.9.2
urllib3==1.26.12
webdriver-manager==3.8.5
websocket==0.2.1
Werkzeug==3.1.3
wrapt==1.17.2
wsproto==1.2.0
xdis==6.1.3
xmindparser==1.0.9
zeroc-ice==3.7.8
zope.event==5.0
zope.interface==6.1



# 用例Excel字段介绍

Excel用例包含以下字段：

字段名	必填	说明
class_name	是	测试类名(对应sheet名)
method	是	要调用的方法名
case_name	是	测试用例名称
auto	否	是否执行(true/false)，默认true
params	是	请求参数(JSON格式)
expected	是	预期结果(JSON格式)
partial_validation	否	是否部分验证(true/false)
save_response	否	缓存响应结果供后续用例使用

# 用例编写指南

基本用例格式
在Excel中，每个测试用例占一行，包含下述字段。例如：

class_name	 method	        case_name	       params	                      expected                               partial_validation                                                     save_response                           auto                              
device	    devRegister	   设备注册测试	{"deviceId":"123"}	  {"resultCode":0,"data":{"status":1}}        true为支持宽松字段匹配，只校验 expected 中 key=value 是否在实际返回中任意位置存在      全局变量存储接口返回值，用于参数关联       true执行自动化 false不执行

# 参数传递

JSON参数：params和expected字段支持JSON格式
简单JSON: {"key":"value"}
嵌套JSON: {"user":{"name":"test","age":20}}
数组: {"ids":[1,2,3]}

# 随机传参：
${RANDOM_STR} - 生成8位随机字符串
${RANDOM_STR[10]} - 生成10位随机字符串
示例：{"token": "${RANDOM_STR}", "code": "TEST_${RANDOM_STR[6]}"}

# 接口关联
缓存响应：使用save_response字段
device_devRegister - 缓存device类的devRegister方法响应
device_devRegister as devReg - 缓存并使用别名

引用缓存值：在params中使用${api_name.response.field}格式
${device_devRegister.response.deviceId} - 引用device_devRegister返回的deviceId
${device_getList.response.data.0.id} - 引用数组第一个元素的id字段

# 断言类型

基础断言：
验证resultCode是否匹配预期 resultCode == 0

全量匹配：
当expected中包含data字段时，会全量匹配返回数据  data == {...}

部分匹配：
设置partial_validation=true时，只验证expected中指定的字段  verify("data.user.name")

支持嵌套字段验证
支持!null特殊值验证字段存在且非空


# 执行测试：
python run.py


# 查看报告：
报告生成在allure_report/html目录
会自动打开浏览器展示报告