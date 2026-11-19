# -*- coding: utf-8 -*-
"""从 cad_desensitize.py 生成浏览器用的引擎 engine.py（去掉本地 GUI 和命令行，加上网页接口）。"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
src = open(os.path.join(ROOT, "cad_desensitize.py"), encoding="utf-8").read()
cut = src.index("# =====================================================================\n# 图形界面（本地网页）")
core = src[:cut]
core = core.replace("import subprocess\n", "try:\n    import subprocess\nexcept ImportError:  # 浏览器里没有\n    subprocess = None\n")
core = core.replace("import threading\n", "").replace("import webbrowser\n", "")
api = open(os.path.join(HERE, "web_api.py"), encoding="utf-8").read()
out = core + api
os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
open(os.path.join(HERE, "dist", "engine.py"), "w", encoding="utf-8").write(out)
print("engine.py", len(out.encode("utf-8")), "bytes")

# 精简：去掉注释和文档字符串（体积小一半左右，逻辑不变）
import ast


def slim(code):
    t = ast.parse(code)
    for n in ast.walk(t):
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module, ast.AsyncFunctionDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and \
                isinstance(n.body[0].value.value, str):
            n.body = n.body[1:] or [ast.Pass()]
    return ast.unparse(t) + "\n"


slim_engine = slim(out)
open(os.path.join(HERE, "dist", "engine.min.py"), "w", encoding="utf-8").write(slim_engine)
samples = open(os.path.join(ROOT, "tests", "make_samples.py"), encoding="utf-8").read()
open(os.path.join(HERE, "dist", "samples.min.py"), "w", encoding="utf-8").write(slim(samples))
print("engine.min.py", len(slim_engine.encode("utf-8")), "samples.min.py", len(slim(samples).encode("utf-8")))
