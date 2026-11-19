#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图隐 DrawVeil · 桌面版（macOS / Windows）

原生窗口里运行与网页版同一套界面，脱敏引擎（cad_desensitize.py）直接在本机运行：
  * 支持 DWG（通过 ODA File Converter），输出可以放在原文件旁边
  * 批次管理：每个批次单独保存代号库，下一批可以沿用
  * 监视文件夹：把图纸放进去就自动脱敏

运行：
  python3 drawveil_desktop.py            # 原生窗口（需要 pip install pywebview）
  python3 drawveil_desktop.py --browser  # 没装 pywebview 时，用浏览器打开同一界面
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (getattr(sys, "_MEIPASS", ""), HERE, os.path.dirname(HERE)):
    if _p and os.path.isfile(os.path.join(_p, "cad_desensitize.py")) and _p not in sys.path:
        sys.path.insert(0, _p)
import cad_desensitize as C  # noqa: E402

APP_NAME = "图隐 DrawVeil"
APP_VERSION = "1.0.1"
PLATFORM = "mac" if sys.platform == "darwin" else ("win" if os.name == "nt" else "linux")


def resource(*parts):
    return os.path.join(getattr(sys, "_MEIPASS", HERE), *parts)


def data_dir():
    if PLATFORM == "mac":
        d = os.path.expanduser("~/Library/Application Support/DrawVeil")
    elif PLATFORM == "win":
        d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "DrawVeil")
    else:
        d = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "drawveil")
    os.makedirs(d, exist_ok=True)
    return d


def documents_dir():
    d = os.path.expanduser("~/Documents")
    return d if os.path.isdir(d) else os.path.expanduser("~")


ODA_URL = "https://www.opendesign.com/guestfiles/oda_file_converter"


def default_settings():
    cfg = C.DEFAULT_CONFIG
    return {
        "preset": "standard",
        "options": dict(cfg["options"]),
        "keywords": [],
        "whitelist": list(cfg["whitelist"]),
        "pseudonyms": dict(cfg["pseudonyms"]),
        "signature_block_pattern": cfg["signature_block_pattern"],
        "oda_converter": "",
        "dwg_version": "same",            # same：与原 DWG 相同版本
        "dwg_converter": "auto",          # auto：ODA 优先，内置 LibreDWG 兜底
        "output_format": "same",
        "output_mode": "beside",          # beside：原文件旁“脱敏输出”；fixed：统一放到 output_dir
        "output_dir": "",
        "output_suffix": "_脱敏",
        "report_dir": os.path.join(documents_dir(), "图隐报告（内部留存）"),
        "reuse_mapping": True,
        "reveal_after": True,
        "theme": "",
        "watch_enabled": False,
        "watch_dir": "",
        "watch_out_dir": "",
    }


def reveal(path):
    """在访达 / 资源管理器中显示。"""
    try:
        if PLATFORM == "mac":
            subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
        elif PLATFORM == "win":
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                os.startfile(path)  # noqa
        else:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
        return True
    except Exception:
        return False


def open_file(path):
    try:
        if PLATFORM == "mac":
            subprocess.Popen(["open", path])
        elif PLATFORM == "win":
            os.startfile(path)  # noqa
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


class Api(object):
    """界面调用的全部接口（pywebview 的 js_api，或浏览器模式下的 /api/<方法名>）。"""

    def __init__(self, state_path=None):
        self._lock = threading.RLock()
        self._state_path = state_path or os.path.join(data_dir(), "state.json")
        self._logs = []
        self._seq = 0
        self._job = None
        self._scans = {}
        self._window = None
        self._load()
        self._watch_seen = {}
        self._watch_pending = {}
        self._stop = threading.Event()
        threading.Thread(target=self._watch_loop, daemon=True).start()

    # ------------------------------------------------------------ 状态
    def _load(self):
        st = {}
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            pass
        s = default_settings()
        s.update(st.get("settings") or {})
        o = dict(C.DEFAULT_CONFIG["options"])
        o.update(s.get("options") or {})
        s["options"] = o
        self.settings = s
        self.batches = st.get("batches") or []
        self.current = st.get("current")
        if not self.batches:
            self._new_batch("第 1 批")
        if not any(b["id"] == self.current for b in self.batches):
            self.current = self.batches[0]["id"]

    def _save(self):
        with self._lock:
            tmp = self._state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"settings": self.settings, "batches": self.batches, "current": self.current}, f,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self._state_path)

    def _batch(self, bid=None):
        bid = bid or self.current
        for b in self.batches:
            if b["id"] == bid:
                return b
        raise ValueError("批次不存在")

    def _new_batch(self, name, inherit=None):
        b = {"id": uuid.uuid4().hex[:12], "name": name, "files": [], "mapping": [], "inherit": inherit,
             "created": time.strftime("%Y-%m-%d %H:%M"), "watch": False}
        self.batches.append(b)
        self.current = b["id"]
        return b

    def log(self, text):
        with self._lock:
            self._seq += 1
            self._logs.append({"seq": self._seq, "t": time.strftime("%H:%M:%S"), "text": str(text)})
            if len(self._logs) > 600:
                self._logs = self._logs[-400:]

    # ------------------------------------------------------------ 给界面
    def get_state(self):
        oda = C.find_oda(self.settings)
        lib = C.find_libredwg(self.settings)
        return {
            "app": APP_NAME, "version": APP_VERSION, "platform": PLATFORM,
            "settings": self.settings, "current": self.current,
            "batches": [self._batch_view(b) for b in self.batches],
            "oda": oda or "", "odaVersion": self._oda_version(oda),
            "libredwg": bool(lib and lib.get("dxf2dwg")), "libredwgRead": bool(lib),
            "odaUrl": ODA_URL,
            "options": [list(x) for x in C.OPTION_INFO], "cats": C.CAT_NAMES,
            "defaults": default_settings(),
        }

    def _oda_version(self, oda):
        if not oda:
            return ""
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", oda)
        return m.group(1) if m else "已安装"

    def _batch_view(self, b):
        return {"id": b["id"], "name": b["name"], "inherit": b.get("inherit"), "watch": b.get("watch", False),
                "created": b.get("created", ""), "mappingCount": len(b.get("mapping") or []),
                "files": b["files"]}

    def select_batch(self, bid):
        self._batch(bid)
        self.current = bid
        self._save()
        return self.get_state()

    def new_batch(self, name, inherit=None):
        name = (name or "").strip() or "第 %d 批" % (len(self.batches) + 1)
        if inherit and not self.settings.get("reuse_mapping"):
            inherit = None
        if inherit is None and self.settings.get("reuse_mapping") and self.batches:
            inherit = self._batch().get("id")
        self._new_batch(name, inherit)
        self._save()
        return self.get_state()

    def rename_batch(self, bid, name):
        b = self._batch(bid)
        if (name or "").strip():
            b["name"] = name.strip()
            self._save()
        return self.get_state()

    def delete_batch(self, bid):
        self.batches = [b for b in self.batches if b["id"] != bid]
        for b in self.batches:
            if b.get("inherit") == bid:
                b["inherit"] = None
        if not self.batches:
            self._new_batch("第 1 批")
        if self.current == bid:
            self.current = self.batches[0]["id"]
        self._save()
        return self.get_state()

    def save_settings(self, s):
        s = dict(s or {})
        if "options" in s:
            o = dict(self.settings["options"])
            o.update(s["options"])
            s["options"] = o
        self.settings.update(s)
        self._save()
        return self.get_state()

    def reset_settings(self):
        self.settings = default_settings()
        self._save()
        return self.get_state()

    def detect_oda(self, path=None):
        cfg = dict(self.settings)
        if path is not None:
            cfg["oda_converter"] = path
        p = C.find_oda(cfg)
        return {"path": p or "", "version": self._oda_version(p), "ok": bool(p)}

    # ------------------------------------------------------------ 文件
    def add_paths(self, paths, bid=None):
        b = self._batch(bid)
        have = set(f["path"] for f in b["files"])
        n = 0
        for p in paths or []:
            p = os.path.abspath(os.path.expanduser(str(p)))
            if os.path.isdir(p):
                for src, _ in C.collect_inputs([p]):
                    if src not in have:
                        b["files"].append(self._file_entry(src))
                        have.add(src)
                        n += 1
            elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in (".dxf", ".dwg") and p not in have:
                b["files"].append(self._file_entry(p))
                have.add(p)
                n += 1
        self._save()
        if n:
            self.log("添加 %d 个文件到「%s」" % (n, b["name"]))
        return self.get_state()

    def _file_entry(self, p):
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        return {"path": p, "name": os.path.basename(p), "size": size, "ext": os.path.splitext(p)[1].lower()[1:],
                "selected": True, "status": "ready", "note": "", "terms": None, "deleted": None, "output": ""}

    def remove_files(self, paths, bid=None):
        b = self._batch(bid)
        ps = set(paths or [])
        b["files"] = [f for f in b["files"] if f["path"] not in ps]
        self._save()
        return self.get_state()

    def set_selected(self, path, selected, bid=None):
        for f in self._batch(bid)["files"]:
            if f["path"] == path or path == "*":
                f["selected"] = bool(selected)
        self._save()
        return self.get_state()

    def pick_files(self):
        w = self._window
        if w is None:
            return None
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        r = w.create_file_dialog(kind, allow_multiple=True, file_types=("CAD 图纸 (*.dxf;*.dwg;*.DXF;*.DWG)", "所有文件 (*.*)"))
        return list(r or [])

    def pick_folder(self):
        w = self._window
        if w is None:
            return None
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        r = w.create_file_dialog(kind)
        return (list(r) if r else [None])[0]

    def pick_oda(self):
        w = self._window
        if w is None:
            return None
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        r = w.create_file_dialog(kind, allow_multiple=False)
        return (list(r) if r else [None])[0]

    def reveal(self, path):
        return reveal(path)

    def open_oda_download(self):
        return open_file(ODA_URL)

    def open_path(self, path):
        return open_file(path)

    # ------------------------------------------------------------ 处理
    def _cfg(self):
        s = self.settings
        return C.merge_config({
            "options": s["options"], "keywords": s.get("keywords") or [], "whitelist": s.get("whitelist") or [],
            "pseudonyms": s.get("pseudonyms") or {}, "signature_block_pattern": s.get("signature_block_pattern"),
            "oda_converter": s.get("oda_converter") or "", "dwg_version": s.get("dwg_version") or "same",
            "dwg_converter": s.get("dwg_converter") or "auto",
            "output_format": s.get("output_format") or "same", "output_suffix": s.get("output_suffix") or "_脱敏",
        })

    def _inputs(self, b, only_selected=True):
        files, used = [], set()
        for f in b["files"]:
            if only_selected and not f.get("selected", True):
                continue
            if not os.path.isfile(f["path"]):
                f["status"], f["note"] = "error", "文件不存在或已移动"
                continue
            rel = f["name"]
            if rel in used:
                rel = os.path.basename(os.path.dirname(f["path"])) + "/" + rel
            k = 2
            while rel in used:
                rel = "%d/%s" % (k, f["name"])
                k += 1
            used.add(rel)
            files.append((f["path"], rel))
        return files

    def _previous(self, b):
        """本批已有代号 + 沿用的批次代号（本批优先）。"""
        m = {}
        seen = set()
        chain = []
        cur = b
        while cur and cur["id"] not in seen:
            seen.add(cur["id"])
            chain.append(cur)
            cur = next((x for x in self.batches if x["id"] == cur.get("inherit")), None)
        for x in reversed(chain):
            for e in x.get("mapping") or []:
                m[e["term"]] = e
        return {"mapping": list(m.values())} if m else None

    def _start(self, kind, fn):
        with self._lock:
            if self._job and self._job["status"] == "running":
                raise RuntimeError("正在处理上一个任务，请稍候")
            self._job = {"id": uuid.uuid4().hex[:8], "kind": kind, "status": "running", "result": None, "error": None,
                         "started": time.time()}
            job = self._job

        def run():
            try:
                job["result"] = fn()
                job["status"] = "done"
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                self.log("✗ 出错：%s" % e)
                traceback.print_exc()
            job["seconds"] = round(time.time() - job["started"], 1)
        threading.Thread(target=run, daemon=True).start()
        return {"job": job["id"]}

    def scan(self, bid=None):
        b = self._batch(bid)
        files = self._inputs(b)
        if not files:
            raise RuntimeError("当前批次没有选中的图纸")
        for f in b["files"]:
            if f.get("selected", True) and f["status"] != "error":
                f["status"], f["note"] = "scanning", ""

        def work():
            self.log("开始扫描「%s」：%d 个文件" % (b["name"], len(files)))
            res = C.run_pipeline([], None, self._cfg(), dry_run=True, previous_mapping=self._previous(b),
                                 log=self.log, files=files)
            terms = []
            for e in res["mapping"].values():
                terms.append({"term": e["term"], "replace": e["replace"], "cat": e["cat"],
                              "catName": C.CAT_NAMES.get(e["cat"], e["cat"]), "rule": e["rule"], "count": e["count"],
                              "files": e["files"], "locs": e["locs"][:3], "enabled": e["enabled"],
                              "warn": ("出现 %d 次，偏多，请确认是人名" % e["count"]) if e["cat"] == "person" and e["count"] > 40 else ""})
            by_rel = {j["rel"]: j for j in res["jobs"]}
            rels = dict((src, rel) for src, rel in files)
            for f in b["files"]:
                rel = rels.get(f["path"])
                if not rel:
                    continue
                j = by_rel.get(rel) or {}
                a = j.get("analysis", {})
                dels = {}
                for _, why in a.get("delete_recs", []):
                    dels[why] = dels.get(why, 0) + 1
                f["rel"] = rel
                f["acadver"] = a.get("acadver", "")
                f["encoding"] = a.get("encoding", "")
                f["entities"] = sum(a.get("counts", {}).values())
                f["deleted"] = dels
                f["terms"] = sum(1 for t in terms if rel in t["files"])
                f["notes"] = self._notes(j)
                if j.get("error"):
                    f["status"], f["note"] = "error", j["error"]
                else:
                    f["status"], f["note"] = "scanned", ""
            self._scans[b["id"]] = {"terms": terms, "time": time.strftime("%H:%M:%S")}
            self._save()
            self.log("扫描完成：识别到 %d 项敏感词" % len(terms))
            agg = {}
            for f in b["files"]:
                for k, v in (f.get("deleted") or {}).items():
                    agg[k] = agg.get(k, 0) + v
            return {"terms": terms, "files": len(files), "deleted": agg,
                    "names": [os.path.basename(src) for src, _ in files][:3],
                    "errors": [f["name"] + "：" + f["note"] for f in b["files"] if f["status"] == "error"]}
        return self._start("scan", work)

    def _notes(self, j):
        a = j.get("analysis", {})
        out = []
        if j.get("converter"):
            out.append("DWG %s 已用 %s 读取" % (C.DWG_LABEL.get(j.get("dwg_version"), ""),
                                           "ODA File Converter" if j["converter"] == "oda" else "内置 LibreDWG"))
        if j.get("out_version"):
            out.append("输出 DWG %s（%s）" % (C.DWG_LABEL.get(j["out_version"], ""),
                                          "ODA File Converter" if j.get("out_converter") == "oda" else "内置 LibreDWG"))
        dv = (j.get("verify") or {}).get("dwg")
        if dv:
            out.append(("DWG 回读：" if dv["ok"] else "DWG 回读未通过：") + dv["readback"])
        out.extend(j.get("notes", []))
        if a.get("unknown"):
            out.append("含非标准对象 %s（多为天正对象，内部文字可能处理不到）" % "、".join(
                "%s×%d" % kv for kv in sorted(a["unknown"].items(), key=lambda x: -x[1])[:4]))
        if a.get("sig_blocks"):
            out.append("签名/印章类图块：%s" % "、".join(C.dxf_unescape(x) for x in a["sig_blocks"][:6]))
        if a.get("ole"):
            out.append("含 OLE 嵌入对象 %d 个" % a["ole"])
        if a.get("geodata"):
            out.append("含地理位置信息，可在 CAD 中执行 GEOREMOVE 删除")
        return out

    def get_scan(self, bid=None):
        return self._scans.get((bid or self.current), {"terms": []})

    def apply(self, decisions=None, bid=None):
        b = self._batch(bid)
        files = self._inputs(b)
        if not files:
            raise RuntimeError("当前批次没有选中的图纸")
        for f in b["files"]:
            if f.get("selected", True) and f["status"] != "error":
                f["status"], f["note"] = "running", ""

        def work():
            return self._process(b, files, decisions or {}, label="执行脱敏")
        return self._start("apply", work)

    def _process(self, b, files, decisions, label="执行脱敏", out_dir_override=None):
        s = self.settings
        cfg = self._cfg()
        self.log("%s「%s」：%d 个文件" % (label, b["name"], len(files)))
        tmp = tempfile.mkdtemp(prefix="drawveil_out_")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        rep = os.path.join(s.get("report_dir") or os.path.join(documents_dir(), "图隐报告（内部留存）"),
                           re.sub(r'[\\/:*?"<>|]', "_", b["name"]), stamp)
        try:
            res = C.run_pipeline([], tmp, cfg, report_dir=rep, decisions=decisions,
                                 previous_mapping=self._previous(b), log=self.log, files=files)
            src_of = dict((rel, src) for src, rel in files)
            outs = []
            for j in res["jobs"]:
                src = src_of.get(j["rel"])
                f = next((x for x in b["files"] if x["path"] == src), None)
                if j.get("output") and os.path.isfile(j["output"]):
                    if out_dir_override:
                        dest_dir = out_dir_override
                    elif s.get("output_mode") == "fixed" and s.get("output_dir"):
                        dest_dir = s["output_dir"]
                    else:
                        dest_dir = os.path.join(os.path.dirname(src), "脱敏输出")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest = os.path.join(dest_dir, os.path.basename(j["output"]))
                    shutil.move(j["output"], dest)
                    outs.append(dest)
                    for extra in j.get("extra_outputs") or []:
                        if os.path.isfile(extra):
                            shutil.move(extra, os.path.join(dest_dir, os.path.basename(extra)))
                else:
                    dest = ""
                v = j.get("verify") or {}
                info = {"rel": j["rel"], "src": src, "output": dest, "error": j.get("error"),
                        "changes": len(j.get("changes", [])), "removed": j.get("removed", []),
                        "geometry": v.get("geometry", ""), "geometry_ok": v.get("geometry_ok", False),
                        "residual": [x["term"] for x in v.get("residual", [])][:10],
                        "binary_residual": [x["term"] for x in v.get("binary_residual", [])][:10],
                        "notes": j.get("notes", []), "dwg": (v.get("dwg") or {}).get("readback", ""),
                        "out_version": C.DWG_LABEL.get(j.get("out_version"), ""), "out_converter": j.get("out_converter")}
                if f is not None:
                    f["output"] = dest
                    f["changes"] = info["changes"]
                    if j.get("error"):
                        f["status"], f["note"] = "error", j["error"]
                    elif not info["geometry_ok"] or info["residual"]:
                        f["status"], f["note"] = "warn", "校验未通过，请看报告"
                    elif info["binary_residual"]:
                        f["status"], f["note"] = "warn", "天正/代理对象里仍有：" + "、".join(info["binary_residual"][:3])
                    elif info["out_converter"] == "libredwg":
                        f["status"], f["note"] = "warn", "DWG 2000（内置转换器写出），建议在 CAD 里打开核对"
                    else:
                        f["status"], f["note"] = "done", "校验通过" + ("，DWG " + info["out_version"] if info["out_version"] else "")
                j["_info"] = info
            # 代号库：合并保存到批次
            old = dict((e["term"], e) for e in (b.get("mapping") or []))
            for e in C.mapping_export(res["mapping"])["mapping"]:
                old[e["term"]] = e
            b["mapping"] = list(old.values())
            self._save()
            infos = [j["_info"] for j in res["jobs"] if "_info" in j]
            ok = sum(1 for i in infos if not i["error"] and i["geometry_ok"] and not i["residual"])
            self.log("完成：%d / %d 个文件校验通过，报告在 %s" % (ok, len(infos), rep))
            if s.get("reveal_after") and outs and label == "执行脱敏":
                reveal(outs[0])
            return {"files": infos, "report_dir": rep, "report_html": os.path.join(rep, "脱敏报告.html"),
                    "ok": ok, "total": len(infos)}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def poll(self, since=0):
        with self._lock:
            logs = [l for l in self._logs if l["seq"] > (since or 0)]
            job = None
            if self._job:
                job = {k: self._job.get(k) for k in ("id", "kind", "status", "error", "seconds")}
                if self._job["status"] != "running":
                    job["result"] = self._job.get("result")
            cur = self._batch()
            return {"logs": logs, "seq": self._seq, "job": job,
                    "files": cur["files"], "current": self.current,
                    "watch": {"enabled": bool(self.settings.get("watch_enabled")), "dir": self.settings.get("watch_dir") or ""}}

    def export_mapping(self, bid=None):
        b = self._batch(bid)
        d = self.settings.get("report_dir") or documents_dir()
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "%s_代号库.json" % re.sub(r'[\\/:*?"<>|]', "_", b["name"]))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"tool": "DrawVeil", "version": APP_VERSION, "mapping": b.get("mapping") or []}, f, ensure_ascii=False, indent=1)
        reveal(p)
        return p

    # ------------------------------------------------------------ 监视文件夹
    def _watch_batch(self):
        b = next((x for x in self.batches if x.get("watch")), None)
        if b is None:
            b = {"id": uuid.uuid4().hex[:12], "name": "监视文件夹", "files": [], "mapping": [], "inherit": None,
                 "created": time.strftime("%Y-%m-%d %H:%M"), "watch": True}
            self.batches.append(b)
            self._save()
        return b

    def _watch_loop(self):
        while not self._stop.wait(4.0):
            try:
                s = self.settings
                d = s.get("watch_dir")
                if not s.get("watch_enabled") or not d or not os.path.isdir(d):
                    continue
                if self._job and self._job["status"] == "running":
                    continue
                suffix = s.get("output_suffix") or "_脱敏"
                ready = []
                for name in sorted(os.listdir(d)):
                    p = os.path.join(d, name)
                    st, ext = os.path.splitext(name)
                    if ext.lower() not in (".dxf", ".dwg") or st.endswith(suffix) or name.startswith((".", "~")):
                        continue
                    try:
                        sig = (os.path.getsize(p), os.path.getmtime(p))
                    except OSError:
                        continue
                    if self._watch_seen.get(p) == sig:
                        continue
                    if self._watch_pending.get(p) == sig:      # 两次检查大小不变才处理（避免文件还在复制中）
                        ready.append(p)
                    self._watch_pending[p] = sig
                if not ready:
                    continue
                b = self._watch_batch()
                for p in ready:
                    if not any(f["path"] == p for f in b["files"]):
                        b["files"].append(self._file_entry(p))
                files = [(p, os.path.basename(p)) for p in ready]
                out = s.get("watch_out_dir") or os.path.join(d, "已脱敏")
                self.log("监视文件夹：发现 %d 个新文件" % len(files))
                with self._lock:
                    self._job = {"id": uuid.uuid4().hex[:8], "kind": "watch", "status": "running", "result": None,
                                 "error": None, "started": time.time()}
                    job = self._job
                try:
                    job["result"] = self._process(b, files, {}, label="自动脱敏", out_dir_override=out)
                    job["status"] = "done"
                except Exception as e:
                    job["status"], job["error"] = "error", str(e)
                    self.log("✗ 自动脱敏出错：%s" % e)
                for p in ready:
                    try:
                        self._watch_seen[p] = (os.path.getsize(p), os.path.getmtime(p))
                    except OSError:
                        pass
            except Exception as e:
                self.log("✗ 监视文件夹出错：%s" % e)

    def handle_drop(self, paths):
        return self.start_session(paths)

    def start_session(self, paths):
        """简洁版界面：每次选择 / 拖入图纸就是新的一批，并立即开始扫描。"""
        paths = [p for p in (paths or []) if p]
        if not paths:
            return self.get_state()
        cur = self._batch()
        if cur.get("watch") or cur["files"]:
            self.new_batch(time.strftime("%m-%d %H:%M"))
        self.add_paths(paths)
        if not self._batch()["files"]:
            raise RuntimeError("没有找到 DWG / DXF 图纸")
        self.scan()
        return self.get_state()


# ---------------------------------------------------------------- 启动
def run_native(api):
    import webview
    w = webview.create_window(APP_NAME, url=resource("ui", "index.html"), js_api=api, width=1120, height=760,
                              min_size=(860, 620), text_select=True)
    api._window = w

    def on_drop(e):
        try:
            files = e.get("dataTransfer", {}).get("files", [])
            paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
            if paths:
                api.start_session(paths)
        except Exception:
            pass

    def bind():
        try:
            from webview.dom import DOMEventHandler
            w.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            pass
    w.events.loaded += bind
    webview.start(http_server=True, debug=("--debug" in sys.argv))


def run_browser(api, port=0, open_browser=True):
    """没有 pywebview 时：本机 HTTP 服务 + 浏览器打开同一界面（文件选择改为输入路径）。"""
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    ui = resource("ui")
    types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
             ".png": "image/png", ".css": "text/css; charset=utf-8"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            p = "/index.html" if p == "/" else p
            full = os.path.normpath(os.path.join(ui, p.lstrip("/")))
            if not full.startswith(os.path.normpath(ui)) or not os.path.isfile(full):
                return self._send(404, "not found", "text/plain")
            with open(full, "rb") as f:
                self._send(200, f.read(), types.get(os.path.splitext(full)[1], "application/octet-stream"))

        def do_POST(self):
            m = re.match(r"^/api/([a-z_]+)$", self.path)
            if not m or m.group(1).startswith("_") or not hasattr(api, m.group(1)):
                return self._send(404, json.dumps({"error": "unknown"}), "application/json")
            try:
                n = int(self.headers.get("Content-Length", "0"))
                args = json.loads(self.rfile.read(n).decode("utf-8") or "[]")
                r = getattr(api, m.group(1))(*args)
                self._send(200, json.dumps({"ok": True, "result": r}, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception as e:
                self._send(200, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://127.0.0.1:%d/?mode=browser" % srv.server_address[1]
    print("%s 已启动：%s" % (APP_NAME, url), flush=True)
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    api = Api()
    if "--browser" in sys.argv:
        port = 0
        for a in sys.argv:
            if a.startswith("--port="):
                port = int(a.split("=", 1)[1])
        return run_browser(api, port, "--no-open" not in sys.argv)
    try:
        import webview  # noqa
    except ImportError:
        print("未安装 pywebview，改用浏览器界面（pip install pywebview 后可使用原生窗口）")
        return run_browser(api)
    run_native(api)


if __name__ == "__main__":
    main()
