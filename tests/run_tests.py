# -*- coding: utf-8 -*-
"""回归测试：python3 tests/run_tests.py"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import cad_desensitize as C  # noqa: E402

tmp = tempfile.mkdtemp(prefix="cad_test_")
fails = 0


def check(cond, msg):
    global fails
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        fails += 1


try:
    subprocess.check_call([sys.executable, os.path.join(HERE, "make_samples.py"), os.path.join(tmp, "in")],
                          stdout=subprocess.DEVNULL)
    src = os.path.join(tmp, "in")

    print("1. 关闭全部规则时，输出与原文件逐字节相同")
    cfg = C.merge_config({"options": {k: False for k, _, _, _ in C.OPTION_INFO}})
    C.run_pipeline([src], os.path.join(tmp, "o1"), cfg, log=lambda *a: None)
    for f in ("样例_新版UTF8", "样例_旧版GBK", "样例_会签栏与单位"):
        a = open(os.path.join(src, f + ".dxf"), "rb").read()
        b = open(os.path.join(tmp, "o1", f + "_脱敏.dxf"), "rb").read()
        check(a == b, f)

    print("2. 默认规则")
    res = C.run_pipeline([src], os.path.join(tmp, "o2"), C.merge_config(None),
                         report_dir=os.path.join(tmp, "rep"), log=lambda *a: None)
    m = res["mapping"]
    for t in ("张伟", "李娜", "王建国", "陈晓东", "周敏", "杭州明湖花园二期", "明湖花园", "杭州明湖示例置业有限公司",
              "浙江青禾示例建筑设计研究院有限公司", "HC2023-JZ-015", "13812345678", "0571-87654321"):
        check(t in m, "识别：" + t)
    for j in res["jobs"]:
        v = j["verify"]
        if "会签栏" in j["rel"]:
            sign_job = j
            continue
        check(v["geometry_ok"], j["rel"] + " 几何一致：" + v["geometry"])
        check(not v["residual"], j["rel"] + " 无文字残留")
        out = C.DxfDoc(j["output"])
        txt = C.dxf_unescape("\n".join(p[1] for p in out.pairs))
        for keep in ("C30", "HRB400", "±0.000", "5.300m", "建施-01", "1:100", "22G101", "中国建筑标准设计研究院",
                     "X=3345678.123", "A-WALL", "monochrome.ctb", "底图.dwg"):
            check(keep in txt, j["rel"] + " 保留设计信息：" + keep)
        for gone in ("张伟", "明湖", "青禾示例建筑", "13812345678", "zhangwei@", "D:\\", "C:\\Users", "HC-PRINT01",
                     "THUMBNAILIMAGE", "PE_URL\n1000\nhttp"):
            check(gone not in txt, j["rel"] + " 已清除：" + gone.replace("\n", " "))
    check(os.path.isfile(os.path.join(tmp, "rep", "脱敏报告.html")), "生成报告")

    print("3. 会签栏、手写签名、中英文单位名、Logo")
    j = sign_job
    check(j["verify"]["geometry_ok"] and not j["verify"]["residual"], "几何一致、无残留")
    for t in ("赵一鸣", "孙昊", "孙    昊", "苏晴", "何志远", "林岚", "云溪市示例建筑设计研究院有限公司",
              "Yunxi Example Architectural Design Institute Co.,Ltd."):
        check(t in m, "识别：" + t)
    check(m["Yunxi Example Architectural Design Institute Co.,Ltd."]["replace"] == m["云溪市示例建筑设计研究院有限公司"]["replace"],
          "英文名与中文名使用同一代号")
    check(m["孙    昊"]["replace"] == m["孙昊"]["replace"], "“孙    昊”与“孙昊”同一代号")
    out = C.DxfDoc(j["output"])
    from collections import Counter
    cnt = Counter((r.type, (out.rget(r, 8) or "").strip()) for r in out.recs if r.section in ("ENTITIES", "BLOCKS"))
    check(cnt[("LINE", "TK")] == 18, "表格线 18 条全部保留")
    check(cnt[("CIRCLE", "A-WALL")] == 1 and cnt[("LWPOLYLINE", "A-WALL")] == 1, "旁边的设计图形保留")
    check(not any(k[1] in ("SIGN", "LOGO") for k in cnt), "签名笔迹、签名图块内容、Logo 全部删除")
    texts = [C.dxf_unescape(out.rget(r, 1) or "") for r in out.recs if r.type == "TEXT"]
    for keep in ("审    定", "项目负责人", "版本号", "2025.07", "建筑工程甲级资质", "设计单位"):
        check(keep in texts, "保留：" + keep)
    check("苏" not in texts and "晴" not in texts, "逐字书写的“苏 晴”已替换")

    print("4. 误报检查（这些都不应被识别）")
    d = C.Detector(C.merge_config(None))
    for t in ("设计使用年限：50年", "施工单位应具有相应资质的专业公司施工", "电梯由业主指定厂家深化设计",
              "请与当地供电局联系", "图号：结施-03", "KL1(2) 300x600", "±0.000相当于绝对标高12.350",
              "详见国标图集12J201，中国建筑标准设计研究院出版", "2023-05-12", "Φ8@100/200(2)"):
        check(not d.detect_text(t), t)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n全部通过" if not fails else "\n失败 %d 项" % fails)
sys.exit(1 if fails else 0)
