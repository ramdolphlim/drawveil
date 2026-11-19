# -*- coding: utf-8 -*-
"""DWG 流程测试（不需要真的转换器）：用“假转换器”把 DXF 原样当 DWG 复制，检查
ODA 优先 / LibreDWG 兜底 / 都没有时降级为 DXF / 回读核对 的接线是否正确。
有真转换器时另外跑：python3 tests/test_dwg_flow.py 真实图纸.dwg"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import cad_desensitize as C  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        fails += 1


def script(path, body):
    with open(path, "w") as f:
        f.write("#!/usr/bin/env python3\nimport sys, os, shutil, glob\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


def real(dwg, out=None, converter="auto"):
    cfg = C.merge_config({"dwg_converter": converter})
    t = C.dwg_tools(cfg)
    print("转换器：ODA=%s  LibreDWG=%s" % (t["oda"], t["libredwg"] and t["libredwg"]["dwg2dxf"]))
    print("原图版本：DWG %s" % C.DWG_LABEL.get(C.dwg_version_of(dwg), "未知"))
    out = out or tempfile.mkdtemp(prefix="dwg_real_")
    import time
    t0 = time.time()
    res = C.run_pipeline([dwg], out, cfg, report_dir=os.path.join(out, "_脱敏报告(含原文,勿外发)"))
    print("用时 %.1f 秒" % (time.time() - t0))
    for j in res["jobs"]:
        v = j.get("verify") or {}
        print("输出：", j.get("output"), " 错误：", j.get("error"))
        print("DXF 校验：", v.get("geometry"), " 残留：", v.get("residual"))
        print("DWG 回读：", (v.get("dwg") or {}).get("readback"), " 残留：", (v.get("dwg") or {}).get("residual"))
        for n in j.get("notes", []):
            print("提示：", n)
    print("敏感词 %d 项，报告：%s" % (len(res["mapping"]), os.path.join(out, "_脱敏报告(含原文,勿外发)", "脱敏报告.html")))
    return 0 if all(not j.get("error") and (j.get("verify") or {}).get("ok") for j in res["jobs"]) else 1


if len(sys.argv) > 1:
    sys.exit(real(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else "auto"))

tmp = tempfile.mkdtemp(prefix="dwg_flow_")
try:
    subprocess.check_call([sys.executable, os.path.join(HERE, "make_samples.py"), os.path.join(tmp, "in")],
                          stdout=subprocess.DEVNULL)
    src = os.path.join(tmp, "in", "样例_会签栏与单位.dxf")
    dwg = os.path.join(tmp, "in", "图.dwg")
    with open(src, "rb") as f:
        data = f.read()
    with open(dwg, "wb") as f:
        f.write(data)
    # 假 ODA：ODAFileConverter 入目录 出目录 版本 类型 递归 审核 过滤
    oda = os.path.join(tmp, "ODAFileConverter")
    script(oda, """i, o, ver, typ = sys.argv[1:5]
open(os.path.join(o, 'oda_calls.log'), 'a').write(ver + ' ' + typ + '\\n')
for p in glob.glob(os.path.join(i, '*')):
    shutil.copy(p, os.path.join(o, os.path.splitext(os.path.basename(p))[0] + '.' + typ.lower()))
open(os.path.join(os.path.dirname(sys.argv[0]), 'oda.log'), 'a').write(ver + ' ' + typ + '\\n')
""")
    lib = os.path.join(tmp, "libredwg")
    os.makedirs(lib)
    body = """a = sys.argv[1:]
out = a[a.index('-o') + 1]
shutil.copy(a[-1], out)
open(os.path.join(os.path.dirname(sys.argv[0]), 'calls.log'), 'a').write(' '.join(a[:-3]) + '\\n')
"""
    script(os.path.join(lib, "dwg2dxf"), body)
    script(os.path.join(lib, "dxf2dwg"), body)

    def run(cfgx, name):
        cfg = C.merge_config(dict({"oda_converter": "/不存在"}, **cfgx))
        out = os.path.join(tmp, name)
        res = C.run_pipeline([dwg], out, cfg, log=lambda *a: None)
        return res["jobs"][0], out

    old_find = C.find_oda
    print("1. 只有 ODA")
    C.find_oda = lambda cfg=None: oda
    os.environ.pop("LIBREDWG_DIR", None)
    j, out = run({}, "o1")
    check(j.get("converter") == "oda", "用 ODA 读取")
    check(j.get("output", "").endswith("_脱敏.dwg"), "输出 DWG")
    check(j.get("out_converter") == "oda" and j.get("out_version") == "ACAD2018", "ODA 写出，认不出原版本时用 2018")
    dv = (j.get("verify") or {}).get("dwg") or {}
    check(dv.get("ok") and dv.get("count_ok") and dv.get("geometry_ok"), "DWG 回读核对通过：" + dv.get("readback", ""))
    check(j["verify"]["ok"], "总校验通过")

    print("2. 原版本保留")
    with open(dwg, "wb") as f:
        f.write(data)  # 文件头不是 ACxxxx，单独测函数
    v = os.path.join(tmp, "v.dwg")
    open(v, "wb").write(b"AC1021" + b"\0" * 20)
    check(C.dwg_version_of(v) == "ACAD2007", "AC1021 → ACAD2007")
    got = C.dxf_to_dwg(src, tmp, C.merge_config({"dwg_version": "same"}), "ACAD2007",
                       {"oda": oda, "libredwg": None, "read": "oda", "write": "oda"})
    check(got[2] == "ACAD2007" and "ACAD2007 DWG" in open(os.path.join(tmp, "oda.log")).read(), "same → 按原图 2007 写出")
    got = C.dxf_to_dwg(src, tmp, C.merge_config({"dwg_version": "ACAD2013"}), "ACAD2007",
                       {"oda": oda, "libredwg": None, "read": "oda", "write": "oda"})
    check(got[2] == "ACAD2013", "指定 2013 时按 2013 写出")

    print("3. 没有 ODA，用 LibreDWG 兜底")
    C.find_oda = lambda cfg=None: None
    os.environ["LIBREDWG_DIR"] = lib
    j, out = run({}, "o3")
    check(j.get("converter") == "libredwg", "用 LibreDWG 读取")
    check(j.get("output", "").endswith(".dwg") and j.get("out_version") == "ACAD2000", "LibreDWG 写出 DWG 2000")
    check(any("实验" in n for n in j.get("notes", [])), "提示实验功能")
    check("--as r2000" in open(os.path.join(lib, "calls.log")).read(), "调用 dxf2dwg --as r2000")
    check((j["verify"].get("dwg") or {}).get("ok"), "回读核对通过")

    print("4. LibreDWG 只有读没有写")
    os.rename(os.path.join(lib, "dxf2dwg"), os.path.join(lib, "dxf2dwg.off"))
    j, out = run({}, "o4")
    check(j.get("output", "").endswith(".dxf"), "降级输出 DXF")
    check(any("无法输出 DWG" in n for n in j.get("notes", [])), "说明原因")
    os.rename(os.path.join(lib, "dxf2dwg.off"), os.path.join(lib, "dxf2dwg"))

    print("5. LibreDWG 写坏（回读少了图元）→ 另存 DXF 备用")
    script(os.path.join(lib, "dxf2dwg"), """a = sys.argv[1:]
out = a[a.index('-o') + 1]
t = open(a[-1], 'rb').read()
i = t.index(b'ENTITIES'); k = t.index(b'\\n  0\\n', i + 20); k2 = t.index(b'\\n  0\\n', k + 5)
open(out, 'wb').write(t[:k] + t[k2:])
""")
    j, out = run({}, "o5")
    dv = j["verify"].get("dwg") or {}
    check(not dv.get("count_ok"), "发现图元数量不一致：" + dv.get("readback", ""))
    check(not j["verify"]["ok"], "总校验标记未通过")
    check(os.path.isfile(os.path.join(out, "图_脱敏.dxf")) and j.get("extra_outputs"), "另存了 DXF 备用")

    print("6. 什么转换器都没有")
    os.environ.pop("LIBREDWG_DIR")
    C.find_libredwg_orig = C.find_libredwg
    C.find_libredwg = lambda cfg=None: None
    j, out = run({}, "o6")
    check(j.get("error") and "ODA" in j["error"], "读 DWG 时报错并提示安装 ODA")
    C.find_libredwg = C.find_libredwg_orig
    C.find_oda = old_find
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("\n全部通过" if not fails else "\n%d 项失败" % fails)
sys.exit(1 if fails else 0)
