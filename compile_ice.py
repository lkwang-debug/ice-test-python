#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import shutil
import re
from pathlib import Path


def fix_imports_and_move(src_path, dest_path):
    """修正导入并移动文件"""
    if not src_path.exists():
        print(f"错误: 源文件不存在 {src_path}")
        return False

    # 读取内容并修正导入
    with open(src_path, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(r'CommonModel_?[iI]ce', 'CommonModel', content)
    content = re.sub(r'CommonService_?[iI]ce', 'CommonService', content)
    content = re.sub(r'from com\.hst\.proxy(\.model)? import CommonModel',
                     'from com.hst.proxy.model import CommonModel', content)

    # 确保目标目录存在
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入新位置
    with open(dest_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"已处理: {src_path.name} -> {dest_path}")
    return True


def compile_ice_files():
    # 配置路径
    base_dir = Path(__file__).parent
    ice_dir = base_dir / "ice_files"
    output_dir = base_dir / "generated"

    # 清理旧目录
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir()

    # 编译函数 - 直接生成到临时目录
    def compile(file):
        temp_dir = output_dir / "temp"
        temp_dir.mkdir(exist_ok=True)

        cmd = [
            "slice2py",
            "-I", str(ice_dir),
            "--output-dir", str(temp_dir),
            str(ice_dir / file)
        ]
        print(f"正在编译: {file}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"编译错误({result.returncode}):", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            raise subprocess.CalledProcessError(result.returncode, cmd)
        print(result.stdout)

        # 返回生成的文件列表
        return list(temp_dir.glob("*.py"))

    # 1. 编译模型文件
    print("第一步：编译数据模型...")
    model_files = compile("CommonModel.ice")

    # 2. 编译服务接口
    print("\n第二步：编译服务接口...")
    service_files = compile("CommonService.ice")

    # 目标目录结构
    model_dir = output_dir / "com" / "hst" / "proxy" / "model"
    service_dir = output_dir / "com" / "hst" / "proxy" / "service" / "common"

    # 3. 处理生成的文件
    print("\n第三步：整理生成的文件...")
    for file in model_files + service_files:
        if "CommonModel" in file.name:
            fix_imports_and_move(file, model_dir / "CommonModel.py")
        elif "CommonService" in file.name:
            fix_imports_and_move(file, service_dir / "CommonService.py")

    # 4. 创建必要的__init__.py
    print("\n第四步：初始化包结构...")
    init_files = {
        model_dir / "__init__.py": [
            "from .CommonModel import Request, Response"
        ],
        service_dir / "__init__.py": [
            "from ....model.CommonModel import Request, Response",
            "from .CommonService import CommonServicePrx"
        ],
        output_dir / "__init__.py": None,
        output_dir / "com" / "__init__.py": None,
        output_dir / "com" / "hst" / "__init__.py": None,
        output_dir / "com" / "hst" / "proxy" / "__init__.py": None,
        output_dir / "com" / "hst" / "proxy" / "service" / "__init__.py": None
    }

    for path, imports in init_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            if imports:
                f.write("\n".join(imports) + "\n")
            f.write("__all__ = []\n")
        print(f"创建: {path.relative_to(output_dir)}")

    # 清理临时目录
    shutil.rmtree(output_dir / "temp", ignore_errors=True)

    print("\n✅ 编译完成！最终文件结构:")
    print(f"请执行: tree /F {output_dir}")
    print(
        "验证导入: python -c \"import sys; sys.path.append('generated'); from com.hst.proxy.model import Request; print('导入成功！')\"")





if __name__ == "__main__":
    try:
        compile_ice_files()
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}", file=sys.stderr)
        sys.exit(1)