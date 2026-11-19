# =====================================================================
# 浏览器接口（图隐网页版：在 Pyodide 中运行，文件只在本机内存里）
# =====================================================================

WEB_ROOT = "/drawveil"


def _web_notes(j):
    a = j.get("analysis", {})
    notes = []
    if a.get("unknown"):
        notes.append("含非标准对象 %s（多为天正对象，其内部文字可能处理不到）" % "、".join(
            "%s×%d" % kv for kv in sorted(a["unknown"].items(), key=lambda x: -x[1])[:4]))
    if a.get("sig_blocks"):
        notes.append("签名/印章类图块：%s" % "、".join(dxf_unescape(x) for x in a["sig_blocks"][:6]))
    if a.get("ole"):
        notes.append("含 OLE 嵌入对象 %d 个，请人工确认内容" % a["ole"])
    if a.get("geodata"):
        notes.append("含地理位置信息，可在 CAD 中执行 GEOREMOVE 删除")
    if a.get("images"):
        notes.append("光栅图片引用 %d 个（路径会去除，外发时不要附带公章/签名图片文件）" % a["images"])
    return notes


def _web_deletions(j):
    d = defaultdict(int)
    for _, why in j.get("analysis", {}).get("delete_recs", []):
        d[why] += 1
    return dict(d)


def web_reset():
    shutil.rmtree(WEB_ROOT, ignore_errors=True)
    os.makedirs(os.path.join(WEB_ROOT, "in"))
    return WEB_ROOT + "/in"


def _web_files():
    d = os.path.join(WEB_ROOT, "in")
    return [(os.path.join(d, f), f) for f in sorted(os.listdir(d)) if f.lower().endswith(".dxf")]


def _web_cfg(cfg_json):
    c = json.loads(cfg_json or "{}")
    return merge_config(c)


def web_scan(cfg_json, log=None):
    logs = []
    lg = log or logs.append
    res = run_pipeline([], None, _web_cfg(cfg_json), dry_run=True, log=lg, files=_web_files())
    terms = [{"term": e["term"], "replace": e["replace"], "cat": e["cat"], "catName": CAT_NAMES.get(e["cat"], e["cat"]),
              "rule": e["rule"], "count": e["count"], "locs": e["locs"][:3], "enabled": e["enabled"],
              "warn": "出现 %d 次，偏多，请确认是人名" % e["count"] if e["cat"] == "person" and e["count"] > 40 else ""}
             for e in res["mapping"].values()]
    files = []
    for j in res["jobs"]:
        a = j.get("analysis", {})
        files.append({"name": j["rel"], "error": j["error"], "acadver": a.get("acadver", ""), "encoding": a.get("encoding", ""),
                      "entities": sum(a.get("counts", {}).values()), "notes": _web_notes(j), "deletions": _web_deletions(j)})
    return json.dumps({"terms": terms, "files": files, "log": logs}, ensure_ascii=False)


def web_apply(cfg_json, decisions_json, log=None):
    logs = []
    lg = log or logs.append
    out = os.path.join(WEB_ROOT, "out")
    rep = os.path.join(WEB_ROOT, "report")
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(rep, ignore_errors=True)
    cfg = _web_cfg(cfg_json)
    cfg["output_format"] = "dxf"
    res = run_pipeline([], out, cfg, report_dir=rep, decisions=json.loads(decisions_json or "{}"), log=lg, files=_web_files())
    files = []
    for j in res["jobs"]:
        v = j.get("verify") or {}
        files.append({"name": j["rel"], "error": j["error"], "output": os.path.basename(j.get("output") or ""),
                      "changes": len(j.get("changes", [])), "removed": j.get("removed", []),
                      "geometry": v.get("geometry", ""), "geometry_ok": v.get("geometry_ok", False),
                      "residual": [x["term"] for x in v.get("residual", [])][:10],
                      "binary_residual": [x["term"] for x in v.get("binary_residual", [])][:10],
                      "entities": sum(j.get("analysis", {}).get("counts", {}).values()),
                      "deletions": _web_deletions(j)})

    def zipdir(src, dst):
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, fs in os.walk(src):
                for f in fs:
                    full = os.path.join(root, f)
                    z.write(full, os.path.relpath(full, src))
    zipdir(out, os.path.join(WEB_ROOT, "drawings.zip"))
    zipdir(rep, os.path.join(WEB_ROOT, "report.zip"))
    enabled = [e for e in res["mapping"].values() if e["enabled"]]
    return json.dumps({"files": files, "log": logs, "terms": len(enabled),
                       "outputs": [os.path.relpath(j["output"], out) for j in res["jobs"] if j.get("output")],
                       "report_html": os.path.join(rep, "脱敏报告.html")}, ensure_ascii=False)


def web_samples(samples_src):
    d = os.path.join(WEB_ROOT, "in")
    old = sys.argv
    try:
        sys.argv = ["make_samples.py", d]
        exec(compile(samples_src, "make_samples.py", "exec"), {"__name__": "__main__", "__file__": "make_samples.py"})
    finally:
        sys.argv = old
    return json.dumps(sorted(f for f in os.listdir(d) if f.lower().endswith(".dxf")), ensure_ascii=False)
