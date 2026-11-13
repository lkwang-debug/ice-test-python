<#
  一键打包脚本 —— 生成 Windows 免安装执行包

  用法（在项目根目录执行）：
      powershell -ExecutionPolicy Bypass -File packaging\build_package.ps1

  产出：
      E:\VSCode_Project\CesIceApiTest-v4.40.0-win64\        解压即用的目录
      E:\VSCode_Project\CesIceApiTest-v4.40.0-win64.zip

  脚本是幂等的，可以反复执行；下载物缓存在 .build_cache\ 里，二次执行不再下载。

  设计要点（改动前请先读）：
    * 运行时用 Python 官方嵌入式发行版，而**不是** PyInstaller 全量打包。
      Ice 的原生扩展 IcePy.cp310-win_amd64.pyd 在 PyInstaller 下很容易出现
      "开发机能跑、换机器就崩"，带一个真实的 Python 环境更稳、也更好排查。
    * IcePy 的文件名带 cp310-win_amd64，所以运行时**必须是 64 位 Python 3.10**。
    * 必须随包带 msvcp140.dll / vcruntime140.dll（VC++ 运行库），
      这两个不是干净 Windows 自带的，缺了会在 import Ice 时报 DLL load failed。
    * Java 用 Temurin/Adoptium，**不要用 Oracle JDK** —— 后者授权不允许再分发。
#>

$ErrorActionPreference = 'Stop'

# ==================================================================== 配置
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OutputRoot  = 'E:\VSCode_Project'
$Stage       = Join-Path $OutputRoot 'CesIceApiTest-v4.40.0-win64'
$Cache       = Join-Path $ProjectRoot '.build_cache'

$PyEmbedUrl = 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip'
$JreUrl     = 'https://api.adoptium.net/v3/binary/latest/8/ga/windows/x64/jre/hotspot/normal/eclipse'
$GetPipUrl  = 'https://bootstrap.pypa.io/get-pip.py'

# 本机已装好的 Allure 位置（换机器打包时改这里）
$LocalAllure  = 'E:\allure-2.18.1'
$AllureDirName = 'allure-2.18.1'

# 只复制这些源码；其余一律不进包（尤其那 6 个一次性工具脚本含硬编码凭据）
$SourceFiles = @(
    'pytest.ini',
    'runner.py', 'launcher.py',
    'method.py', 'conftest.py', 'setup_path.py', 'test_api_all.py',
    'requirements-min.txt', 'README.md'
)
$SourceDirs  = @('common', 'generated', 'ice_files', 'data', 'tests', 'docs', 'tools')

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Die($msg)  { Write-Host "`n[错误] $msg" -ForegroundColor Red; exit 1 }

function Get-Cached($url, $dest) {
    if (Test-Path $dest) { Write-Host "  用缓存 $dest"; return }
    Write-Host "  下载 $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
}

# ==================================================================== 0 准备
Step "0/8 准备目录"
New-Item -ItemType Directory -Force -Path $Stage, $Cache | Out-Null
Write-Host "  输出目录: $Stage"
Write-Host "  缓存目录: $Cache"

# ==================================================================== 1 下载
Step "1/8 下载 Python 嵌入式运行时与 JRE"
$PyZip  = Join-Path $Cache 'python-embed.zip'
$JreZip = Join-Path $Cache 'temurin-jre8.zip'
$GetPip = Join-Path $Cache 'get-pip.py'
Get-Cached $PyEmbedUrl $PyZip
Get-Cached $JreUrl     $JreZip
Get-Cached $GetPipUrl  $GetPip

# ==================================================================== 2 runtime
Step "2/8 组装 runtime\（Python + 依赖 + VC++ 运行库）"
$Runtime = Join-Path $Stage 'runtime'
Remove-Item -Recurse -Force $Runtime -ErrorAction SilentlyContinue
Expand-Archive -Path $PyZip -DestinationPath $Runtime -Force

# 让嵌入式运行时能用 site-packages（默认是隔离模式，装了包也 import 不到）
$Pth = Join-Path $Runtime 'python310._pth'
@('python310.zip', '.', 'Lib\site-packages', '', 'import site') |
    Set-Content -Path $Pth -Encoding ASCII

$Py = Join-Path $Runtime 'python.exe'
if (-not (Test-Path $Py)) { Die "解压后没找到 $Py" }

Write-Host "  安装 pip ..."
& $Py $GetPip --no-warn-script-location -q
if ($LASTEXITCODE -ne 0) { Die "pip 安装失败" }

Write-Host "  安装依赖（requirements-min.txt）..."
& $Py -m pip install --no-warn-script-location -q -r (Join-Path $ProjectRoot 'requirements-min.txt')
if ($LASTEXITCODE -ne 0) { Die "依赖安装失败" }

# VC++ 运行库：app-local 放在 python.exe 旁边，目标机不需要装组件包
Write-Host "  补 VC++ 运行库 ..."
foreach ($dll in @('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll')) {
    $dst = Join-Path $Runtime $dll
    if (Test-Path $dst) { Write-Host "    已有 $dll"; continue }
    $src = Join-Path $env:SystemRoot "System32\$dll"
    if (-not (Test-Path $src)) { Die "本机 System32 里没有 $dll，无法打包" }
    Copy-Item $src $dst
    Write-Host "    补入 $dll"
}

# ==================================================================== 3 tools
Step "3/8 组装 tools\（JRE + Allure）"
$Tools = Join-Path $Stage 'tools'
Remove-Item -Recurse -Force $Tools -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Tools | Out-Null

# JRE：解压后顶层是 jdkXuXX-bXX-jre 这样的目录，拉平成 tools\jre8
$JreTmp = Join-Path $Cache 'jre_tmp'
Remove-Item -Recurse -Force $JreTmp -ErrorAction SilentlyContinue
Expand-Archive -Path $JreZip -DestinationPath $JreTmp -Force
$JreInner = Get-ChildItem $JreTmp -Directory | Select-Object -First 1
if (-not $JreInner) { Die "JRE 压缩包结构不认识" }
Move-Item $JreInner.FullName (Join-Path $Tools 'jre8')
Remove-Item -Recurse -Force $JreTmp

# Allure
if (-not (Test-Path $LocalAllure)) { Die "找不到本机 Allure: $LocalAllure" }
Copy-Item $LocalAllure (Join-Path $Tools $AllureDirName) -Recurse -Force

# ==================================================================== 4 源码
Step "4/8 复制源码与用例"
Get-ChildItem $Stage -File | Where-Object { $_.Name -notin @('启动测试.exe') } | Remove-Item -Force
foreach ($d in $SourceDirs) {
    $dst = Join-Path $Stage $d
    Remove-Item -Recurse -Force $dst -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $ProjectRoot $d) $dst -Recurse
}
foreach ($f in $SourceFiles) {
    Copy-Item (Join-Path $ProjectRoot $f) (Join-Path $Stage $f) -Force
}
# 清掉 __pycache__，避免把开发机的字节码带出去
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ==================================================================== 5 exe
Step "5/8 构建启动器 exe"
& python -m PyInstaller `
    --onefile --console --noconfirm `
    --name '启动测试' `
    --distpath $Stage `
    --workpath (Join-Path $Cache 'pyi_build') `
    --specpath $Cache `
    (Join-Path $ProjectRoot 'launcher.py')
if ($LASTEXITCODE -ne 0) { Die "PyInstaller 构建失败" }

# ==================================================================== 6 文档
Step "6/8 复制交付文档"
foreach ($f in @('使用说明.txt', '依赖清单.txt')) {
    Copy-Item (Join-Path $PSScriptRoot $f) (Join-Path $Stage $f) -Force
}
Copy-Item (Join-Path $ProjectRoot 'docs\gateway-testing.md') (Join-Path $Stage '使用说明.txt') -Force

# ==================================================================== 7 自检
Step "7/8 自检"
# 网关和SSH地址只来自common/config.py，不交付第二份服务器配置。
if (Test-Path -LiteralPath (Join-Path $Stage 'config.ini')) { Die "交付目录仍有旧INI配置，请检查源码复制清单" }
# 这一条同时验证 IcePy.pyd 与 VC++ 运行库能否加载
& $Py -c "import Ice,pytest,allure,openpyxl,sys; print('  Ice', Ice.stringVersion(), '| Python', sys.version.split()[0]); print('  依赖全部可导入')"
if ($LASTEXITCODE -ne 0) { Die "依赖自检失败" }

& $Py -c "import sys; sys.path.insert(0, sys.argv[1]); from common.config import SERVER_HOST, TEST_CONFIG, ICE_CONFIG; assert TEST_CONFIG['host'] == TEST_CONFIG['database']['host'] == SERVER_HOST; assert SERVER_HOST in ICE_CONFIG['locator']; print('  单一服务器配置自检通过')" $Stage
if ($LASTEXITCODE -ne 0) { Die "配置自检失败" }

& (Join-Path $Stage 'tools\jre8\bin\java.exe') -version 2>&1 | Select-Object -First 1 | ForEach-Object { Write-Host "  $_" }

$Size = '{0:N0} MB' -f ((Get-ChildItem $Stage -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "  包体积: $Size"

# ==================================================================== 8 打包
Step "8/8 打成 zip"
$Zip = "$Stage.zip"
Remove-Item -Force $Zip -ErrorAction SilentlyContinue
# 连顶层目录一起打，解压后直接得到 CesIceApiTest-v4.40.0-win64\ 目录
Compress-Archive -Path $Stage -DestinationPath $Zip -CompressionLevel Optimal
Write-Host ("  zip: {0} ({1:N0} MB)" -f $Zip, ((Get-Item $Zip).Length / 1MB))

Write-Host "`n打包完成。" -ForegroundColor Green
Write-Host "  目录: $Stage"
Write-Host "  zip : $Zip"
Write-Host "`n分发前请注意：data\test_cases.xlsx 是当前工作副本，"
Write-Host "确认里面没有残留的调试改动。"
