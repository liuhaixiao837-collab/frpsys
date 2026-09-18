"""检查业务源码和模型是否具有完整中文说明。"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_APP_PREFIXES = ('ops', 'platform_logs', 'data_security', 'identity')


def contains_chinese(text: str) -> bool:
    """判断说明文字是否包含中文字符。"""
    return bool(re.search(r'[\u4e00-\u9fff]', text or ''))


def maintained_python_files():
    """产生需要执行说明检查的业务 Python 源文件，排除迁移、测试和生成目录。"""
    for path in sorted(BACKEND_ROOT.rglob('*.py')):
        if any(part in {'migrations', '__pycache__', '.venv', 'venv'} for part in path.parts):
            continue
        if path.name.startswith('test') or path.name == 'tests.py':
            continue
        yield path


def source_documentation_issues() -> list[str]:
    """扫描函数、方法和业务模型类，返回缺少中文说明的位置。"""
    issues = []
    for path in maintained_python_files():
        relative_path = path.relative_to(BACKEND_ROOT)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(relative_path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not contains_chinese(ast.get_docstring(node) or ''):
                    issues.append(f'{relative_path}:{node.lineno} 函数 {node.name} 缺少中文用途说明')
                continue
            if not isinstance(node, ast.ClassDef) or node.name == 'Meta':
                continue
            is_model = any(
                (isinstance(base, ast.Name) and base.id.endswith('Model'))
                or (isinstance(base, ast.Attribute) and base.attr == 'Model')
                for base in node.bases
            )
            if is_model and not contains_chinese(ast.get_docstring(node) or ''):
                issues.append(f'{relative_path}:{node.lineno} 模型 {node.name} 缺少中文职责说明')
    return issues


def model_field_issues() -> list[str]:
    """加载 Django 业务模型并返回缺少中文字段说明的字段。"""
    sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

    import django
    from django.apps import apps

    django.setup()
    issues = []
    for model in apps.get_models():
        if not model.__module__.startswith(PROJECT_APP_PREFIXES):
            continue
        for field in [*model._meta.fields, *model._meta.many_to_many]:
            if not contains_chinese(str(field.help_text or '')):
                issues.append(f'{model._meta.label}.{field.name} 缺少中文 help_text')
    return issues


def main() -> int:
    """运行全部说明检查，打印问题并用进程退出码表示检查结果。"""
    issues = [*source_documentation_issues(), *model_field_issues()]
    if issues:
        print('中文代码说明检查失败：')
        for issue in issues:
            print(f'- {issue}')
        return 1
    print('中文代码说明检查通过：函数、方法、模型和模型字段均有中文说明。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
