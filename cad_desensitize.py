#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAD 图纸信息脱敏工具 (DXF / DWG)
=================================

设计原则：只改“字符串”，不动“几何”。
  * 坐标、尺寸、标高、图层、块结构、线型、标注测量值一概不改；
  * 只替换识别出的敏感文字（人名、单位、项目名、电话、证件号……），
    同一个敏感词在所有图纸里替换成同一个代号，保证前后一致；
  * 清理文件元数据（作者、最后保存人、外部参照/图片的本机路径、超链接、
    缩略图、编辑时长、GUID……）；
  * 处理完自动做“几何指纹”比对，证明几何数据零改动，并扫描残留。

只依赖 Python 3.8+ 标准库。DWG 先转 DXF 处理，再转回 DWG：
  优先用 ODA File Converter（免费，需自行安装，质量最好）；
  没装 ODA 时用内置/系统里的 LibreDWG 兜底（只能写 R2000 格式的 DWG，属实验功能）。
  写出的 DWG 会再读回来核对图元数量、几何和残留。

用法：
  python3 cad_desensitize.py gui                       # 打开图形界面（浏览器）
  python3 cad_desensitize.py run  图纸或文件夹... -o 输出目录
  python3 cad_desensitize.py scan 图纸或文件夹...      # 只扫描、出报告，不改文件
  python3 cad_desensitize.py init-config 配置.json     # 导出默认配置
"""

import argparse
import base64
import copy
import csv
import glob
import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from collections import OrderedDict, defaultdict

VERSION = "1.0.1"

# =====================================================================
# 默认配置
# =====================================================================

OPTION_INFO = [
    # key, 默认值, 分组, 中文说明
    ("titleblock_person", True, "图签识别", "图签/会签栏中的人员姓名（设计、校对、审核、审定、项目负责人……）"),
    ("titleblock_org", True, "图签识别", "单位名称（建设单位、设计单位、施工单位……）"),
    ("titleblock_project", True, "图签识别", "工程名称 / 项目名称 / 子项名称"),
    ("titleblock_address", True, "图签识别", "工程地址 / 建设地点"),
    ("titleblock_projno", True, "图签识别", "工程编号 / 项目编号 / 合同号（图号不动）"),
    ("titleblock_cert", True, "图签识别", "资质证书号、注册号、执业印章号"),
    ("titleblock_date", False, "图签识别", "图签日期（默认保留，版次追溯常要用）"),
    ("detect_company", True, "全文识别", "全图中的公司/设计院/政府机构名称（按“有限公司、设计院、管委会”等后缀识别）"),
    ("detect_phone", True, "全文识别", "手机号、座机、传真、400 电话"),
    ("detect_email", True, "全文识别", "电子邮箱"),
    ("detect_idcard", True, "全文识别", "身份证号（带校验位验证）"),
    ("detect_uscc", True, "全文识别", "统一社会信用代码（带校验位验证）"),
    ("detect_account", True, "全文识别", "银行账号、QQ / 微信号（需有“账号/QQ/微信”等提示词）"),
    ("detect_url", True, "全文识别", "网址"),
    ("coord_text", False, "全文识别", "测量坐标文字 X=3456789.123（默认保留，属于设计信息）"),
    ("clean_metadata", True, "文件清理", "文件属性：作者、最后保存人、标题、关键字、自定义属性、编辑时长、GUID"),
    ("normalize_dates", True, "文件清理", "创建/修改时间统一改为 2000-01-01"),
    ("strip_paths", True, "文件清理", "外部参照、光栅图片、PDF 底图、打印机/打印样式的本机路径只留文件名"),
    ("remove_hyperlinks", True, "文件清理", "清除对象上的超链接"),
    ("remove_thumbnail", True, "文件清理", "删除文件缩略图和块预览图（缩略图上能看到图签内容）"),
    ("clear_signature_blocks", True, "文件清理", "清空签名、印章、出图章、Logo 类图块的内容"),
    ("clear_signature_strokes", True, "文件清理", "删除“签名”栏里用线条手写的签名笔迹（表格线保留）"),
    ("clear_logo", True, "文件清理", "删除单位名称左侧的 Logo 图形"),
    ("rename_symbols", True, "文件清理", "图层名、块名、布局名中出现的敏感词一并替换（引用关系自动同步）"),
    ("remove_ole", False, "文件清理", "删除 OLE 嵌入对象（可能是盖章扫描件，也可能是 Excel 门窗表，默认保留）"),
]

DEFAULT_CONFIG = {
    "keywords": [],
    "whitelist": [
        "中国建筑标准设计研究院", "中国建筑工业出版社", "中国计划出版社",
        "住房和城乡建设部", "中华人民共和国住房和城乡建设部", "国家市场监督管理总局",
        "国家建筑标准设计", "中国建筑科学研究院有限公司建筑结构研究所",
    ],
    "options": {k: v for k, v, _, _ in OPTION_INFO},
    "signature_block_pattern": r"签名|签字|手签|印章|出图章|注册章|执业章|审图章|公章|图章|(?<![A-Za-z])(?:SIGN|SIGNATURE|STAMP|SEAL|LOGO)(?![A-Za-z])",
    "pseudonyms": {
        "keyword": "关键词{n:02d}",
        "person": "人员{n:02d}",
        "org": "单位{n:02d}",
        "project": "项目{n:02d}",
        "address": "地址{n:02d}",
        "projno": "编号{n:02d}",
        "cert": "证书号{n:02d}",
        "date": "日期{n:02d}",
        "phone": "电话{n:02d}",
        "email": "邮箱{n:02d}",
        "idcard": "证件号{n:02d}",
        "uscc": "信用代码{n:02d}",
        "account": "账号{n:02d}",
        "url": "网址{n:02d}",
        "coord": "*",
    },
    "output_format": "same",        # same / dxf / dwg
    "dwg_version": "same",          # 输出 DWG 版本：same（与原 DWG 相同）/ ACAD2018 / ACAD2013 / ACAD2010 / ACAD2007 / ACAD2004 / ACAD2000
    "oda_converter": "",            # ODA File Converter 路径，留空自动查找
    "dwg_converter": "auto",        # auto（ODA 优先，LibreDWG 兜底）/ oda / libredwg
    "libredwg_dir": "",             # LibreDWG 程序所在目录（含 dwg2dxf、dxf2dwg），留空自动查找
}

CAT_NAMES = OrderedDict([
    ("keyword", "自定义关键词"), ("person", "人员姓名"), ("org", "单位名称"), ("project", "项目名称"),
    ("address", "地址"), ("projno", "工程编号"), ("cert", "证书/注册号"), ("date", "日期"),
    ("phone", "电话"), ("email", "邮箱"), ("idcard", "身份证号"), ("uscc", "统一社会信用代码"),
    ("account", "账号"), ("url", "网址"), ("coord", "测量坐标"),
])
CAT_PRIORITY = {k: i for i, k in enumerate(CAT_NAMES)}


def merge_config(user_cfg):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not user_cfg:
        return cfg
    for k, v in user_cfg.items():
        if k in ("options", "pseudonyms") and isinstance(v, dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def load_config(path):
    if not path:
        return merge_config(None)
    with open(path, "r", encoding="utf-8") as f:
        return merge_config(json.load(f))


# =====================================================================
# 词表
# =====================================================================

def _ws(s):
    return set(s.split())

PERSON_LABELS = _ws("""设计 设计人 设计者 校对 校对人 校核 校核人 审核 审核人 审定 审定人 审批 审批人 批准 批准人 核定 核定人
制图 制图人 绘图 绘图人 描图 项目负责人 项目负责 专业负责人 专业负责 工种负责人 工程负责人 设计总负责人 设计负责人
总负责人 项目经理 项目总工 总工 总工程师 主任工程师 院长 所长 室主任 负责人 注册建筑师 注册结构工程师 注册工程师
注册师 审图 审图人 编制 编制人 复核 复核人 签发 主持人 设计主持人 项目主持人 建筑师 结构工程师 专业工程师""")
PERSON_LABELS_EN = _ws("""DESIGNED DESIGNEDBY DESIGNER DRAWN DRAWNBY DRAFTED DRAFTEDBY DRAFTER CHECKED CHECKEDBY CHECKER
REVIEWED REVIEWEDBY REVIEWER APPROVED APPROVEDBY APPROVER AUTHORIZED AUTHORIZEDBY PROJECTMANAGER PROJECTENGINEER
PROJECTLEADER DISCIPLINELEADER PROJECTDIRECTOR""")
NAMECOL_LABELS = _ws("姓名 实名 名字 打印姓名 印刷体 NAME PRINTNAME")
SIGNCOL_LABELS = _ws("签名 签字 签署 手签 签章 本人签字 亲笔签名 SIGNATURE SIGN")
ORG_LABELS = _ws("""建设单位 业主 业主单位 甲方 发包人 委托单位 委托方 设计单位 设计方 施工单位 监理单位 勘察单位 审图机构
审图单位 合作设计 合作单位 合作设计单位 客户 开发单位 开发商 代建单位 使用单位 出图单位 编制单位 设计院 设计公司""")
ORG_LABELS_EN = _ws("CLIENT OWNER EMPLOYER CONSULTANT CONTRACTOR DEVELOPER")
PROJECT_LABELS = _ws("工程名称 项目名称 子项名称 子项 单项名称 单体名称 工程项目 项目全称 项目名 工程名")
PROJECT_LABELS_EN = _ws("PROJECT PROJECTNAME SUBPROJECT")
ADDRESS_LABELS = _ws("工程地址 项目地址 建设地点 建设地址 工程地点 地址 项目地点 项目位置 工程位置")
ADDRESS_LABELS_EN = _ws("ADDRESS LOCATION")
PROJNO_LABELS = _ws("工程编号 项目编号 工程号 项目号 合同号 合同编号 设计编号 设计号 委托编号 工程代号 项目代号")
PROJNO_LABELS_EN = _ws("PROJECTNO PROJECTNUMBER JOBNO JOBNUMBER CONTRACTNO")
CERT_LABELS = _ws("证书编号 资质证书编号 资质证书 证书号 资质编号 资质证号 注册号 注册证号 注册编号 执业印章号 印章号 执业证号 注册章号")
CERT_LABELS_EN = _ws("CERTIFICATENO LICENSENO")
DATE_LABELS = _ws("日期 出图日期 设计日期 完成日期")
DATE_LABELS_EN = _ws("DATE")

LABEL_TABLE = [
    ("person", PERSON_LABELS, PERSON_LABELS_EN, "titleblock_person"),
    ("org", ORG_LABELS, ORG_LABELS_EN, "titleblock_org"),
    ("project", PROJECT_LABELS, PROJECT_LABELS_EN, "titleblock_project"),
    ("address", ADDRESS_LABELS, ADDRESS_LABELS_EN, "titleblock_address"),
    ("projno", PROJNO_LABELS, PROJNO_LABELS_EN, "titleblock_projno"),
    ("cert", CERT_LABELS, CERT_LABELS_EN, "titleblock_cert"),
    ("date", DATE_LABELS, DATE_LABELS_EN, "titleblock_date"),
]
CAT_OPTION = {c: o for c, _, _, o in LABEL_TABLE}

# 图签里的“字段名”，它们本身不是值
FIELD_WORDS = _ws("""图号 图名 比例 日期 版本 版次 阶段 设计阶段 专业 张数 图别 修改 备注 签名 签字 姓名 会签 出图章 注册章
说明 页次 第 共 张 页 图纸 名称 编号 序号 内容 做法 部位 材料 规格 数量 单位 型号 图纸目录 版号 修改记录 修改内容
图纸名称 图纸编号 版本号 执业专用章 出图专用章 执业章 审图章 盖章 图签 签章 签字栏 会签栏 角色 职责 职务 工种 项目 工程""")

COMMON_WORDS = _ws("""施工图 初设 初步设计 方案 方案设计 施工图设计 扩初 扩初设计 竣工图 招标图 报建 送审 审查 建筑 结构 给排水
给水排水 暖通 电气 智能化 总图 景观 室内 幕墙 消防 节能 人防 装修 装饰 燃气 动力 照明 弱电 强电 通风 空调 防排烟
已签 同上 详见 见图 待定 无 合格 通过 有效 作废 出图 晒图 存档 设计院 本院 我院 本公司 业主 甲方 乙方 监理 施工
总包 分包 签字有效 电子签名 电子签章 平面图 立面图 剖面图 详图 大样 大样图 节点 说明 目录 封面 首页 附注 附图""")
EN_NONNAMES = _ws("NA N/A NONE NULL DATE SCALE NAME SIGN SIGNATURE TITLE REV REVISION NO NUMBER SHEET DRAWING CHECK APPROVE DESIGN")
# 中英双语图签里的英文标签词：整行都由这些词组成时，它是标签，不是要脱敏的值
EN_LABEL_WORDS = _ws("""BY OF IN FOR AND THE TO ON AT DESIGNED DESIGN DESIGNER DRAWN DRAFTED DRAFTER DRAWER DRAFTSMAN CHECKED CHECKER
CHECK VERIFIED VERIFY VERIFIER REVIEWED REVIEW REVIEWER APPROVED APPROVE APPROVAL APPROVER AUTHORIZED AUTHORISED
AUDITED AUDIT AUDITOR EXAMINED SUPERVISOR SUPERVISED SUPERVISION PROJECT PROJECTS SUB SUB-PROJECT SUBPROJECT NAME
NAMES TITLE SITE LOCATION ADDRESS CLIENT OWNER EMPLOYER DEVELOPER CONTRACTOR CONSULTANT ARCHITECT ARCHITECTURE
ARCHITECTURAL ENGINEER ENGINEERING STRUCTURAL STRUCTURE CIVIL CHIEF LEADER LEAD MANAGER DIRECTOR DISCIPLINE PROFESSIONAL
RESPONSIBLE PERSON PERSONS CHARGE COORDINATION COORDINATED COUNTERSIGN COUNTERSIGNED SIGN SIGNED SIGNATURE SEAL
STAMP DATE SCALE NO NO. NUMBER SHEET SHEETS DRAWING DRAWINGS DWG STAGE PHASE REV REVISION VERSION STATUS JOB CONTRACT
FILE ISSUE ISSUED CONSTRUCTION REMARK REMARKS NOTE NOTES DESCRIPTION CERTIFICATE REGISTERED REGISTRATION
QUALIFICATION LICENSE LICENCE CODE GRADE UNIT ITEM ITEMS TOTAL PAGE PART PLAN ELEVATION SECTION DETAIL KEY CAD
MEP ELEC ELECTRICAL PLUMBING HVAC MECHANICAL BUILDING BLDG FLOOR AREA""")
# 常见姓氏（含复姓）。只用于“推断出来的人名”：首字不是常见姓氏、又含明显不是人名的字时，不当作人名
SURNAMES = set("""王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖萧田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦
付傅方白邹孟熊秦邱江尹薛闫阎段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰
焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦
褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻苑迟邝官封谈匡鞠惠荆乐冀郁胥
南班储原栗燕楚鄢劳谌奚皮粟冼蔺楼盘满闻位厉伊仝区郜海阚花权强帅屠豆朴盖练廉禹井祖漆巴丰支卿国狄平计索宣晋相初门云容敬来扈晁芮都普阙浦戈
伏鹿薄邸雍辜羊阿乌母裘亓修邰赫杭况那宿鲜印逯隆茹诸战慕危玉银亢嵇公哈湛宾戎勾茅利於呼居揭干但尉冶斯元束檀衣信展阴昝智幸奉植衡富尧闭由""")
COMPOUND_SURNAMES = _ws("欧阳 司马 上官 诸葛 东方 皇甫 尉迟 公孙 慕容 长孙 宇文 司徒 令狐 夏侯 澹台 端木 西门 南宫 独孤 轩辕 百里 呼延 万俟 钟离 闻人 赫连")
NON_NAME_CHARS = set("版图纸封面页号层栏表说明目录第张期次级型式类区栋楼室宿舍厂房段程项工计设施审核校对签章字部系统号稿底样示意总平立剖详")

# 属性标签 → 类别
TAG_RULES = [
    ("projno", re.compile(r"(编号|工程号|项目号|合同号|PROJ.*(NO|NUM)|JOB.*(NO|NUM)|CONTRACT)", re.I)),
    ("date", re.compile(r"(日期|DATE)", re.I)),
    ("cert", re.compile(r"(证书|注册号|印章号|CERT|LICEN)", re.I)),
    ("address", re.compile(r"(地址|地点|ADDR|LOCATION)", re.I)),
    ("org", re.compile(r"(单位|业主|甲方|建设方|CLIENT|OWNER|COMPANY|公司|设计院)", re.I)),
    ("project", re.compile(r"(工程名|项目名|子项|单体|PROJECT|PROJNAME|PRJ_?NAME|工程|项目)", re.I)),
    ("person", re.compile(r"(设计人|设计者|校对|校核|审核|审定|审批|批准|核定|制图|绘图|负责|经理|总工|主持|姓名|签名|签字|"
                          r"DESIGNER|DESIGNED|DRAWN|DRAFT|CHECK|APPROV|REVIEW|ENGINEER|AUTHOR|SIGN|NAME|"
                          r"^(SJ|SJR|JH|JD|XD|SH|SD|PZ|ZT|HT|HD|XMFZR|ZYFZR|FZR|GCFZR|SDR|SHR|JHR|XDR)\d*$)", re.I)),
]
TAG_EXCLUDE = re.compile(r"(阶段|STAGE|PHASE|比例|SCALE|图名|TITLE|专业|DISC|版|REV|图号|SHEET|DWG)", re.I)

COMPANY_SUFFIX = (r"(?:股份有限公司|有限责任公司|集团有限公司|有限公司|集团公司|集团|分公司|公司|设计研究总院|设计研究院|设计总院|"
                  r"设计院|研究总院|研究院|规划设计院|规划院|勘察院|勘测院|事务所|工作室|管理委员会|管委会|指挥部|"
                  r"住房和城乡建设局|建设局|住建局|规划局|自然资源和规划局|自然资源局|人民政府|街道办事处)")
COMPANY_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9（）()·&]{2,40}?" + COMPANY_SUFFIX)
COMPANY_SUFFIX_RUN = re.compile(COMPANY_SUFFIX)
COMPANY_SPLIT = re.compile(r".*(?:由|为|是|与|和|及|向|经|委托|采用|请|并|或|在|于|从|据|按|以|给|对|被|将|会同|联系|咨询|提供|详见|参见|见|的|：|:|、|，|,|。|；|;|\s)")
_EN_WORD = r"[A-Z][A-Za-z&'\-]*\.?"
_EN_LINK = r"(?:of|and|for|the|&|de|Of|And|For|The|OF|AND|FOR|THE)"
_EN_SEQ = r"(?:" + _EN_WORD + r"\s+(?:" + _EN_LINK + r"\s+)?)"
EN_ORG_RE = re.compile(r"(?<![A-Za-z])" + _EN_SEQ + r"{1,10}?(?:Co\.?\s*,?\s*Ltd\.?|CO\.?\s*,?\s*LTD\.?|Company\s+Limited|COMPANY\s+LIMITED|"
                       r"Corp\.?\s*,?\s*Ltd\.?|CORP\.?\s*,?\s*LTD\.?|Co\.?,?\s*Limited|Limited|LIMITED|Ltd\.?|LTD\.?|Inc\.?|INC\.?|Incorporated|Corporation|CORPORATION|Corp\.?|"
                       r"LLC|L\.L\.C\.|GmbH|Holdings|Group(?:\s+Co\.?\s*,?\s*Ltd\.?)?|GROUP)(?![A-Za-z])")
EN_INST_RE = re.compile(r"(?<![A-Za-z])" + _EN_SEQ + r"{1,8}?(?:Design\s+|DESIGN\s+)?(?:Research\s+|RESEARCH\s+)?"
                        r"(?:Institute|INSTITUTE|Academy|ACADEMY|University|UNIVERSITY|Architects|ARCHITECTS|Design\s+Studio)"
                        r"(?:\s+" + _EN_LINK + r"(?:\s+" + _EN_WORD + r"){1,6})?(?![A-Za-z])")
EN_ORG_GENERIC = re.compile(r"^(?:The\s+)?(?:Contractor|Owner|Client|Employer|Supplier|Manufacturer|Engineer|Consultant|Design|Approved|Local|"
                            r"Relevant|Qualified|Specialist|Main|Sub)(?:\s+\w+)?\s", re.I)
COMPANY_PAREN_RUN = re.compile(r"[（(][\u4e00-\u9fff]{1,6}[）)]" + COMPANY_SUFFIX)
COMPANY_SENTENCE = re.compile(r"(应|须|需|必须|应当|具有|具备|负责|要求|进行|采用|按照|根据|如|若|可|不得|严禁|满足|符合|相应)")
COMPANY_GENERIC = re.compile(
    r"^(?:施工|总承包|总包|专业|分包|设备|供货|供应|生产|厂家|监理|物业|检测|相关|有关|具有.{0,8}资质的?|有资质的?|该|本|各|"
    r"其他|其它|原|设计|勘察|建设|电力|供电|燃气|自来水|市政|消防|当地|所在地|上述|下列|中标|承包|安装|劳务|材料|产品|合格|"
    r"正规|指定|认可|甲方指定|业主指定|专业公司|有关部门|主管|主管部门|规划|测绘|质检|质监|环保|园林|绿化|电信|移动|联通|"
    r"保险|银行|设计单位|施工单位|总包单位|供应商|运营|管理|技术|工程|建筑|结构|机电|暖通|给排水|电气|装饰|幕墙|钢结构|"
    r"一级|二级|三级|甲级|乙级|丙级|相应|具备|具有)+$")

# 识别模式
RE_MOBILE = re.compile(r"(?<![\d.])(?:\+?86[\s-]?)?1[3-9]\d(?:\d{8}|[\s-]\d{4}[\s-]\d{4})(?![\d.])")
RE_LANDLINE = re.compile(r"(?<![\d.])(?:\(0\d{2,3}\)|（0\d{2,3}）|0\d{2,3}-)\s?\d{7,8}(?:-\d{1,5})?(?![\d.])")
RE_400 = re.compile(r"(?<![\d.])[48]00-?\d{3}-?\d{4}(?![\d.])")
RE_PHONE_CTX = re.compile(r"(?:电话|手机|传真|联系电话|联系方式|Tel|TEL|Fax|FAX|Phone|PHONE|Mobile)\s*[.:：]?\s*(\+?\d[\d\-\s()（）]{5,20}\d)")
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_URL = re.compile(r"(?:https?://|www\.)[^\s\u4e00-\u9fff，。；、）)\]]+", re.I)
RE_IDCARD = re.compile(r"(?<![0-9A-Za-z])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])")
RE_USCC = re.compile(r"(?<![0-9A-Z])[0-9A-HJ-NP-RTUW-Y]{2}\d{6}[0-9A-HJ-NP-RTUW-Y]{10}(?![0-9A-Z])")
RE_ACCOUNT = re.compile(r"(?:账号|帐号|账户|帐户|开户账号|银行账号|卡号)\s*[:：]?\s*(\d[\d\s]{9,28}\d)")
RE_IM = re.compile(r"(?:QQ|qq|微信|WeChat|wechat|微信号)\s*号?\s*[:：]?\s*([A-Za-z0-9_\-]{5,20})")
RE_CERT_CTX = re.compile(r"(?:证书编号|证书号|资质证书编号|资质证书号|注册号|注册证号|执业证号|印章编号|执业印章号|注册章号)\s*[:：]?\s*([A-Za-z0-9\-（）()]{6,30})")
RE_COORD = re.compile(r"(?<![A-Za-z])(?:X|Y|A|B|N|E)\s*[=＝:：]\s*(-?\d{5,8}\.\d{1,4})")
RE_DRIVE_PATH = re.compile(r"(?:[A-Za-z]:\\|\\\\)[^\"<>|*?\r\n]*?\\[^\"<>|*?\r\n\\]*\\?[^\"<>|*?\r\n\\]*")
RE_UNIX_PATH = re.compile(r"/(?:Users|home|Volumes)/[^\"<>|*?\r\n]+")

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def has_cjk(s):
    return bool(CJK_RE.search(s))


def idcard_ok(s):
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    try:
        sm = sum(int(s[i]) * w[i] for i in range(17))
    except ValueError:
        return False
    return "10X98765432"[sm % 11] == s[17].upper()


def uscc_ok(s):
    chars = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    w = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
    try:
        sm = sum(chars.index(s[i]) * w[i] for i in range(17))
    except ValueError:
        return False
    c = 31 - sm % 31
    if c == 31:
        c = 0
    return chars[c] == s[17]


# =====================================================================
# DXF 文本转义
# =====================================================================

U_ESC = re.compile(r"\\U\+([0-9A-Fa-f]{4})")
M_ESC = re.compile(r"\\M\+([1-5])([0-9A-Fa-f]{4})")
MIF_ENC = {"1": "cp932", "2": "cp950", "3": "cp949", "4": "johab", "5": "gb2312"}


def dxf_unescape(s):
    if "\\" not in s:
        return s

    def mrep(m):
        try:
            return bytes.fromhex(m.group(2)).decode(MIF_ENC[m.group(1)])
        except Exception:
            return m.group(0)

    s = M_ESC.sub(mrep, s)
    return U_ESC.sub(lambda m: chr(int(m.group(1), 16)), s)


def mtext_plain(s):
    s = s.replace("\\P", "\n").replace("\\~", " ").replace("\\\\", "\x00")
    s = re.sub(r"\\[ACcFfHhQqTtWwp][^;\\{}]*;", "", s)
    s = re.sub(r"\\S([^;]*?)[\^/#]([^;]*?);", r"\1/\2", s)
    s = re.sub(r"\\[LlOoKkNX]", "", s)
    s = s.replace("\\{", "\x01").replace("\\}", "\x02").replace("{", "").replace("}", "")
    return s.replace("\x01", "{").replace("\x02", "}").replace("\x00", "\\")


def text_plain(s):
    return re.sub(r"%%[uUoOkK]", "", s).replace("%%c", "Φ").replace("%%C", "Φ").replace("%%d", "°") \
        .replace("%%D", "°").replace("%%p", "±").replace("%%P", "±")


def basename_any(p):
    p = p.rstrip("\\/")
    return re.split(r"[\\/]", p)[-1] if p else p


# =====================================================================
# DXF 文档（逐行读写，未改动的行原样保留）
# =====================================================================

CODEPAGES = {
    "ANSI_936": "gb18030", "ANSI_950": "cp950", "ANSI_932": "cp932", "ANSI_949": "cp949",
    "ANSI_1250": "cp1250", "ANSI_1251": "cp1251", "ANSI_1252": "cp1252", "ANSI_1253": "cp1253",
    "ANSI_1254": "cp1254", "ANSI_1255": "cp1255", "ANSI_1256": "cp1256", "ANSI_1257": "cp1257",
    "ANSI_874": "cp874", "ANSI_1258": "cp1258", "DOS936": "gb18030", "GB2312": "gb18030",
}


class DxfError(Exception):
    pass


def is_numeric_code(c):
    return (10 <= c <= 59) or (60 <= c <= 99) or (140 <= c <= 149) or (160 <= c <= 179) or \
        (210 <= c <= 239) or (270 <= c <= 289) or (370 <= c <= 389) or (400 <= c <= 409) or \
        (420 <= c <= 429) or (440 <= c <= 459) or (460 <= c <= 469) or (1010 <= c <= 1071)


def is_string_code(c):
    if is_numeric_code(c):
        return False
    if c in (0, 5, 100, 102, 105, 999, 1001, 1002, 1004, 1005):
        return False
    if 310 <= c <= 369 or 390 <= c <= 399 or 480 <= c <= 481:
        return False
    return True


class Record(object):
    __slots__ = ("type", "i0", "i1", "section", "block", "parent", "deleted", "idx")

    def __init__(self, t, i0, i1):
        self.type = t
        self.i0 = i0
        self.i1 = i1
        self.section = None
        self.block = None
        self.parent = None
        self.deleted = False
        self.idx = 0


class DxfDoc(object):
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            raw = f.read()
        if raw.startswith(b"AutoCAD Binary DXF"):
            raise DxfError("这是二进制 DXF，请在 CAD 中另存为 ASCII（文本）DXF 后再处理")
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        if self.bom:
            raw = raw[3:]
        head = raw[:400000].decode("latin-1")
        m = re.search(r"\$ACADVER\s*\r?\n\s*1\s*\r?\n([^\r\n]*)", head)
        self.acadver = m.group(1).strip() if m else "AC1009"
        m = re.search(r"\$DWGCODEPAGE\s*\r?\n\s*3\s*\r?\n([^\r\n]*)", head)
        self.codepage = m.group(1).strip() if m else ""
        if self.acadver >= "AC1021":
            self.encoding = "utf-8"
        else:
            self.encoding = CODEPAGES.get(self.codepage.upper(), "cp1252")
            if self.encoding == "cp1252" and re.search(rb"[\x81-\xfe][\x40-\xfe]", raw[:2000000]):
                # 代码页未知但含双字节字符，按中文处理
                try:
                    raw.decode("gb18030")
                    self.encoding = "gb18030"
                except UnicodeDecodeError:
                    pass
        text = raw.decode(self.encoding, "surrogateescape")
        self.crlf = "\r\n" in text[:5000]
        self.lines = text.split("\n")
        self.changed = {}           # 行号 -> 新内容
        self.deleted_lines = set()
        self.inserts = defaultdict(list)  # 行号 -> 在该行之前插入的行
        self._parse()

    # ---- 解析 ----
    def _parse(self):
        lines = self.lines
        n = len(lines)
        pairs = []
        i = 0
        while i + 1 < n:
            cl = lines[i].strip()
            if cl == "":
                if all(not l.strip() for l in lines[i:]):
                    break
                raise DxfError("第 %d 行组码为空，DXF 文件可能已损坏" % (i + 1))
            try:
                code = int(cl)
            except ValueError:
                raise DxfError("第 %d 行不是有效组码：%r" % (i + 1, cl[:40]))
            v = lines[i + 1]
            if v.endswith("\r"):
                v = v[:-1]
            pairs.append([code, v, i, i + 1])
            i += 2
        self.pairs = pairs
        recs = []
        start = None
        for pi, p in enumerate(pairs):
            if p[0] == 0:
                if start is not None:
                    recs.append(Record(pairs[start][1].strip(), start, pi))
                start = pi
        if start is not None:
            recs.append(Record(pairs[start][1].strip(), start, len(pairs)))
        section = None
        block = None
        parent = None
        for k, r in enumerate(recs):
            r.idx = k
            t = r.type
            if t == "SECTION":
                section = (self.rget(r, 2) or "").strip()
                r.section = section
                continue
            if t == "ENDSEC":
                r.section = section
                section = None
                continue
            r.section = section
            if section == "BLOCKS":
                if t == "BLOCK":
                    block = (self.rget(r, 2) or "").strip()
                    r.block = block
                    continue
                if t == "ENDBLK":
                    r.block = block
                    block = None
                    continue
                r.block = block
            if section in ("ENTITIES", "BLOCKS"):
                if t in ("ATTRIB", "VERTEX", "SEQEND") and parent is not None:
                    r.parent = parent
                    if t == "SEQEND":
                        parent = None
                elif t == "POLYLINE" or (t == "INSERT" and (self.rget(r, 66) or "").strip() == "1"):
                    parent = r
                else:
                    parent = None
        self.recs = recs

    # ---- 访问 ----
    def rget(self, r, code, default=None):
        for pi in range(r.i0 + 1, r.i1):
            c = self.pairs[pi][0]
            if c == 1001:
                break
            if c == code:
                return self.pairs[pi][1]
        return default

    def rgetf(self, r, code, default=0.0):
        v = self.rget(r, code)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    def rpairs(self, r):
        return range(r.i0 + 1, r.i1)

    def is_utf8(self):
        return self.encoding == "utf-8"

    def encode_value(self, s):
        if self.is_utf8():
            return s
        out = []
        for ch in s:
            o = ord(ch)
            if 0xDC80 <= o <= 0xDCFF:
                out.append(ch)
                continue
            try:
                ch.encode(self.encoding)
                out.append(ch)
            except UnicodeEncodeError:
                out.append("\\U+%04X" % o)
        return "".join(out)

    # ---- 修改 ----
    def set_value(self, pi, newval):
        p = self.pairs[pi]
        newval = newval.replace("\r", " ").replace("\n", " ")
        p[1] = newval
        vl = p[3]
        self.changed[vl] = newval + ("\r" if self.lines[vl].endswith("\r") else "")

    def delete_pair(self, pi):
        p = self.pairs[pi]
        self.deleted_lines.add(p[2])
        self.deleted_lines.add(p[3])

    def delete_record(self, r):
        r.deleted = True
        for pi in range(r.i0, r.i1):
            self.delete_pair(pi)

    def insert_pair_before(self, pi, code_line, value):
        cl = self.pairs[pi][2]
        eol = "\r" if self.crlf else ""
        self.inserts[cl].append(code_line.rstrip("\r") + eol)
        self.inserts[cl].append(value + eol)

    def save(self, path):
        out = []
        lines = self.lines
        changed = self.changed
        deleted = self.deleted_lines
        inserts = self.inserts
        for i, l in enumerate(lines):
            if i in inserts:
                out.extend(inserts[i])
            if i in deleted:
                continue
            out.append(changed.get(i, l))
        data = "\n".join(out).encode(self.encoding, "surrogateescape")
        if self.bom:
            data = b"\xef\xbb\xbf" + data
        with open(path, "wb") as f:
            f.write(data)


# =====================================================================
# 识别
# =====================================================================

def norm_label(s):
    s = s.strip()
    s = re.sub(r"[\s\u3000:：()（）\[\]【】_\-./·]", "", s)
    return s


def classify_label(s, opts=None):
    n = norm_label(s)
    if not n or len(n) > 24:
        return None
    if n in SIGNCOL_LABELS or n.upper() in SIGNCOL_LABELS:
        return "signcol"
    if n in NAMECOL_LABELS or n.upper() in NAMECOL_LABELS:
        return "namecol"
    n2 = re.sub(r"(签字|签名|签章|盖章|人员)$", "", n)
    cjk = "".join(CJK_RE.findall(n2))
    lat = re.sub(r"[^A-Za-z]", "", n2).upper()
    # 汉字部分与英文部分以外不能有别的内容（数字等）
    if re.search(r"\d", n2):
        return None
    for cat, cn, en, _ in LABEL_TABLE:
        if cjk:
            if cjk in cn and (not lat or lat in en or lat in PERSON_LABELS_EN | ORG_LABELS_EN | PROJECT_LABELS_EN
                              | ADDRESS_LABELS_EN | PROJNO_LABELS_EN | CERT_LABELS_EN | DATE_LABELS_EN or len(lat) <= 12):
                return cat
        elif lat and lat in en:
            return cat
    return None


def en_label_like(t):
    toks = [x for x in re.split(r"[\s/:：_\-.()（）]+", t.upper()) if x]
    return bool(toks) and all(re.fullmatch(r"[A-Z0-9.]+", x) for x in toks) and \
        all(x in EN_LABEL_WORDS or x.isdigit() for x in toks) and not all(x.isdigit() for x in toks)


def is_non_value(t):
    n = norm_label(t)
    if not n:
        return True
    if n in FIELD_WORDS or classify_label(t):
        return True
    if en_label_like(t.strip()):
        return True
    # 模板占位符：“工程名称1”“建设单位 2”这类“标签 + 编号”
    n2 = re.sub(r"[\d\s]+$", "", t.strip())
    if n2 and n2 != t.strip() and (norm_label(n2) in FIELD_WORDS or classify_label(n2)):
        return True
    return False


def name_like(p):
    p = p.strip()
    if re.fullmatch(r"[\u4e00-\u9fff][\u4e00-\u9fff·]{1,3}", p):
        if p in COMMON_WORDS or p in FIELD_WORDS or classify_label(p):
            return False
        surname = p[0] in SURNAMES or p[:2] in COMPOUND_SURNAMES
        if not surname and any(ch in NON_NAME_CHARS for ch in p):
            return False      # “第一版”“图纸封面”
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z.' \-]{1,29}", p):
        return p.upper().replace(" ", "") not in EN_NONNAMES and not en_label_like(p) and not classify_label(p)
    return False


def value_terms(cat, text):
    out = []
    text = text.replace("\\P", "\n").strip()     # 多行属性里残留的 MTEXT 换行码
    if not text:
        return out
    for line in text.split("\n"):
        line = line.strip()
        if not line or is_non_value(line):
            continue
        if cat == "person":
            parts = [p for p in re.split(r"[\s\u3000]+", line) if p]
            if 2 <= len(parts) <= 4 and all(len(p) == 1 and has_cjk(p) for p in parts) and name_like("".join(parts)):
                out.append(line)          # “孙　昊”这种中间加空格的名字
                continue
            for p in re.split(r"[\s\u3000、，,/;；]+", line):
                if name_like(p):
                    out.append(p)
        elif cat in ("org", "project", "address"):
            cut = None
            for mm in re.finditer(r"[（(，,；;。]", line):
                if mm.group(0) in "（(" and COMPANY_PAREN_RUN.match(line, mm.start()):
                    continue
                cut = mm
                break
            if cut and cut.start() >= 2 and cat != "address":
                line = line[:cut.start()].strip()
            if len(line) >= 2 and not re.fullmatch(r"[\d\s.\-/:：,，]+", line):
                out.append(line)
        elif cat == "projno":
            if re.search(r"\d", line) and 3 <= len(line) <= 40:
                out.append(line)
        elif cat == "cert":
            if re.search(r"\d", line) and len(line) >= 5:
                out.append(line)
        elif cat == "date":
            if re.search(r"\d", line):
                out.append(line)
    return out


def classify_tag(tag):
    if not tag or TAG_EXCLUDE.search(tag) and not re.search(r"(人|NAME|BY)", tag, re.I):
        return None
    for cat, rx in TAG_RULES:
        if rx.search(tag):
            return cat
    return None


def _inline_regexes():
    allcjk = []
    for cat, cn, en, opt in LABEL_TABLE:
        for w in cn:
            allcjk.append((w, cat))
    allcjk.sort(key=lambda x: -len(x[0]))
    lab = "|".join(re.escape(w) for w, _ in allcjk)
    m = {w: c for w, c in allcjk}
    # “设计：张三  校对：李四”
    colon = re.compile(r"(" + lab + r")\s*(?:人)?\s*[:：]\s*([^\s:：]+(?:[ \t][^\s:：]+)*?)(?=\s{2,}|\s*(?:" + lab + r")\s*[:：]|$)")
    # “建设单位 某某公司”
    space = re.compile(r"^\s*(" + lab + r")\s+(\S.*?)\s*$")
    return colon, space, m


INLINE_COLON, INLINE_SPACE, LABEL_CAT = _inline_regexes()


class Keyword(object):
    def __init__(self, term, replace=None):
        self.replace = replace or None
        if term.startswith("re:"):
            self.rx = re.compile(term[3:])
            self.literal = None
        else:
            self.rx = re.compile(re.escape(term))
            self.literal = term


def parse_keywords(items):
    out = []
    for it in items or []:
        if isinstance(it, dict):
            t = (it.get("term") or "").strip()
            if t:
                out.append(Keyword(t, (it.get("replace") or "").strip() or None))
        elif isinstance(it, str):
            it = it.strip()
            if not it or it.startswith("#"):
                continue
            if "=" in it and not it.startswith("re:"):
                a, b = it.split("=", 1)
                if a.strip():
                    out.append(Keyword(a.strip(), b.strip() or None))
            else:
                out.append(Keyword(it))
    return out


class Detector(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.o = cfg["options"]
        self.whitelist = [w.strip() for w in cfg.get("whitelist", []) if w and w.strip()]
        self.keywords = parse_keywords(cfg.get("keywords"))
        self.kw_replace = {}
        for k in self.keywords:
            if k.literal and k.replace:
                self.kw_replace[k.literal] = k.replace
        self.sig_re = re.compile(cfg.get("signature_block_pattern") or r"(?!x)x", re.I)

    def allowed(self, term):
        t = term.strip()
        if len(t) < 2:
            return False
        for w in self.whitelist:
            if w and (w in t or t in w):
                return False
        return True

    def _company(self, text, out):
        pos = 0
        while True:
            m = COMPANY_RE.search(text, pos)
            if not m:
                break
            s, e = m.start(), m.end()
            while True:  # 向后吞并“集团有限公司”“（集团）有限公司”之类的连续后缀
                m2 = COMPANY_SUFFIX_RUN.match(text, e) or COMPANY_PAREN_RUN.match(text, e)
                if not m2 or m2.end() <= e:
                    break
                e = m2.end()
            pos = e
            term = text[s:e]
            cut = COMPANY_SPLIT.match(term)
            if cut:
                term = term[cut.end():]
            base = COMPANY_SUFFIX_RUN.sub("", re.sub(r"[（(][^）)]*[）)]", "", term))
            if len(term) < 4 or not base or COMPANY_GENERIC.match(base) or COMPANY_SENTENCE.search(base):
                continue
            out.append((term, "org", "单位名称后缀"))

    def _company_en(self, text, out):
        if not re.search(r"[A-Za-z]{2}", text):
            return
        spans = []
        for rx in (EN_ORG_RE, EN_INST_RE):
            for m in rx.finditer(text):
                s, e = m.span()
                if any(not (e <= a or s >= b) for a, b in spans):
                    continue
                term = m.group(0).strip()
                words = re.findall(r"[A-Za-z]+", term)
                if len(words) < 3 or EN_ORG_GENERIC.match(term + " "):
                    continue
                spans.append((s, e))
                out.append((term, "org", "英文单位名称"))

    def detect_text(self, text, labels=True):
        o = self.o
        out = []
        if not text or not text.strip():
            return out
        for k in self.keywords:
            for m in k.rx.finditer(text):
                if m.group(0):
                    out.append((m.group(0), "keyword", "自定义关键词"))
        if o.get("detect_phone"):
            for rx in (RE_MOBILE, RE_LANDLINE, RE_400):
                for m in rx.finditer(text):
                    out.append((m.group(0).strip(), "phone", "电话号码"))
            for m in RE_PHONE_CTX.finditer(text):
                if len(re.sub(r"\D", "", m.group(1))) >= 7:
                    out.append((m.group(1).strip(), "phone", "电话(提示词)"))
        if o.get("detect_email"):
            for m in RE_EMAIL.finditer(text):
                out.append((m.group(0), "email", "邮箱"))
        if o.get("detect_url"):
            for m in RE_URL.finditer(text):
                out.append((m.group(0), "url", "网址"))
        if o.get("detect_idcard"):
            for m in RE_IDCARD.finditer(text):
                if idcard_ok(m.group(0)):
                    out.append((m.group(0), "idcard", "身份证号(校验通过)"))
        if o.get("detect_uscc"):
            for m in RE_USCC.finditer(text):
                if uscc_ok(m.group(0)):
                    out.append((m.group(0), "uscc", "统一社会信用代码(校验通过)"))
        if o.get("detect_account"):
            for m in RE_ACCOUNT.finditer(text):
                out.append((m.group(1).strip(), "account", "银行账号"))
            for m in RE_IM.finditer(text):
                out.append((m.group(1), "account", "QQ/微信"))
        if o.get("titleblock_cert"):
            for m in RE_CERT_CTX.finditer(text):
                out.append((m.group(1), "cert", "证书号(提示词)"))
        if o.get("coord_text"):
            for m in RE_COORD.finditer(text):
                out.append((m.group(1), "coord", "测量坐标"))
        if o.get("detect_company"):
            self._company(text, out)
            self._company_en(text, out)
        if labels:
            for line in text.split("\n"):
                for m in INLINE_COLON.finditer(line):
                    cat = LABEL_CAT.get(m.group(1))
                    if cat and o.get(CAT_OPTION[cat]):
                        for t in value_terms(cat, m.group(2)):
                            out.append((t, cat, "图签行内：" + m.group(1)))
                m = INLINE_SPACE.match(line)
                if m:
                    cat = LABEL_CAT.get(m.group(1))
                    if cat in ("org", "project", "address") and o.get(CAT_OPTION[cat]):
                        for t in value_terms(cat, m.group(2)):
                            out.append((t, cat, "图签行内：" + m.group(1)))
        return [x for x in out if self.allowed(x[0])]

    def detect_name(self, text):
        """图层名、块名等符号名：只看关键词和单位名称。"""
        out = []
        if not text:
            return out
        for k in self.keywords:
            for m in k.rx.finditer(text):
                if m.group(0):
                    out.append((m.group(0), "keyword", "自定义关键词"))
        if self.o.get("detect_company"):
            self._company(text, out)
            self._company_en(text, out)
        return [x for x in out if self.allowed(x[0])]


class Findings(object):
    def __init__(self):
        self.terms = OrderedDict()

    def add(self, term, cat, rule, fname, loc, canon=None):
        term = term.strip()
        if not term:
            return
        e = self.terms.get(term)
        if e is None:
            e = {"term": term, "cat": cat, "rule": rule, "count": 0, "files": OrderedDict(), "locs": [], "canon": canon}
            self.terms[term] = e
        elif CAT_PRIORITY.get(cat, 99) < CAT_PRIORITY.get(e["cat"], 99):
            e["cat"] = cat
            e["rule"] = rule
        e["count"] += 1
        e["files"][fname] = 1
        if len(e["locs"]) < 6:
            e["locs"].append(fname + " · " + loc)


# ---------------------------------------------------------------------
# 文字位置（用于“标签→相邻值”的图签识别）
# ---------------------------------------------------------------------

def angle_zero(a):
    return abs(((a + 180.0) % 360.0) - 180.0) < 1.0


def est_width(s, h, wf=1.0):
    w = 0.0
    for ch in s:
        o = ord(ch)
        w += 1.0 if (o >= 0x2E80 or ch in "ＭＷ") else (0.35 if ch in " .,:;!|il1'" else 0.68)
    return w * h * wf


class Item(object):
    __slots__ = ("rec", "text", "x0", "x1", "y0", "y1", "h", "rotated", "virtual", "tag", "recs")

    def __init__(self, rec, text, x0, x1, y0, y1, h, rotated, virtual=False, tag=None, recs=None):
        self.rec = rec
        self.recs = recs or [rec]
        self.text = text
        self.x0, self.x1, self.y0, self.y1 = x0, x1, y0, y1
        self.h = h
        self.rotated = rotated
        self.virtual = virtual
        self.tag = tag

    def moved(self, f):
        x0, y0 = f(self.x0, self.y0)
        x1, y1 = f(self.x1, self.y1)
        h = abs(y1 - y0) or self.h
        return Item(self.rec, self.text, min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1),
                    h, self.rotated, True, self.tag, self.recs)


def mtext_group(doc, r):
    """MTEXT 的正文 = 若干个组码 3 + 一个组码 1（在扩展数据之前）。"""
    idx = []
    for pi in doc.rpairs(r):
        c = doc.pairs[pi][0]
        if c in (1001, 101):
            break
        if c in (1, 3):
            idx.append(pi)
    return idx


def text_item(doc, r):
    t = r.type
    g = doc.rget
    gf = doc.rgetf
    if t in ("TEXT", "ATTRIB"):
        raw = g(r, 1, "") or ""
        plain = text_plain(dxf_unescape(raw)).strip()
        if not plain:
            return None
        h = gf(r, 40, 2.5) or 2.5
        rot = gf(r, 50, 0.0)
        wf = gf(r, 41, 1.0) or 1.0
        hj = int(gf(r, 72, 0))
        vj = int(gf(r, 74 if t == "ATTRIB" else 73, 0))
        x, y = gf(r, 10), gf(r, 20)
        if (hj or vj) and g(r, 11) is not None:
            ax, ay = gf(r, 11), gf(r, 21)
        else:
            ax, ay = x, y
        w = est_width(plain, h, wf)
        if hj in (3, 5):
            x0, x1 = min(x, ax), max(x, ax)
            if x1 - x0 < 1e-9:
                x1 = x0 + w
        else:
            frac = {1: 0.5, 2: 1.0, 4: 0.5}.get(hj, 0.0)
            x0 = ax - w * frac
            x1 = x0 + w
        if hj == 4 or vj == 2:
            y0 = ay - h / 2
        elif vj == 3:
            y0 = ay - h
        else:
            y0 = ay
        tag = (g(r, 2) or "").strip() if t == "ATTRIB" else None
        return Item(r, plain, x0, x1, y0, y0 + h, h, not angle_zero(rot), False, tag)
    if t == "MTEXT":
        raw = "".join(doc.pairs[pi][1] for pi in mtext_group(doc, r))
        plain = mtext_plain(dxf_unescape(raw)).strip()
        if not plain:
            return None
        h = gf(r, 40, 2.5) or 2.5
        ap = int(gf(r, 71, 1)) or 1
        x, y = gf(r, 10), gf(r, 20)
        lines = [l for l in plain.split("\n")] or [plain]
        w = max(est_width(l, h) for l in lines)
        H = h * (1 + 1.6 * (len(lines) - 1))
        col, row = (ap - 1) % 3, (ap - 1) // 3
        x0 = x - w * (0, 0.5, 1.0)[col]
        y1 = y + H * (0, 0.5, 1.0)[row]
        rot = gf(r, 50, 0.0)
        dy = gf(r, 21, 0.0)
        rotated = abs(dy) > 1e-3 or not angle_zero(rot)
        return Item(r, plain, x0, x0 + w, y1 - H, y1, h, rotated, False, None)
    return None


def merge_fragments(items):
    """把“审”“定”、“刘”“辉”这种逐字单独书写的文字，按同一行、间距相近合并成一个整体。"""
    frag = [it for it in items if not it.rotated and it.rec.type in ("TEXT", "ATTRIB")
            and re.fullmatch(r"[\u4e00-\u9fff]", it.text.strip())]
    if len(frag) < 2:
        return items
    fid = set(id(x) for x in frag)
    rest = [it for it in items if id(it) not in fid]
    frag.sort(key=lambda it: (it.y0, it.x0))
    rows = []
    for it in frag:
        for row in rows:
            r0 = row[0]
            if abs(it.y0 - r0.y0) < 0.3 * r0.h and abs(it.h - r0.h) < 0.25 * r0.h:
                row.append(it)
                break
        else:
            rows.append([it])
    for row in rows:
        row.sort(key=lambda it: it.x0)
        grp = [row[0]]
        for it in row[1:] + [None]:
            if it is not None and it.x0 - grp[-1].x1 < 3.2 * grp[-1].h:
                grp.append(it)
                continue
            if len(grp) == 1:
                rest.append(grp[0])
            else:
                rest.append(Item(grp[0].rec, "".join(g.text.strip() for g in grp), grp[0].x0, grp[-1].x1,
                                 min(g.y0 for g in grp), max(g.y1 for g in grp), sum(g.h for g in grp) / len(grp),
                                 False, grp[0].virtual, None, [g.rec for g in grp]))
            if it is not None:
                grp = [it]
    return rest


GEO_TYPES = set("LINE LWPOLYLINE POLYLINE SPLINE ARC CIRCLE ELLIPSE HATCH SOLID TRACE INSERT IMAGE OLE2FRAME OLEFRAME "
                "WIPEOUT POINT LEADER MLINE REGION".split())


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def rec_bbox(doc, r, children, block_bbox):
    """图元的外包框 (x0, y0, x1, y1)，以及是否“横平竖直的直线”（表格线）。"""
    t = r.type
    P = doc.pairs
    xs, ys = [], []
    straight = False
    if t in ("CIRCLE", "ARC"):
        cx, cy, rr = doc.rgetf(r, 10), doc.rgetf(r, 20), doc.rgetf(r, 40)
        return (cx - rr, cy - rr, cx + rr, cy + rr), False
    if t == "ELLIPSE":
        cx, cy = doc.rgetf(r, 10), doc.rgetf(r, 20)
        rr = (doc.rgetf(r, 11) ** 2 + doc.rgetf(r, 21) ** 2) ** 0.5
        return (cx - rr, cy - rr, cx + rr, cy + rr), False
    if t == "INSERT":
        ix, iy = doc.rgetf(r, 10), doc.rgetf(r, 20)
        bb = block_bbox((doc.rget(r, 2) or "").strip())
        if bb is None or not angle_zero(doc.rgetf(r, 50, 0.0)):
            return (ix, iy, ix, iy), False
        sx, sy = doc.rgetf(r, 41, 1.0) or 1.0, doc.rgetf(r, 42, 1.0) or 1.0
        (bx0, by0, bx1, by1), base = bb
        xa, xb = ix + sx * (bx0 - base[0]), ix + sx * (bx1 - base[0])
        ya, yb = iy + sy * (by0 - base[1]), iy + sy * (by1 - base[1])
        return (min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)), False
    if t == "IMAGE":
        px, py = doc.rgetf(r, 10), doc.rgetf(r, 20)
        ux, uy, vx, vy = doc.rgetf(r, 11), doc.rgetf(r, 21), doc.rgetf(r, 12), doc.rgetf(r, 22)
        w, h = doc.rgetf(r, 13, 1.0), doc.rgetf(r, 23, 1.0)
        pts = [(px, py), (px + ux * w, py + uy * w), (px + vx * h, py + vy * h), (px + ux * w + vx * h, py + uy * w + vy * h)]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)), False
    recs = [r] + children.get(r.idx, []) if t == "POLYLINE" else [r]
    bulge = False
    for rr in recs:
        lx = None
        for pi in doc.rpairs(rr):
            c, v = P[pi][0], P[pi][1]
            if c == 1001:
                break
            if c == 42 and abs(_f(v) or 0) > 1e-9:
                bulge = True
            if c in (10, 11, 12, 13):
                lx = _f(v)
            elif c in (20, 21, 22, 23) and lx is not None:
                y = _f(v)
                if y is not None:
                    xs.append(lx)
                    ys.append(y)
                lx = None
    if t in ("POLYLINE", "HATCH"):
        xs, ys = xs[1:] or xs, ys[1:] or ys   # 第一个 10/20 是 POLYLINE/HATCH 自身的标高点
    if not xs:
        return None, False
    if t in ("LINE", "LWPOLYLINE", "POLYLINE") and not bulge and len(xs) >= 2:
        straight = all(abs(xs[i + 1] - xs[i]) < 1e-6 or abs(ys[i + 1] - ys[i]) < 1e-6 for i in range(len(xs) - 1))
    return (min(xs), min(ys), max(xs), max(ys)), straight


def find_value(L, items):
    """在标签右侧同一行（找不到再找下方）寻找最近的文字。"""
    best, bgap = None, None
    lh = L.h
    cyl = (L.y0 + L.y1) / 2
    for it in items:
        if it.rotated or it.rec is L.rec:
            continue
        h = max(lh, it.h)
        if abs((it.y0 + it.y1) / 2 - cyl) > 0.75 * h:
            continue
        gap = it.x0 - L.x1
        if gap < -0.6 * lh or gap > 16 * lh:
            continue
        if it.x1 <= L.x1:
            continue
        if best is None or gap < bgap:
            best, bgap = it, gap
    if best is not None and not is_non_value(best.text):
        return best
    # 下方
    best2, bgap2 = None, None
    cxl = (L.x0 + L.x1) / 2
    for it in items:
        if it.rotated or it.rec is L.rec:
            continue
        cx = (it.x0 + it.x1) / 2
        if not (L.x0 - 1.5 * lh <= cx <= L.x1 + 1.5 * lh) and not (it.x0 <= cxl <= it.x1):
            continue
        gap = L.y0 - it.y1
        if gap < -0.3 * lh or gap > 2.5 * max(lh, it.h):
            continue
        if best2 is None or gap < bgap2:
            best2, bgap2 = it, gap
    if best2 is not None and not is_non_value(best2.text):
        return best2
    return None


def column_values(L, items):
    out = []
    lh = L.h
    for it in items:
        if it.rotated or it.rec is L.rec:
            continue
        cx = (it.x0 + it.x1) / 2
        if not (L.x0 - 2 * lh <= cx <= L.x1 + 2 * lh):
            continue
        gap = L.y0 - it.y1
        if 0 - 0.3 * lh <= gap <= 30 * lh:
            out.append(it)
    out.sort(key=lambda it: -it.y1)
    return out


def rec_loc(doc, r):
    hnd = doc.rget(r, 5)
    where = r.block if r.block else ("图纸空间" if (doc.rget(r, 67) or "").strip() == "1" else "模型空间")
    if r.parent is not None and not r.block:
        where = "图纸空间" if (doc.rget(r.parent, 67) or "").strip() == "1" else "模型空间"
    return "%s/%s%s" % (where, r.type, ("#" + hnd.strip()) if hnd else "")


TEXT_CODES = {
    "TEXT": (1,), "ATTRIB": (1,), "ATTDEF": (1, 3), "MTEXT": (1, 3), "DIMENSION": (1,), "ARC_DIMENSION": (1,),
    "LARGE_RADIAL_DIMENSION": (1,), "TOLERANCE": (1,), "RTEXT": (1,), "ARCALIGNEDTEXT": (1, 2, 3),
    "MULTILEADER": (304, 302, 1), "MLEADER": (304, 302, 1), "ACAD_TABLE": (1, 3, 302, 303), "TABLE": (1, 3, 302, 303),
    "FIELD": (1, 2, 3, 301, 302, 303, 304), "TABLECONTENT": (1, 2, 3, 300, 301, 302, 303, 304),
    "LAYOUT": (1,), "GROUP": (300,), "DATALINK": (1, 300, 301, 302, 303, 304), "XRECORD": (1, 2, 3, 4, 6, 7, 300, 301, 302, 303, 304),
}
PATH_CODES = {
    "IMAGEDEF": (1,), "PDFDEFINITION": (1,), "DWFDEFINITION": (1,), "DGNDEFINITION": (1,), "UNDERLAYDEFINITION": (1,),
    "ACDBPOINTCLOUDDEF": (1, 300, 301), "ACDBPOINTCLOUDDEFEX": (1, 300, 301), "POINTCLOUDDEF": (1, 300, 301),
    "BLOCK": (1,), "LAYOUT": (2, 7), "PLOTSETTINGS": (2, 7), "DATALINK": (1,), "MATERIAL": (3, 4, 6, 7, 8, 9),
}
STD_ENTITIES = set("""3DFACE 3DSOLID ACAD_PROXY_ENTITY ARC ARCALIGNEDTEXT ATTDEF ATTRIB BODY CIRCLE DIMENSION ARC_DIMENSION
LARGE_RADIAL_DIMENSION ELLIPSE HATCH HELIX IMAGE INSERT LEADER LIGHT LINE LWPOLYLINE MESH MLINE MLEADERSTYLE MLEADER
MULTILEADER MTEXT OLEFRAME OLE2FRAME POINT POLYLINE RAY REGION RTEXT SECTION SEQEND SHAPE SOLID SPLINE SUN SURFACE
EXTRUDEDSURFACE LOFTEDSURFACE REVOLVEDSURFACE SWEPTSURFACE PLANESURFACE NURBSURFACE TABLE ACAD_TABLE TEXT TOLERANCE
TRACE UNDERLAY PDFUNDERLAY DWFUNDERLAY DGNUNDERLAY VERTEX VIEWPORT WIPEOUT XLINE BLOCK ENDBLK WIPEOUTVARIABLES
ACDBPOINTCLOUDEX ACDBPOINTCLOUD GEOPOSITIONMARKER CAMERA NAVISWORKSMODEL""".split())


def is_dwgprops(doc, r):
    return r.type == "XRECORD" and (doc.rget(r, 1) or "").strip() == "DWGPROPS COOKIE"


def header_vars(doc):
    """返回 [(变量名, pair 索引)]"""
    out = []
    for r in doc.recs:
        if r.type == "SECTION" and r.section == "HEADER":
            cur = None
            for pi in doc.rpairs(r):
                c, v = doc.pairs[pi][0], doc.pairs[pi][1]
                if c == 9:
                    cur = v.strip()
                    continue
                if c == 2 and cur is None:
                    continue
                out.append((cur, pi))
    return out


def scan_doc(doc, det, findings, fname, analysis):
    o = det.o
    P = doc.pairs

    def add(term, cat, rule, r):
        if det.allowed(term):
            findings.add(term, cat, rule, fname, rec_loc(doc, r) if r is not None else "文件属性")

    # ---- 文件属性：工程名、作者 → 作为已知敏感词 ----
    for var, pi in header_vars(doc):
        if var == "$PROJECTNAME" and P[pi][1].strip() and o.get("titleblock_project"):
            add(dxf_unescape(P[pi][1]).strip(), "project", "文件属性 $PROJECTNAME", None)
    for r in doc.recs:
        if is_dwgprops(doc, r):
            for pi in doc.rpairs(r):
                c, v = P[pi][0], P[pi][1].strip()
                if c in (4, 8) and v and o.get("titleblock_person"):
                    vv = dxf_unescape(v)
                    if (name_like(vv) or (re.fullmatch(r"[A-Za-z][A-Za-z0-9._\-]{2,30}", vv)
                                          and vv.lower() not in ("administrator", "admin", "user", "owner", "autocad", "guest"))):
                        add(vv, "person", "文件属性 作者/最后保存人", None)

    items_by_cont = defaultdict(list)
    inserts_by_cont = defaultdict(list)
    geo_by_cont = defaultdict(list)
    children = defaultdict(list)
    block_recs = defaultdict(list)
    delete_recs = OrderedDict()      # 记录序号 -> 原因
    entity_edits = []                # ([记录序号...], 词)
    block_base = {}
    sig_blocks = set()
    unknown = defaultdict(int)
    counts = defaultdict(int)
    has_geodata = False
    ole = 0
    images = 0
    proxy_text = 0

    for r in doc.recs:
        t = r.type
        sec = r.section
        if sec == "OBJECTS" and t == "GEODATA":
            has_geodata = True
        if sec == "TABLES" and t in ("LAYER", "BLOCK_RECORD", "STYLE", "DIMSTYLE", "LTYPE", "UCS", "VIEW", "VPORT"):
            for pi in doc.rpairs(r):
                if P[pi][0] in (2, 3) and o.get("rename_symbols"):
                    for term, cat, rule in det.detect_name(dxf_unescape(P[pi][1])):
                        add(term, cat, rule + "（%s 名称）" % t, r)
            continue
        if sec not in ("ENTITIES", "BLOCKS", "OBJECTS"):
            continue
        if sec in ("ENTITIES", "BLOCKS"):
            if t == "BLOCK":
                nm = (doc.rget(r, 2) or "").strip()
                block_base[nm] = (doc.rgetf(r, 10), doc.rgetf(r, 20))
                if det.sig_re.search(dxf_unescape(nm)) and not nm.startswith("*"):
                    sig_blocks.add(nm)
                if o.get("rename_symbols"):
                    for term, cat, rule in det.detect_name(dxf_unescape(nm)):
                        add(term, cat, rule + "（块名）", r)
                continue
            if t in ("ENDBLK", "SEQEND", "VERTEX", "SECTION", "ENDSEC", "EOF"):
                continue
            counts[t] += 1
            if t not in STD_ENTITIES:
                unknown[t] += 1
            if t in ("OLE2FRAME", "OLEFRAME"):
                ole += 1
            if t == "IMAGE":
                images += 1
            if t == "ACAD_PROXY_ENTITY" or t not in STD_ENTITIES:
                for pi in doc.rpairs(r):
                    if P[pi][0] == 310:
                        proxy_text += 1
                        break
        # ---- 文字内容 ----
        codes = TEXT_CODES.get(t)
        if codes is None and sec in ("ENTITIES", "BLOCKS") and t not in STD_ENTITIES:
            codes = (1, 3, 300, 301, 302, 303, 304)
        if t == "MTEXT":
            txt = mtext_plain(dxf_unescape("".join(P[pi][1] for pi in mtext_group(doc, r))))
            for term, cat, rule in det.detect_text(txt):
                add(term, cat, rule, r)
        elif codes:
            for pi in doc.rpairs(r):
                c = P[pi][0]
                if c == 1001:
                    break
                if c in codes:
                    v = dxf_unescape(P[pi][1])
                    v = text_plain(v) if t in ("TEXT", "ATTRIB", "ATTDEF") and "\\P" not in v and "{\\" not in v else mtext_plain(v)
                    for term, cat, rule in det.detect_text(v, labels=(sec != "OBJECTS" or t in ("TABLECONTENT", "FIELD"))):
                        add(term, cat, rule, r)
        if t in ("ATTRIB", "ATTDEF"):
            tag = (doc.rget(r, 2) or "").strip()
            cat = classify_tag(tag)
            if cat and o.get(CAT_OPTION.get(cat, ""), False):
                val = dxf_unescape(doc.rget(r, 1) or "")
                val = mtext_plain(val) if ("\\P" in val or "{\\" in val) else text_plain(val)
                for term in value_terms(cat, val):
                    add(term, cat, "属性标签 " + tag, r)
        # 扩展数据中的字符串
        inx = False
        for pi in doc.rpairs(r):
            c = P[pi][0]
            if c == 1001:
                inx = True
                continue
            if inx and c == 1000:
                for term, cat, rule in det.detect_text(dxf_unescape(P[pi][1]), labels=False):
                    add(term, cat, rule + "（扩展数据）", r)
        # ---- 位置信息 ----
        if sec in ("ENTITIES", "BLOCKS"):
            if r.block:
                cont = r.block
            else:
                base = r.parent if r.parent is not None else r
                cont = "*Paper_Space" if (doc.rget(base, 67) or "").strip() == "1" else "*Model_Space"
            if t in ("TEXT", "ATTRIB", "MTEXT"):
                it = text_item(doc, r)
                if it:
                    items_by_cont[cont].append(it)
            elif t == "INSERT":
                inserts_by_cont[cont].append(r)
            if t in GEO_TYPES and r.parent is None:
                geo_by_cont[cont].append(r)
            if r.parent is not None:
                children[r.parent.idx].append(r)
            if r.block:
                block_recs[r.block].append(r)

    # ---- 图签：标签 → 相邻值 ----
    bb_cache = {}

    def block_bbox(name, depth=0):
        if name in bb_cache:
            return bb_cache[name]
        bb_cache[name] = None
        if depth > 3 or name not in block_base:
            return None
        acc = None
        for br in block_recs.get(name, []):
            if br.type not in GEO_TYPES or br.parent is not None:
                continue
            b, _ = rec_bbox(doc, br, children, lambda n: block_bbox(n, depth + 1))
            if b:
                acc = b if acc is None else (min(acc[0], b[0]), min(acc[1], b[1]), max(acc[2], b[2]), max(acc[3], b[3]))
        bb_cache[name] = (acc, block_base[name]) if acc else None
        return bb_cache[name]

    def add_value(term, cat, rule, it):
        if len(it.recs) > 1:
            joined = re.sub(r"\s+", "", term)
            if det.allowed(joined):
                findings.add(joined, cat, rule, fname, rec_loc(doc, it.rec))
                entity_edits.append(([x.idx for x in it.recs], joined))
            return
        if cat == "person" and re.search(r"\s", term.strip()):
            canon = re.sub(r"\s+", "", term)
            add(canon, cat, rule, it.rec)
            if det.allowed(term):
                findings.add(term, cat, rule, fname, rec_loc(doc, it.rec), canon=canon)
            return
        add(term, cat, rule, it.rec)

    def strokes_in(cont, x0, x1, y0, y1, maxw, maxh, h, types, why):
        n = 0
        for g in geo_by_cont.get(cont, []):
            if g.type not in types or g.idx in delete_recs:
                continue
            b, straight = rec_bbox(doc, g, children, block_bbox)
            if not b:
                continue
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                continue
            w, hh = b[2] - b[0], b[3] - b[1]
            if w > maxw or hh > maxh:
                continue
            if straight and max(w, hh) > 3 * h:
                continue        # 表格线、图框线不动
            delete_recs[g.idx] = why
            n += 1
        return n

    label_cats_on = any(o.get(opt) for _, _, _, opt in LABEL_TABLE)
    if label_cats_on or o.get("clear_signature_strokes"):
        def virtual_items(blk, depth, seen):
            if depth > 3 or blk in seen:
                return []
            seen = seen | {blk}
            res = [it for it in items_by_cont.get(blk, []) if it.rec.type != "ATTRIB"]
            for ins in inserts_by_cont.get(blk, []):
                res.extend(transformed(ins, depth + 1, seen))
            return res

        def transformed(ins, depth, seen):
            name = (doc.rget(ins, 2) or "").strip()
            if name not in block_base:
                return []
            rot = doc.rgetf(ins, 50, 0.0)
            if not angle_zero(rot):
                return []
            ix, iy = doc.rgetf(ins, 10), doc.rgetf(ins, 20)
            sx, sy = doc.rgetf(ins, 41, 1.0) or 1.0, doc.rgetf(ins, 42, 1.0) or 1.0
            bx, by = block_base[name]
            f = lambda x, y: (ix + sx * (x - bx), iy + sy * (y - by))
            return [it.moved(f) for it in virtual_items(name, depth, seen)]

        for cont in list(items_by_cont.keys()):
            items_by_cont[cont] = merge_fragments(items_by_cont[cont])
        for cont, items in items_by_cont.items():
            anchors = list(items)
            for ins in inserts_by_cont.get(cont, []):
                anchors.extend(transformed(ins, 1, frozenset([cont])))
            name_rows = []
            sign_heads = []
            for L in anchors:
                if L.rotated:
                    continue
                cat = classify_label(L.text)
                if not cat:
                    continue
                if cat in ("namecol", "signcol"):
                    if cat == "signcol":
                        sign_heads.append(L)
                    if not o.get("titleblock_person"):
                        continue
                    for it in column_values(L, items):
                        if classify_label(it.text):
                            break
                        terms = value_terms("person", it.text)
                        for term in terms:
                            add_value(term, "person", "签名栏：" + L.text.strip(), it)
                        if terms:
                            name_rows.append(it)
                    continue
                if not o.get(CAT_OPTION[cat]):
                    continue
                V = find_value(L, items)
                if V is not None:
                    terms = value_terms(cat, V.text)
                    for term in terms:
                        add_value(term, cat, "图签邻近：" + L.text.strip()[:12], V)
                    if cat == "person" and terms:
                        name_rows.append(V)
            # ---- “签名”栏里的手写笔迹 ----
            if o.get("clear_signature_strokes"):
                for L in sign_heads:
                    cx, cy, h = (L.x0 + L.x1) / 2, (L.y0 + L.y1) / 2, L.h
                    row = [a for a in anchors if a is not L and not a.rotated
                           and abs((a.y0 + a.y1) / 2 - cy) < 0.75 * max(h, a.h)]
                    lefts = [(a.x0 + a.x1) / 2 for a in row if (a.x0 + a.x1) / 2 < cx]
                    rights = [(a.x0 + a.x1) / 2 for a in row if (a.x0 + a.x1) / 2 > cx]
                    x0 = (max(lefts) + cx) / 2 if lefts else cx - 6 * h
                    x1 = (min(rights) + cx) / 2 if rights else cx + 6 * h
                    below = [it for it in name_rows if it.y1 < L.y0 + 0.3 * h]
                    y_bottom = (min(it.y0 for it in below) - 1.6 * h) if below else L.y0 - 20 * h
                    n = strokes_in(cont, x0, x1, y_bottom, L.y0 + 0.2 * h, (x1 - x0) * 1.4, 8 * h, h,
                                   GEO_TYPES - {"OLEFRAME"}, "签名栏手写笔迹")
                    if n:
                        analysis.setdefault("_sign_n", 0)
                        analysis["_sign_n"] = analysis["_sign_n"] + n

    # ---- 英文单位名与紧邻的中文单位名使用同一代号；单位名左侧的 Logo ----
    org_terms = [t for t, e in findings.terms.items() if e["cat"] == "org" and fname in e["files"]]
    if org_terms:
        cn_orgs = sorted([t for t in org_terms if has_cjk(t)], key=len, reverse=True)
        en_orgs = sorted([t for t in org_terms if not has_cjk(t)], key=len, reverse=True)
        for cont, items in items_by_cont.items():
            hit = []
            for it in items:
                cn = next((t for t in cn_orgs if t in it.text), None)
                en = next((t for t in en_orgs if t in it.text), None)
                if cn or en:
                    hit.append((it, cn, en))
            for it, cn, en in hit:
                if en and not cn:
                    for it2, cn2, _ in hit:
                        if cn2 and abs(it2.x0 - it.x0) < 3 * max(it.h, it2.h) and \
                                (0 <= it2.y0 - it.y1 < 2.5 * it2.h or 0 <= it.y0 - it2.y1 < 2.5 * it2.h):
                            e = findings.terms.get(en)
                            if e is not None and not e.get("canon") and cn2 in findings.terms:
                                e["canon"] = cn2
                                e["rule"] += "（与“%s”同一单位）" % cn2
                            break
            if o.get("clear_logo"):
                for it, cn, en in hit:
                    h = it.h
                    strokes_in(cont, it.x0 - 7 * h, it.x0 + 0.2 * h, it.y0 - 3 * h, it.y1 + 2 * h, 6 * h, 6 * h, h,
                               {"HATCH", "LWPOLYLINE", "POLYLINE", "SPLINE", "CIRCLE", "ARC", "ELLIPSE", "SOLID", "INSERT", "IMAGE"},
                               "单位 Logo 图形")

    analysis["delete_recs"] = list(delete_recs.items())
    analysis["entity_edits"] = entity_edits

    corpus = []
    for r in doc.recs:
        if r.section in ("ENTITIES", "BLOCKS", "OBJECTS", "TABLES"):
            for pi in doc.rpairs(r):
                c = P[pi][0]
                if is_string_code(c) and P[pi][1]:
                    corpus.append(dxf_unescape(P[pi][1]))
    analysis["_corpus"] = "\n".join(corpus)
    analysis.update({
        "counts": dict(counts), "unknown": dict(unknown), "geodata": has_geodata, "ole": ole,
        "images": images, "proxy_binary": proxy_text, "sig_blocks": sorted(sig_blocks),
        "encoding": doc.encoding, "acadver": doc.acadver,
    })


REGIONS = ("北京 天津 上海 重庆 河北 山西 辽宁 吉林 黑龙江 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 海南 四川 贵州 "
           "云南 陕西 甘肃 青海 台湾 内蒙古 广西 西藏 宁夏 新疆 香港 澳门 杭州 宁波 温州 绍兴 嘉兴 湖州 金华 台州 衢州 丽水 舟山 "
           "义乌 南京 苏州 无锡 常州 南通 扬州 徐州 镇江 泰州 盐城 连云港 淮安 宿迁 合肥 芜湖 福州 厦门 泉州 南昌 济南 青岛 烟台 "
           "潍坊 郑州 洛阳 武汉 长沙 广州 深圳 东莞 佛山 珠海 中山 惠州 汕头 成都 绵阳 贵阳 昆明 西安 兰州 西宁 石家庄 太原 沈阳 "
           "大连 长春 哈尔滨 南宁 桂林 海口 三亚 拉萨 银川 乌鲁木齐 呼和浩特 雄安 保定 唐山 廊坊").split()
RE_REGION_PREFIX = re.compile(r"^(?:(?:%s)(?:省|市|自治区|特别行政区)?)+(?:[\u4e00-\u9fff]{2,3}?(?:新区|区|县|市|镇))?" % "|".join(
    sorted(REGIONS, key=len, reverse=True)))
RE_PHASE_SUFFIX = re.compile(r"(?:[（(]?[一二三四五六七八九十\d]+期[）)]?|项目|工程|地块|[A-Za-z\d\-]+地块|[一二三四五六七八九十\d]+标段|"
                             r"标段|EPC|总承包|施工图|改造|新建|扩建|改扩建)+$")


def derive_variants(findings, corpora):
    """项目名常以简称出现（去掉省市前缀、“二期/项目/地块”后缀），自动补充这些简称。"""
    allc = "\n".join(corpora.values())
    for e in list(findings.terms.values()):
        if e["cat"] != "project":
            continue
        full = e["term"]
        cands = set()
        a = RE_REGION_PREFIX.sub("", full)
        b = RE_PHASE_SUFFIX.sub("", full)
        c = RE_PHASE_SUFFIX.sub("", a)
        for v in (a, b, c):
            v = v.strip()
            if v and v != full and len(v) >= 4 and has_cjk(v):
                cands.add(v)
        for v in sorted(cands, key=len, reverse=True):
            if v in findings.terms:
                continue
            n_v = allc.count(v)
            n_f = sum(allc.count(t) for t in findings.terms if v in t and t != v)
            if n_v > n_f:
                for fname, txt in corpora.items():
                    k = txt.count(v)
                    if k:
                        for _ in range(k):
                            findings.add(v, "project", "项目简称（由“%s”派生）" % full, fname, "文字")


# =====================================================================
# 映射（原文 → 代号）
# =====================================================================

def build_mapping(findings, cfg, decisions=None, previous=None):
    decisions = decisions or {}
    pseud = cfg["pseudonyms"]
    det_kw = {}
    for k in parse_keywords(cfg.get("keywords")):
        if k.literal and k.replace:
            det_kw[k.literal] = k.replace
    counters = defaultdict(int)
    prev = {}
    if previous:
        for e in previous.get("mapping", []):
            prev[e["term"]] = e
            m = re.search(r"(\d+)$", e.get("replace", ""))
            if m:
                counters[e["cat"]] = max(counters[e["cat"]], int(m.group(1)))
    mapping = OrderedDict()
    items = list(findings.terms.values())
    items.sort(key=lambda e: (CAT_PRIORITY.get(e["cat"], 99), 1 if e.get("canon") else 0))
    for e in items:
        term = e["term"]
        d = decisions.get(term, {})
        enabled = d.get("enabled", True)
        rep = (d.get("replace") or "").strip()
        canon = e.get("canon")
        if not rep and canon and canon in mapping:
            rep = mapping[canon]["replace"]
        if not rep:
            if term in det_kw:
                rep = det_kw[term]
            elif term in prev:
                rep = prev[term]["replace"]
            elif e["cat"] == "coord":
                rep = "*" * len(term)
            else:
                counters[e["cat"]] += 1
                tpl = pseud.get(e["cat"], "代号{n:02d}")
                try:
                    rep = tpl.format(n=counters[e["cat"]])
                except Exception:
                    rep = "%s%02d" % (tpl, counters[e["cat"]])
        mapping[term] = {"term": term, "replace": rep, "cat": e["cat"], "rule": e["rule"], "count": e["count"],
                         "files": list(e["files"].keys()), "locs": e["locs"], "enabled": bool(enabled)}
    return mapping


def mapping_regex(mapping):
    terms = [t for t, e in mapping.items() if e["enabled"] and t]
    if not terms:
        return None, {}
    terms.sort(key=len, reverse=True)

    def pat(t):
        e = re.escape(t)
        if re.match(r"[A-Za-z0-9]", t):
            e = r"(?<![A-Za-z0-9])" + e
        if re.search(r"[A-Za-z0-9]$", t):
            e = e + r"(?![A-Za-z0-9])"
        return e
    rx = re.compile("|".join(pat(t) for t in terms))
    rep = {t: mapping[t]["replace"] for t in terms}
    return rx, rep


# =====================================================================
# 应用脱敏
# =====================================================================

FIXED_JULIAN = "2451544.5"   # 2000-01-01 00:00
RESERVED_NAMES = set("BYLAYER BYBLOCK CONTINUOUS STANDARD 0 DEFPOINTS *MODEL_SPACE *PAPER_SPACE MODEL ANNOTATIVE".split())


def apply_doc(doc, mapping, cfg, analysis):
    o = cfg["options"]
    det = Detector(cfg)
    rx, rep = mapping_regex(mapping)
    P = doc.pairs
    log = []           # (位置, 组码, 原值, 新值, 原因)
    removed = []       # 删除的对象描述

    def sub_terms(v):
        if rx is None:
            return v
        u = dxf_unescape(v)
        if not rx.search(u):
            return v
        return doc.encode_value(rx.sub(lambda m: rep[m.group(0)], u))

    def setv(pi, new, r, why):
        old = P[pi][1]
        if new != old:
            doc.set_value(pi, new)
            log.append((rec_loc(doc, r) if r is not None else "文件头", P[pi][0], dxf_unescape(old), dxf_unescape(new), why))

    # ---- 1. 文件头变量 ----
    for r in doc.recs:
        if r.type == "SECTION" and r.section == "HEADER":
            cur = None
            for pi in doc.rpairs(r):
                c, v = P[pi][0], P[pi][1]
                if c == 9:
                    cur = v.strip()
                    continue
                if c == 2 and cur is None:
                    continue
                new = v
                why = "敏感词替换"
                if o.get("clean_metadata"):
                    if cur in ("$PROJECTNAME", "$HYPERLINKBASE", "$LASTSAVEDBY") and c == 1:
                        new, why = "", "清除文件属性"
                    elif cur in ("$FINGERPRINTGUID", "$VERSIONGUID") and c == 2:
                        new, why = "{%s}" % str(uuid.uuid4()).upper(), "重置 GUID"
                    elif cur in ("$TDINDWG", "$TDUSRTIMER") and c == 40:
                        new, why = "0.0", "清零编辑时长"
                if o.get("normalize_dates") and cur in ("$TDCREATE", "$TDUCREATE", "$TDUPDATE", "$TDUUPDATE") and c == 40:
                    new, why = FIXED_JULIAN, "统一日期"
                if o.get("strip_paths") and cur in ("$STYLESHEET", "$MENU") and c == 1 and re.search(r"[\\/]", dxf_unescape(v)):
                    new, why = doc.encode_value(basename_any(dxf_unescape(v))), "去除本机路径"
                if new == v and c in (1, 2, 3, 6, 7, 8) and (o.get("rename_symbols") or c == 1):
                    new = sub_terms(v)
                setv(pi, new, None, why if new != v else "")
            break

    # ---- 2. 缩略图 ----
    if o.get("remove_thumbnail"):
        for r in doc.recs:
            if r.section == "THUMBNAILIMAGE" and r.type in ("SECTION", "ENDSEC"):
                doc.delete_record(r)
                if r.type == "SECTION":
                    removed.append("文件缩略图（THUMBNAILIMAGE）")
        n310 = 0
        for r in doc.recs:
            if r.section == "TABLES" and r.type == "BLOCK_RECORD":
                for pi in doc.rpairs(r):
                    if P[pi][0] == 310:
                        doc.delete_pair(pi)
                        n310 += 1
        if n310:
            removed.append("块预览图数据 %d 段" % n310)

    # ---- 3. 签名/印章块、OLE ----
    sig_blocks = set(analysis.get("sig_blocks", [])) if o.get("clear_signature_blocks") else set()
    for r in doc.recs:
        if r.deleted:
            continue
        if r.section == "BLOCKS" and r.block in sig_blocks and r.type not in ("BLOCK", "ENDBLK"):
            doc.delete_record(r)
        if o.get("remove_ole") and r.section in ("ENTITIES", "BLOCKS") and r.type in ("OLE2FRAME", "OLEFRAME"):
            doc.delete_record(r)
            removed.append("OLE 嵌入对象 %s" % rec_loc(doc, r))
    for b in sorted(sig_blocks):
        removed.append("清空签名/印章类图块内容：%s" % dxf_unescape(b))
    why_n = defaultdict(int)
    kids = defaultdict(list)
    for r in doc.recs:
        if r.parent is not None:
            kids[r.parent.idx].append(r)
    for idx, why in analysis.get("delete_recs", []):
        if idx < len(doc.recs) and not doc.recs[idx].deleted:
            doc.delete_record(doc.recs[idx])
            for k in kids.get(idx, []):
                doc.delete_record(k)
            why_n[why] += 1
    for why, n in why_n.items():
        removed.append("删除%s %d 个图元" % (why, n))
    # 被删掉的签名/Logo 图块，如果已经没有别处引用，块定义里的图形也一并清空
    gone = set()
    for idx, why in analysis.get("delete_recs", []):
        r = doc.recs[idx]
        if r.type == "INSERT":
            gone.add((doc.rget(r, 2) or "").strip())
    if gone:
        still = set((doc.rget(r, 2) or "").strip() for r in doc.recs
                    if r.type == "INSERT" and not r.deleted and r.section in ("ENTITIES", "BLOCKS"))
        purge = set(b for b in gone if b and b not in still)
        for r in doc.recs:
            if r.section == "BLOCKS" and r.block in purge and r.type not in ("BLOCK", "ENDBLK") and not r.deleted:
                doc.delete_record(r)
        for b in sorted(purge):
            removed.append("清空已无引用的签名/Logo 图块：%s" % dxf_unescape(b))

    # ---- 4. 逐对象处理字符串 ----
    for r in doc.recs:
        if r.deleted or r.section in (None, "HEADER", "CLASSES", "THUMBNAILIMAGE"):
            continue
        t = r.type
        if t in ("SECTION", "ENDSEC", "EOF"):
            continue
        dwgprops = o.get("clean_metadata") and is_dwgprops(doc, r)
        path_codes = PATH_CODES.get(t, ()) if o.get("strip_paths") else ()
        sig_attr = (t == "ATTRIB" and r.parent is not None and
                    (doc.rget(r.parent, 2) or "").strip() in sig_blocks)
        mgroup = set(mtext_group(doc, r)) if t == "MTEXT" else set()
        inx = False
        pe_url = False
        for pi in doc.rpairs(r):
            c, v = P[pi][0], P[pi][1]
            if c == 1001:
                inx = True
                pe_url = v.strip() == "PE_URL"
                continue
            if pi in mgroup or not is_string_code(c):
                continue
            if t in ("ATTRIB", "ATTDEF") and c == 2 and not inx:
                continue          # 属性标签是字段名，改了会让属性提取、图签插件对不上
            if v.strip().upper() in RESERVED_NAMES:
                continue
            new, why = v, "敏感词替换"
            if dwgprops and (c in (2, 3, 4, 6, 7, 8) or 300 <= c <= 309) and v:
                new, why = "", "清除文件属性"
            elif inx and pe_url and c == 1000 and o.get("remove_hyperlinks"):
                new, why = "", "清除超链接"
            elif c in path_codes and v and re.search(r"[\\/]", dxf_unescape(v).replace("\\U+", "")):
                new, why = doc.encode_value(basename_any(dxf_unescape(v))), "去除本机路径"
            elif sig_attr and c == 1:
                new, why = "", "清空签名属性"
            elif o.get("strip_paths") and (inx and c == 1000 or t == "XRECORD") and (
                    RE_DRIVE_PATH.search(v) or RE_UNIX_PATH.search(v)):
                new = doc.encode_value(RE_UNIX_PATH.sub(lambda m: basename_any(m.group(0)), RE_DRIVE_PATH.sub(
                    lambda m: basename_any(m.group(0)), dxf_unescape(v))))
                why = "去除本机路径"
            if new == v or why == "去除本机路径":
                n2 = sub_terms(new) if (o.get("rename_symbols") or c not in (2, 3, 6, 7, 8, 1003) or
                                        t in ("TEXT", "ATTRIB", "ATTDEF", "MTEXT", "DIMENSION")) else new
                if n2 != new and new == v:
                    why = "敏感词替换"
                new = n2
            setv(pi, new, r, why)
        # MTEXT 正文整体处理（敏感词可能跨 250 字符分段）
        if mgroup:
            idx = sorted(mgroup)
            old_raw = "".join(P[pi][1] for pi in idx)
            u = dxf_unescape(old_raw)
            new_u = rx.sub(lambda m: rep[m.group(0)], u) if rx is not None else u
            if new_u != u:
                new_raw = doc.encode_value(new_u)
                chunks = [new_raw[i:i + 250] for i in range(0, len(new_raw), 250)] or [""]
                threes = [pi for pi in idx if P[pi][0] == 3]
                ones = [pi for pi in idx if P[pi][0] == 1]
                if ones:
                    last = ones[-1]
                    need3 = len(chunks) - 1
                    for k, pi in enumerate(threes):
                        if k < need3:
                            doc.set_value(pi, chunks[k])
                        else:
                            doc.delete_pair(pi)
                    if need3 > len(threes):
                        code_line = doc.lines[P[threes[0]][2]] if threes else "  3"
                        for k in range(len(threes), need3):
                            doc.insert_pair_before(last, code_line, chunks[k])
                    doc.set_value(last, chunks[-1])
                    log.append((rec_loc(doc, r), 1, mtext_plain(u), mtext_plain(new_u), "敏感词替换"))
    # 逐字书写的名字：第一个字换成代号，其余清空
    for idxs, term in analysis.get("entity_edits", []):
        e = mapping.get(term)
        if not e or not e["enabled"]:
            continue
        for k, idx in enumerate(idxs):
            r = doc.recs[idx]
            if r.deleted:
                continue
            for pi in doc.rpairs(r):
                if P[pi][0] == 1001:
                    break
                if P[pi][0] == 1:
                    setv(pi, doc.encode_value(e["replace"]) if k == 0 else "", r, "逐字书写的名字")
                    break
    return log, removed


# =====================================================================
# 校验：几何指纹 + 残留扫描
# =====================================================================

def _num_key(c, v):
    v = v.strip()
    try:
        f = float(v)
    except ValueError:
        return "%d=%s;" % (c, v)
    if f == int(f) and abs(f) < 1e15:
        return "%d=%d;" % (c, int(f))
    return "%d=%.9g;" % (c, f)


def geometry_fingerprints(doc, numeric=False):
    """numeric=True：数值按 9 位有效数字比较（用于 DWG 回读，不同转换器的小数写法不同）。"""
    out = []
    for r in doc.recs:
        if r.deleted or r.section not in ("ENTITIES", "BLOCKS"):
            continue
        h = hashlib.md5()
        h.update(r.type.encode("utf-8", "surrogateescape"))
        for pi in doc.rpairs(r):
            c, v = doc.pairs[pi][0], doc.pairs[pi][1]
            if c == 1001:
                break
            if is_numeric_code(c):
                if numeric:
                    if c in (5, 105, 330, 360) or 320 <= c <= 369 or 390 <= c <= 399 or 480 <= c <= 481:
                        continue  # 句柄、软/硬指针：转换器会重排
                    h.update(_num_key(c, v).encode("ascii", "replace"))
                else:
                    h.update(("%d=%s;" % (c, v.strip())).encode("ascii", "replace"))
        out.append((r.type, h.hexdigest(), doc.rget(r, 5)))
    return out


def binary_residual(doc, terms):
    """在二进制块（代理对象/OLE/预览图）里查找原文，只报告不修改。"""
    if not terms:
        return []
    enc_terms = []
    for t in terms:
        if len(t) < 2:
            continue
        for enc in ("utf-16-le", "utf-8", "gb18030"):
            try:
                b = t.encode(enc)
                if len(b) >= 4:
                    enc_terms.append((t, b))
            except Exception:
                pass
    hits = defaultdict(int)
    P = doc.pairs
    for r in doc.recs:
        if r.deleted:
            continue
        chunks = [P[pi][1].strip() for pi in doc.rpairs(r) if P[pi][0] in (310, 1004) and pi not in ()]
        if not chunks:
            continue
        try:
            data = bytes.fromhex("".join(chunks))
        except ValueError:
            continue
        for t, b in enc_terms:
            if b in data:
                hits[(t, r.type)] += 1
    return [{"term": t, "type": ty, "count": n} for (t, ty), n in hits.items()]


def verify(src_doc, out_path, mapping):
    res = {"ok": True, "geometry": "", "geometry_ok": True, "residual": [], "binary_residual": []}
    try:
        out = DxfDoc(out_path)
    except Exception as e:
        res.update(ok=False, geometry="输出文件无法重新解析：%s" % e, geometry_ok=False)
        return res
    a = geometry_fingerprints(src_doc)
    b = geometry_fingerprints(out)
    if len(a) != len(b):
        res["geometry_ok"] = False
        res["geometry"] = "图元数量不一致：原 %d / 新 %d" % (len(a), len(b))
    else:
        diff = [x for x, y in zip(a, b) if x[:2] != y[:2]]
        if diff:
            res["geometry_ok"] = False
            res["geometry"] = "%d 个图元的几何数据不一致（例如 %s #%s）" % (len(diff), diff[0][0], diff[0][2])
        else:
            res["geometry"] = "%d 个图元的坐标、尺寸、角度等数值全部一致" % len(a)
    rx, _ = mapping_regex(mapping)
    if rx is not None:
        hits = defaultdict(int)
        for r in out.recs:
            if r.section in ("CLASSES",):
                continue
            for pi in out.rpairs(r):
                c, v = out.pairs[pi][0], out.pairs[pi][1]
                if is_string_code(c):
                    for m in rx.finditer(dxf_unescape(v)):
                        hits[(m.group(0), r.type)] += 1
        res["residual"] = [{"term": t, "type": ty, "count": n} for (t, ty), n in hits.items()]
    terms = [t for t, e in mapping.items() if e["enabled"] and e["cat"] not in ("coord",)]
    res["binary_residual"] = binary_residual(out, terms)
    res["ok"] = res["geometry_ok"] and not res["residual"]
    return res


# =====================================================================
# DWG 转换
# =====================================================================

DWG_VERSIONS = OrderedDict([
    ("AC1032", "ACAD2018"), ("AC1027", "ACAD2013"), ("AC1024", "ACAD2010"), ("AC1021", "ACAD2007"),
    ("AC1018", "ACAD2004"), ("AC1015", "ACAD2000"), ("AC1014", "ACAD14"), ("AC1012", "ACAD13"),
])
DWG_LABEL = {"ACAD2018": "2018", "ACAD2013": "2013", "ACAD2010": "2010", "ACAD2007": "2007",
             "ACAD2004": "2004", "ACAD2000": "2000", "ACAD14": "R14", "ACAD13": "R13"}


def dwg_version_of(path):
    """读 DWG 文件头 6 个字节，返回 ODA 用的版本名，例如 AC1021 → ACAD2007；认不出返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(6).decode("ascii", "replace")
    except OSError:
        return None
    return DWG_VERSIONS.get(head)


def find_oda(cfg=None):
    cands = []
    p = (cfg or {}).get("oda_converter") or os.environ.get("ODA_CONVERTER")
    if p:
        if os.path.isdir(p) and p.endswith(".app"):
            p = os.path.join(p, "Contents", "MacOS", "ODAFileConverter")
        cands.append(p)
    cands += ["/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"]
    cands += sorted(glob.glob("/Applications/ODAFileConverter*.app/Contents/MacOS/ODAFileConverter"), reverse=True)
    cands += sorted(glob.glob(os.path.expanduser("~/Applications/ODAFileConverter*.app/Contents/MacOS/ODAFileConverter")), reverse=True)
    for pf in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        cands += sorted(glob.glob(os.path.join(pf, "ODA", "ODAFileConverter*", "ODAFileConverter.exe")), reverse=True)
    w = shutil.which("ODAFileConverter")
    if w:
        cands.append(w)
    cands += ["/usr/bin/ODAFileConverter", "/usr/local/bin/ODAFileConverter"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def _exe(name):
    return name + (".exe" if os.name == "nt" else "")


def find_libredwg(cfg=None):
    """返回 {"dwg2dxf": 路径, "dxf2dwg": 路径或 None}；找不到 dwg2dxf 返回 None。
    查找顺序：配置 libredwg_dir → 环境变量 LIBREDWG_DIR → 打包内置（libredwg/ 子目录）→ 系统 PATH。"""
    dirs = []
    for d in ((cfg or {}).get("libredwg_dir"), os.environ.get("LIBREDWG_DIR")):
        if d:
            dirs += [d, os.path.join(d, "bin")]
    bases = []
    if getattr(sys, "_MEIPASS", None):
        bases.append(sys._MEIPASS)
    if getattr(sys, "frozen", False):
        ex = os.path.dirname(os.path.abspath(sys.executable))
        bases += [ex, os.path.join(ex, "..", "Resources"), os.path.join(ex, "..", "Frameworks")]
    here = os.path.dirname(os.path.abspath(__file__))
    bases += [here, os.path.dirname(here)]
    for bs in bases:
        dirs += [os.path.join(bs, "libredwg"), os.path.join(bs, "libredwg", "bin")]
    for d in dirs:
        r = os.path.join(d, _exe("dwg2dxf"))
        if os.path.isfile(r):
            w = os.path.join(d, _exe("dxf2dwg"))
            return {"dwg2dxf": r, "dxf2dwg": w if os.path.isfile(w) else None, "dir": d}
    r = shutil.which("dwg2dxf")
    if r:
        return {"dwg2dxf": r, "dxf2dwg": shutil.which("dxf2dwg"), "dir": os.path.dirname(r)}
    return None


def dwg_tools(cfg=None):
    """当前可用的 DWG 转换器，按 dwg_converter 设置排好优先级。"""
    pref = ((cfg or {}).get("dwg_converter") or "auto").lower()
    oda = find_oda(cfg) if pref in ("auto", "oda") else None
    lib = find_libredwg(cfg) if pref in ("auto", "libredwg") else None
    return {"oda": oda, "libredwg": lib,
            "read": "oda" if oda else ("libredwg" if lib else None),
            "write": "oda" if oda else ("libredwg" if lib and lib.get("dxf2dwg") else None)}


def _run(cmd, timeout=900):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, **kw)


def _tail(p):
    return (p.stdout.decode("utf-8", "ignore")[-300:] + " " + p.stderr.decode("utf-8", "ignore")[-300:]).strip()


def oda_convert(exe, src, dst_dir, out_type, version="ACAD2018"):
    tin = tempfile.mkdtemp(prefix="oda_in_")
    try:
        shutil.copy2(src, tin)
        os.makedirs(dst_dir, exist_ok=True)
        ext = os.path.splitext(src)[1]
        cmd = [exe, tin, dst_dir, version, out_type, "0", "1", "*" + ext]
        p = _run(cmd)
        stem = os.path.splitext(os.path.basename(src))[0]
        for f in os.listdir(dst_dir):
            if os.path.splitext(f)[0] == stem and os.path.splitext(f)[1].lower() == "." + out_type.lower():
                return os.path.join(dst_dir, f)
        raise RuntimeError("ODA File Converter 未生成文件。输出：%s" % _tail(p))
    finally:
        shutil.rmtree(tin, ignore_errors=True)


def libredwg_convert(tools, src, dst_dir, out_type):
    os.makedirs(dst_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    if out_type.upper() == "DXF":
        out = os.path.join(dst_dir, stem + ".dxf")
        p = _run([tools["dwg2dxf"], "-y", "-o", out, src])
    else:
        if not tools.get("dxf2dwg"):
            raise RuntimeError("LibreDWG 缺少 dxf2dwg，无法写 DWG")
        out = os.path.join(dst_dir, stem + ".dwg")
        p = _run([tools["dxf2dwg"], "-y", "--as", "r2000", "-o", out, src])
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    raise RuntimeError("LibreDWG 转换失败：%s" % _tail(p))


def dwg_to_dxf(src, work, cfg, tools=None):
    tools = tools or dwg_tools(cfg)
    dst = tempfile.mkdtemp(prefix="dxf_", dir=work)
    errs = []
    if tools["oda"]:
        try:
            return oda_convert(tools["oda"], src, dst, "DXF", "ACAD2018"), "oda"
        except Exception as e:
            errs.append(str(e))
    if tools["libredwg"]:
        try:
            return libredwg_convert(tools["libredwg"], src, dst, "DXF"), "libredwg"
        except Exception as e:
            errs.append(str(e))
    if errs:
        raise RuntimeError("DWG 读取失败：" + "；".join(errs))
    raise RuntimeError("处理 DWG 需要 DWG 转换器：请安装免费的 ODA File Converter"
                       "（https://www.opendesign.com/guestfiles/oda_file_converter），或先在 CAD 里把 DWG 另存为 DXF")


def dxf_to_dwg(src_dxf, work, cfg, src_version=None, tools=None):
    """返回 (dwg 路径, 转换器名, 实际版本, 提示列表)。"""
    tools = tools or dwg_tools(cfg)
    notes = []
    want = (cfg.get("dwg_version") or "same")
    if want == "same":
        want = src_version if src_version in DWG_LABEL and src_version not in ("ACAD14", "ACAD13") else "ACAD2018"
    dst = tempfile.mkdtemp(prefix="dwg_", dir=work)
    if tools["oda"]:
        try:
            return oda_convert(tools["oda"], src_dxf, dst, "DWG", want), "oda", want, notes
        except Exception as e:
            notes.append("ODA 写 DWG 失败（%s），改用 LibreDWG" % e)
    if tools["libredwg"] and tools["libredwg"].get("dxf2dwg"):
        out = libredwg_convert(tools["libredwg"], src_dxf, dst, "DWG")
        notes.append("未使用 ODA，已用内置 LibreDWG 写出 DWG 2000 格式（实验功能）。正式交付前请在 CAD 里打开核对一遍；"
                     "安装 ODA File Converter 后可输出与原图相同版本的 DWG")
        return out, "libredwg", "ACAD2000", notes
    raise RuntimeError("no-dwg-writer")


def _numeric_pairs(doc, r):
    out = []
    for pi in doc.rpairs(r):
        c, v = doc.pairs[pi][0], doc.pairs[pi][1]
        if c == 1001:
            break
        if is_numeric_code(c) and not (c in (5, 105, 330, 360) or 320 <= c <= 369 or 390 <= c <= 399 or 480 <= c <= 481):
            out.append(_num_key(c, v))
    return out


def numeric_diff_detail(ref_doc, doc, limit=6):
    """按句柄配对，统计哪类图元的哪个组码不同，例如“MTEXT 组码 46 新增×800”。"""
    def index(d):
        m = {}
        for r in d.recs:
            if not r.deleted and r.section in ("ENTITIES", "BLOCKS"):
                h = (d.rget(r, 5) or "").strip()
                if h:
                    m[h] = r
        return m
    ia, ib = index(ref_doc), index(doc)
    tally = defaultdict(int)
    nent = 0
    for h, ra in ia.items():
        rb = ib.get(h)
        if rb is None or rb.type != ra.type:
            continue
        ka, kb = _numeric_pairs(ref_doc, ra), _numeric_pairs(doc, rb)
        if ka == kb:
            continue
        nent += 1
        ca = defaultdict(int)
        cb = defaultdict(int)
        for k in ka:
            ca[k] += 1
        for k in kb:
            cb[k] += 1
        codes_a = set(k.split("=")[0] for k in ka)
        codes_b = set(k.split("=")[0] for k in kb)
        seen = set()
        for k in set(ca) | set(cb):
            if ca[k] == cb[k]:
                continue
            c = k.split("=")[0]
            kind = "新增" if c not in codes_a else ("缺失" if c not in codes_b else "数值变化")
            key = "%s 组码 %s %s" % (ra.type, c, kind)
            if key not in seen:
                seen.add(key)
                tally[key] += 1
    return ["%s×%d" % kv for kv in sorted(tally.items(), key=lambda x: -x[1])[:limit]], nent


def verify_dwg(dwg_path, ref_doc, mapping, cfg, work, tools=None):
    """把写出的 DWG 再转回 DXF，核对能否打开、图元数量、几何数值和残留。"""
    res = {"ok": False, "readback": "", "count_ok": False, "geometry_ok": False, "residual": []}
    try:
        back, conv = dwg_to_dxf(dwg_path, work, cfg, tools)
        doc = DxfDoc(back)
    except Exception as e:
        res["readback"] = "写出的 DWG 读不回来：%s" % e
        return res
    a = geometry_fingerprints(ref_doc, numeric=True)
    b = geometry_fingerprints(doc, numeric=True)
    res["count_ok"] = len(a) == len(b)
    if res["count_ok"]:
        sa, sb = sorted(x[:2] for x in a), sorted(x[:2] for x in b)
        nd = sum(1 for x, y in zip(sa, sb) if x != y)
        res["geometry_ok"] = nd == 0
        if nd == 0:
            res["readback"] = "回读 %d 个图元，数量和几何数值一致" % len(a)
        else:
            det, nent = numeric_diff_detail(ref_doc, doc)
            res["diff_detail"] = det
            align = det and all(re.match(r"(ATTDEF|ATTRIB|TEXT) 组码 (10|20|30) ", d) for d in det)
            res["readback"] = "回读 %d 个图元，数量一致；%d 个图元的数值有差异：%s%s" % (
                len(a), nent or nd, "，".join(det[:5]) or "（无法按句柄配对）",
                "（文字改短/改长后，CAD 按对齐方式重算了起点，属正常）" if align else "")
    else:
        ta, tb = defaultdict(int), defaultdict(int)
        for x in a:
            ta[x[0]] += 1
        for x in b:
            tb[x[0]] += 1
        diff = ["%s %d→%d" % (k, ta[k], tb[k]) for k in sorted(set(ta) | set(tb)) if ta[k] != tb[k]][:6]
        res["readback"] = "回读图元数量不一致：原 %d / DWG %d（%s）" % (len(a), len(b), "，".join(diff))
    rx, _ = mapping_regex(mapping)
    if rx is not None:
        hits = defaultdict(int)
        for r in doc.recs:
            if r.section in ("CLASSES",):
                continue
            for pi in doc.rpairs(r):
                c, v = doc.pairs[pi][0], doc.pairs[pi][1]
                if is_string_code(c):
                    for m in rx.finditer(dxf_unescape(v)):
                        hits[(m.group(0), r.type)] += 1
        res["residual"] = [{"term": t, "type": ty, "count": n} for (t, ty), n in hits.items()]
    res["ok"] = res["count_ok"] and not res["residual"]
    return res


# =====================================================================
# 批处理流程
# =====================================================================

def collect_inputs(inputs, out_dir=None):
    files = []
    out_abs = os.path.abspath(out_dir) if out_dir else None
    for inp in inputs:
        inp = os.path.abspath(inp)
        if os.path.isdir(inp):
            for root, dirs, fs in os.walk(inp):
                if out_abs and os.path.abspath(root).startswith(out_abs):
                    continue
                dirs[:] = [d for d in dirs if not d.startswith((".", "_脱敏报告"))]
                for f in sorted(fs):
                    st, ext = os.path.splitext(f)
                    if ext.lower() in (".dxf", ".dwg") and not st.endswith("_脱敏") and not f.startswith("."):
                        full = os.path.join(root, f)
                        files.append((full, os.path.relpath(full, inp)))
        elif os.path.isfile(inp):
            if os.path.splitext(inp)[1].lower() in (".dxf", ".dwg"):
                files.append((inp, os.path.basename(inp)))
            else:
                print("跳过（不是 DXF/DWG）：%s" % inp)
        else:
            print("找不到：%s" % inp)
    return files


def run_pipeline(inputs, out_dir, cfg, report_dir=None, dry_run=False, decisions=None,
                 previous_mapping=None, log=print, files=None):
    t0 = time.time()
    files = files if files is not None else collect_inputs(inputs, out_dir)
    if not files:
        raise RuntimeError("没有找到 DXF / DWG 文件")
    work = tempfile.mkdtemp(prefix="cad_desens_")
    tools = dwg_tools(cfg) if any(os.path.splitext(f[0])[1].lower() == ".dwg" for f in files) or \
        (cfg.get("output_format") or "").lower() == "dwg" else None
    det = Detector(cfg)
    findings = Findings()
    jobs = []
    for src, rel in files:
        job = {"src": src, "rel": rel, "ext": os.path.splitext(src)[1].lower(), "dxf": None, "error": None,
               "analysis": {}, "converter": None, "dwg_version": None}
        try:
            if job["ext"] == ".dwg":
                job["dwg_version"] = dwg_version_of(src)
                log("转换 DWG → DXF：%s（DWG %s）" % (rel, DWG_LABEL.get(job["dwg_version"], "未知版本")))
                job["dxf"], job["converter"] = dwg_to_dxf(src, work, cfg, tools)
            else:
                job["dxf"] = src
            log("扫描：%s" % rel)
            doc = DxfDoc(job["dxf"])
            scan_doc(doc, det, findings, rel, job["analysis"])
        except Exception as e:
            job["error"] = str(e)
            log("  ✗ %s" % e)
        jobs.append(job)

    corpora = {}
    for job in jobs:
        corpora[job["rel"]] = job["analysis"].pop("_corpus", "")
    derive_variants(findings, corpora)
    corpora = None
    mapping = build_mapping(findings, cfg, decisions, previous_mapping)
    result = {"version": VERSION, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "dry_run": dry_run,
              "mapping": mapping, "jobs": jobs, "out_dir": out_dir, "report_dir": report_dir}

    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
        fmt = (cfg.get("output_format") or "same").lower()
        for job in jobs:
            if job["error"]:
                continue
            try:
                doc = DxfDoc(job["dxf"])
                changes, removed = apply_doc(doc, mapping, cfg, job["analysis"])
                job["changes"] = changes
                job["removed"] = removed
                job["notes"] = []
                rel_dir, base = os.path.split(job["rel"])
                stem = os.path.splitext(base)[0] + (cfg.get("output_suffix") or "_脱敏")
                want_dwg = (fmt == "dwg") or (fmt == "same" and job["ext"] == ".dwg")
                tgt_dir = os.path.join(out_dir, rel_dir)
                os.makedirs(tgt_dir, exist_ok=True)
                tmp_dxf = os.path.join(tempfile.mkdtemp(dir=work), stem + ".dxf")
                doc.save(tmp_dxf)
                job["verify"] = verify(doc, tmp_dxf, mapping)
                if want_dwg and not (tools and tools["write"]):
                    job["notes"].append("没有可用的 DWG 转换器（ODA File Converter / LibreDWG），无法输出 DWG，已改为输出 DXF")
                    want_dwg = False
                if want_dwg:
                    try:
                        got, conv, ver, notes = dxf_to_dwg(tmp_dxf, work, cfg, job["dwg_version"], tools)
                    except Exception as e:
                        got = None
                        job["notes"].append("写 DWG 失败（%s），已改为输出 DXF" % e)
                if want_dwg and got:
                    job["notes"].extend(notes)
                    job["out_converter"], job["out_version"] = conv, ver
                    log("  写出 DWG %s（%s），回读核对中…" % (DWG_LABEL.get(ver, ver), "ODA" if conv == "oda" else "LibreDWG"))
                    dv = verify_dwg(got, DxfDoc(tmp_dxf), mapping, cfg, work, tools)
                    job["verify"]["dwg"] = dv
                    if dv["residual"]:
                        job["verify"]["residual"] = job["verify"]["residual"] + dv["residual"]
                    if not dv["ok"]:
                        job["verify"]["ok"] = False
                        if not dv["count_ok"]:
                            job["verify"]["geometry_ok"] = False
                            job["verify"]["geometry"] = dv["readback"]
                    final = os.path.join(tgt_dir, stem + ".dwg")
                    shutil.copy2(got, final)
                    if conv == "libredwg" and not dv["ok"]:
                        # LibreDWG 写坏了：同时留一份 DXF，保证一定有可用结果
                        bak = os.path.join(tgt_dir, stem + ".dxf")
                        shutil.copy2(tmp_dxf, bak)
                        job["extra_outputs"] = [bak]
                        job["notes"].append("DWG 回读核对未通过（%s），已在旁边另存一份同名 DXF 作为备用" % dv["readback"])
                else:
                    final = os.path.join(tgt_dir, stem + ".dxf")
                    shutil.copy2(tmp_dxf, final)
                job["output"] = final
                v = job["verify"]
                log("  ✓ %s → %s  （改动 %d 处，几何%s，残留 %d）" % (
                    job["rel"], os.path.relpath(final, out_dir), len(changes),
                    "一致" if v["geometry_ok"] else "异常！", len(v["residual"])))
            except Exception as e:
                job["error"] = str(e)
                log("  ✗ %s：%s" % (job["rel"], e))
    if report_dir:
        write_reports(result, report_dir, cfg)
    shutil.rmtree(work, ignore_errors=True)
    result["seconds"] = round(time.time() - t0, 1)
    return result


# =====================================================================
# 报告
# =====================================================================

def mapping_export(mapping):
    return {"tool": "cad_desensitize", "version": VERSION, "mapping": [
        {"term": e["term"], "replace": e["replace"], "cat": e["cat"], "enabled": e["enabled"]} for e in mapping.values()]}


def write_reports(result, report_dir, cfg):
    os.makedirs(report_dir, exist_ok=True)
    mapping = result["mapping"]
    with open(os.path.join(report_dir, "映射表.json"), "w", encoding="utf-8") as f:
        json.dump(mapping_export(mapping), f, ensure_ascii=False, indent=1)
    with open(os.path.join(report_dir, "映射表.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["原文", "替换为", "类别", "识别依据", "出现次数", "是否替换", "所在文件"])
        for e in mapping.values():
            w.writerow([e["term"], e["replace"], CAT_NAMES.get(e["cat"], e["cat"]), e["rule"], e["count"],
                        "是" if e["enabled"] else "否（保留）", "；".join(e["files"])])
    if not result["dry_run"]:
        with open(os.path.join(report_dir, "改动明细.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["文件", "位置", "组码", "原值", "新值", "原因"])
            for j in result["jobs"]:
                for loc, code, old, new, why in j.get("changes", []):
                    w.writerow([j["rel"], loc, code, old, new, why])
    with open(os.path.join(report_dir, "脱敏报告.html"), "w", encoding="utf-8") as f:
        f.write(render_report_html(result))


def render_report_html(result):
    E = html.escape
    mapping = result["mapping"]
    jobs = result["jobs"]
    rows = []
    for e in mapping.values():
        warn = ""
        if e["cat"] == "person" and e["count"] > 40:
            warn = "<span class='warn'>出现次数偏多，请确认是人名</span>"
        rows.append("<tr class='%s'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='n'>%d</td><td>%s%s</td></tr>" % (
            "" if e["enabled"] else "off", E(e["term"]), E(e["replace"]) if e["enabled"] else "（保留原文）",
            E(CAT_NAMES.get(e["cat"], e["cat"])), E(e["rule"]), e["count"], E("；".join(e["locs"][:3])), warn))
    frows = []
    for j in jobs:
        a = j.get("analysis", {})
        notes = []
        if j.get("error"):
            notes.append("<span class='bad'>失败：%s</span>" % E(j["error"]))
        v = j.get("verify")
        if v:
            notes.append(("<span class='good'>✓ 几何校验：%s</span>" if v["geometry_ok"] else "<span class='bad'>✗ 几何校验：%s</span>") % E(v["geometry"]))
            if v["residual"]:
                notes.append("<span class='bad'>文字残留：%s</span>" % E("、".join("%s(%s×%d)" % (x["term"], x["type"], x["count"]) for x in v["residual"][:10])))
            else:
                notes.append("<span class='good'>✓ 文字残留扫描：0</span>")
            if v["binary_residual"]:
                notes.append("<span class='warn'>二进制数据（天正/代理对象/OLE）中仍检测到：%s —— 这部分无法直接修改，建议先在天正中“图纸导出 T3”或分解后再脱敏</span>" % E(
                    "、".join("%s(%s)" % (x["term"], x["type"]) for x in v["binary_residual"][:10])))
        if a.get("unknown"):
            notes.append("<span class='warn'>含非标准对象 %s（多为天正等插件对象，其内部文字可能未被处理）</span>" % E(
                "、".join("%s×%d" % kv for kv in sorted(a["unknown"].items(), key=lambda x: -x[1])[:6])))
        if a.get("geodata"):
            notes.append("<span class='warn'>文件含地理位置（GEODATA），可在 CAD 中执行 GEOREMOVE 删除</span>")
        if a.get("ole"):
            notes.append("<span class='warn'>含 OLE 嵌入对象 %d 个，请人工确认内容</span>" % a["ole"])
        if a.get("images"):
            notes.append("光栅图片引用 %d 个（路径已去除；外发时不要附带公章/签名图片文件）" % a["images"])
        if a.get("sig_blocks"):
            notes.append("签名/印章类图块：%s" % E("、".join(dxf_unescape(x) for x in a["sig_blocks"][:10])))
        dv = (v or {}).get("dwg")
        if dv:
            notes.append(("<span class='good'>✓ DWG 回读：%s</span>" if dv["ok"] else "<span class='bad'>✗ DWG 回读：%s</span>") % E(dv["readback"]))
        if j.get("out_version"):
            notes.append("输出 DWG %s（%s 写出）" % (E(DWG_LABEL.get(j["out_version"], j["out_version"])),
                                              "ODA File Converter" if j.get("out_converter") == "oda" else "LibreDWG"))
        for nt in j.get("notes", []):
            notes.append("<span class='warn'>%s</span>" % E(nt))
        for rm in j.get("removed", [])[:12]:
            notes.append("已删除：" + E(rm))
        n_changes = len(j.get("changes", []))
        frows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td class='n'>%s</td><td>%s</td></tr>" % (
            E(j["rel"]), E(a.get("acadver", "")) + " / " + E(a.get("encoding", "")),
            E(os.path.basename(j.get("output", "") or "")) or "—", n_changes if not result["dry_run"] else "—",
            "<br>".join(notes)))
    cats = defaultdict(int)
    for e in mapping.values():
        if e["enabled"]:
            cats[e["cat"]] += 1
    summary = "、".join("%s %d" % (CAT_NAMES.get(k, k), v) for k, v in sorted(cats.items(), key=lambda x: CAT_PRIORITY.get(x[0], 99)))
    title = "脱敏扫描报告（预览，未修改文件）" if result["dry_run"] else "脱敏处理报告"
    return """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>%s</title>
<style>
body{font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f6f7f9;color:#1d2433}
.wrap{max-width:1200px;margin:0 auto;padding:28px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
.meta{color:#667;font-size:13px}.alert{background:#fff4e5;border:1px solid #f3c27a;border-radius:8px;padding:10px 14px;margin:14px 0}
table{border-collapse:collapse;width:100%%;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 2px rgba(0,0,0,.06)}
th,td{padding:7px 10px;border-bottom:1px solid #eceef2;text-align:left;vertical-align:top;font-size:13px}
th{background:#eef1f5;font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.off td{color:#999}.good{color:#137a3a}.bad{color:#c62828;font-weight:600}.warn{color:#a15c00}
</style></head><body><div class="wrap">
<h1>%s</h1><div class="meta">生成时间 %s · 工具版本 %s · 文件 %d 个</div>
<div class="alert">⚠ 本报告与映射表包含<b>脱敏前的原文</b>，仅供内部核对，请勿随图纸外发。</div>
<p>已识别并替换：%s</p>
<h2>文件</h2><table><tr><th>文件</th><th>版本/编码</th><th>输出</th><th>改动</th><th>校验与提示</th></tr>%s</table>
<h2>敏感词映射（共 %d 项）</h2>
<table><tr><th>原文</th><th>替换为</th><th>类别</th><th>识别依据</th><th>次数</th><th>示例位置</th></tr>%s</table>
</div></body></html>""" % (E(title), E(title), E(result["time"]), VERSION, len(jobs), E(summary or "无"),
                           "".join(frows), len(mapping), "".join(rows) or "<tr><td colspan=6>未发现敏感信息</td></tr>")


# =====================================================================
# 图形界面（本地网页）
# =====================================================================

GUI_HTML = r"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>CAD 图纸信息脱敏工具</title>
<style>
:root{--b:#2f6fed;--bd:#e3e6ec;--mut:#6b7280}
*{box-sizing:border-box}body{margin:0;font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#1d2433}
header{background:#1d2433;color:#fff;padding:14px 28px;display:flex;align-items:center;gap:16px}
header h1{font-size:18px;margin:0;font-weight:600}header .s{color:#aab;font-size:13px}
main{max-width:1180px;margin:0 auto;padding:22px 28px 60px}
.card{background:#fff;border:1px solid var(--bd);border-radius:10px;padding:18px 20px;margin-bottom:16px}
.card h2{font-size:15px;margin:0 0 12px}
.drop{border:2px dashed #c4cad6;border-radius:10px;padding:26px;text-align:center;color:var(--mut);cursor:pointer}
.drop.on{border-color:var(--b);background:#f0f5ff}
.files{margin-top:10px;font-size:13px}.files span{display:inline-block;background:#eef1f5;border-radius:6px;padding:2px 8px;margin:3px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.grid h3{font-size:13px;color:var(--mut);margin:0 0 6px;font-weight:600}
label.o{display:flex;gap:6px;align-items:flex-start;font-size:13px;margin:4px 0}
textarea{width:100%;min-height:96px;border:1px solid var(--bd);border-radius:8px;padding:8px;font:13px/1.5 Menlo,monospace}
.row{display:flex;gap:16px}.row>div{flex:1}
button{background:var(--b);color:#fff;border:0;border-radius:8px;padding:9px 20px;font-size:14px;cursor:pointer}
button.sec{background:#fff;color:#1d2433;border:1px solid var(--bd)}button:disabled{opacity:.5;cursor:default}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
select{border:1px solid var(--bd);border-radius:6px;padding:5px}
table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #eef0f3;padding:6px 8px;font-size:13px;text-align:left;vertical-align:top}
th{background:#f3f5f8;position:sticky;top:0}td input[type=text]{width:120px;border:1px solid var(--bd);border-radius:5px;padding:3px 6px}
tr.off td{color:#aaa}.tbl{max-height:520px;overflow:auto;border:1px solid var(--bd);border-radius:8px}
.tag{display:inline-block;padding:0 6px;border-radius:4px;background:#eef1f5;font-size:12px}
.mut{color:var(--mut);font-size:12px}.ok{color:#137a3a}.bad{color:#c62828}.warn{color:#a15c00}
#log{white-space:pre-wrap;font:12px/1.5 Menlo,monospace;background:#0f1420;color:#cfe3ff;border-radius:8px;padding:10px;max-height:200px;overflow:auto;display:none}
</style></head><body>
<header><h1>CAD 图纸信息脱敏工具</h1><span class="s">DXF / DWG · 只改文字，不动几何 · 全部在本机处理</span><span class="s" id="oda" style="margin-left:auto"></span></header>
<main>
<div class="card"><h2>① 选择图纸</h2>
<div class="drop" id="drop">把 DXF / DWG 文件拖到这里，或点击选择（可多选，同一批图纸会使用同一套代号）<input type="file" id="fi" multiple accept=".dxf,.dwg,.DXF,.DWG" style="display:none"></div>
<div class="files" id="files"></div></div>

<div class="card"><h2>② 脱敏规则</h2><div class="grid" id="opts"></div>
<div class="row" style="margin-top:14px">
<div><h3 class="mut">自定义敏感词（一行一个；可写成 原词=替换词；以 re: 开头为正则）</h3><textarea id="kw" placeholder="某某花园二期=项目A&#10;某某置业有限公司=建设单位&#10;张三"></textarea></div>
<div><h3 class="mut">白名单（这些词永远不替换）</h3><textarea id="wl"></textarea></div></div>
<div class="bar" style="margin-top:12px"><span class="mut">输出格式</span>
<select id="fmt"><option value="same">与原文件相同</option><option value="dxf">DXF</option><option value="dwg">DWG</option></select>
<span class="mut">DWG 版本</span><select id="ver"><option value="same">与原图相同</option><option>ACAD2018</option><option>ACAD2013</option><option>ACAD2010</option><option>ACAD2007</option><option>ACAD2004</option><option>ACAD2000</option></select>
<span style="flex:1"></span><button id="bscan">扫描预览</button></div>
<div id="log" style="margin-top:12px"></div></div>

<div class="card" id="res" style="display:none"><h2>③ 核对识别结果 <span class="mut" id="sum"></span></h2>
<div class="bar" style="margin-bottom:10px"><span class="mut">取消勾选的词将保留原文；“替换为”可直接修改。</span><span style="flex:1"></span>
<select id="fcat"><option value="">全部类别</option></select>
<button class="sec" id="ball">全选</button><button class="sec" id="bnone">全不选</button></div>
<div class="tbl"><table><thead><tr><th style="width:30px"></th><th>原文</th><th>替换为</th><th>类别</th><th>识别依据</th><th>次数</th><th>位置示例</th></tr></thead><tbody id="tb"></tbody></table></div>
<div id="fileinfo" style="margin-top:12px"></div>
<div class="bar" style="margin-top:14px"><span style="flex:1"></span><button id="bapply">执行脱敏</button></div></div>

<div class="card" id="done" style="display:none"><h2>④ 完成</h2><div id="donebody"></div></div>
</main>
<script>
const OPTS=__OPTS__, CATS=__CATS__, WL=__WL__;
let files=[], sid=null, terms=[];
const $=id=>document.getElementById(id);
$('wl').value=WL.join('\n');
(function(){const g={};OPTS.forEach(o=>{(g[o[2]]=g[o[2]]||[]).push(o)});
 let h='';for(const k in g){h+='<div><h3>'+k+'</h3>'+g[k].map(o=>'<label class="o"><input type="checkbox" id="op_'+o[0]+'" '+(o[1]?'checked':'')+'><span>'+o[3]+'</span></label>').join('')+'</div>'}
 $('opts').innerHTML=h;
 for(const c in CATS){const op=document.createElement('option');op.value=c;op.textContent=CATS[c];$('fcat').appendChild(op)}})();
fetch('/api/status').then(r=>r.json()).then(s=>{$('oda').innerHTML=s.oda?'DWG 转换器：ODA 已就绪':(s.libredwg?'<span style="color:#ffcf7a">DWG 转换器：LibreDWG（只能写 DWG 2000，建议安装 ODA）</span>':'<span style="color:#ffcf7a">未检测到 DWG 转换器，只能处理 DXF</span>')});
const drop=$('drop');drop.onclick=()=>$('fi').click();
drop.ondragover=e=>{e.preventDefault();drop.classList.add('on')};drop.ondragleave=()=>drop.classList.remove('on');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('on');addFiles(e.dataTransfer.files)};
$('fi').onchange=e=>addFiles(e.target.files);
function addFiles(fl){for(const f of fl){if(/\.(dxf|dwg)$/i.test(f.name)&&!files.find(x=>x.name==f.name))files.push(f)}
 $('files').innerHTML=files.map(f=>'<span>'+f.name+' <small class="mut">'+(f.size/1048576).toFixed(1)+'MB</small></span>').join('');sid=null}
function cfg(){const o={};OPTS.forEach(x=>o[x[0]]=$('op_'+x[0]).checked);
 return {options:o,keywords:$('kw').value.split('\n'),whitelist:$('wl').value.split('\n').map(s=>s.trim()).filter(Boolean),output_format:$('fmt').value,dwg_version:$('ver').value}}
function b64(f){return new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result.split(',')[1]);r.onerror=no;r.readAsDataURL(f)})}
function log(s){$('log').style.display='block';$('log').textContent=s}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});const j=await r.json();if(!r.ok||j.error)throw new Error(j.error||r.statusText);return j}
$('bscan').onclick=async()=>{if(!files.length){alert('请先选择图纸');return}
 $('bscan').disabled=true;log('正在读取并扫描 '+files.length+' 个文件……');
 try{const fs=[];for(const f of files)fs.push({name:f.name,data:await b64(f)});
  const j=await post('/api/scan',{files:fs,config:cfg()});sid=j.sid;terms=j.terms;render();
  log(j.log.join('\n'));$('res').style.display='block';$('done').style.display='none';
  $('fileinfo').innerHTML=j.files.map(f=>'<div class="mut">'+f.name+'：'+(f.error?'<span class="bad">'+f.error+'</span>':f.notes.join('；'))+'</div>').join('');
  $('res').scrollIntoView({behavior:'smooth'})}catch(e){log('出错：'+e.message)}$('bscan').disabled=false};
function render(){const fc=$('fcat').value;const cnt={};terms.forEach(t=>cnt[t.cat]=(cnt[t.cat]||0)+1);
 $('sum').textContent='共 '+terms.length+' 项：'+Object.keys(cnt).map(k=>CATS[k]+' '+cnt[k]).join('、');
 $('tb').innerHTML=terms.map((t,i)=>(fc&&t.cat!=fc)?'':'<tr class="'+(t.enabled?'':'off')+'"><td><input type="checkbox" data-i="'+i+'" '+(t.enabled?'checked':'')+'></td><td>'+esc(t.term)+'</td><td><input type="text" data-r="'+i+'" value="'+esc(t.replace)+'"></td><td><span class="tag">'+CATS[t.cat]+'</span></td><td class="mut">'+esc(t.rule)+'</td><td>'+t.count+'</td><td class="mut">'+esc(t.locs.slice(0,2).join('；'))+'</td></tr>').join('')||'<tr><td colspan=7 class="mut">没有识别到敏感信息。可以在“自定义敏感词”里补充后重新扫描。</td></tr>';
 document.querySelectorAll('[data-i]').forEach(c=>c.onchange=()=>{terms[c.dataset.i].enabled=c.checked;c.closest('tr').className=c.checked?'':'off'});
 document.querySelectorAll('[data-r]').forEach(c=>c.oninput=()=>{terms[c.dataset.r].replace=c.value})}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
$('fcat').onchange=render;
$('ball').onclick=()=>{const fc=$('fcat').value;terms.forEach(t=>{if(!fc||t.cat==fc)t.enabled=true});render()};
$('bnone').onclick=()=>{const fc=$('fcat').value;terms.forEach(t=>{if(!fc||t.cat==fc)t.enabled=false});render()};
$('bapply').onclick=async()=>{if(!sid)return;$('bapply').disabled=true;log('正在脱敏……');
 try{const dec={};terms.forEach(t=>dec[t.term]={enabled:t.enabled,replace:t.replace});
  const j=await post('/api/apply',{sid:sid,config:cfg(),decisions:dec});log(j.log.join('\n'));
  $('donebody').innerHTML='<p>'+j.files.map(f=>'<div>'+(f.error?'<span class="bad">✗ '+f.name+'：'+f.error+'</span>':'<span class="'+(f.ok?'ok':'bad')+'">'+(f.ok?'✓':'⚠')+'</span> '+f.name+' → '+f.output+' <span class="mut">改动 '+f.changes+' 处 · '+f.geometry+(f.residual?' · <span class="bad">残留 '+f.residual+'</span>':'')+'</span>'+(f.warn?'<div class="warn" style="margin-left:22px">'+f.warn+'</div>':''))+'</div>').join('')+'</p>'+
  '<div class="bar"><a href="/dl/'+sid+'"><button>下载脱敏后的图纸</button></a><a href="/report/'+sid+'" target="_blank"><button class="sec">查看报告</button></a><a href="/dlreport/'+sid+'"><button class="sec">下载报告与映射表</button></a></div><p class="mut">报告和映射表含脱敏前的原文，只供内部核对，请勿随图纸外发。</p>';
  $('done').style.display='block';$('done').scrollIntoView({behavior:'smooth'})}catch(e){log('出错：'+e.message)}$('bapply').disabled=false};
</script></body></html>"""


class _Sessions(object):
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="cad_desens_gui_")
        self.data = {}
        self.lock = threading.Lock()


def run_gui(port=0, open_browser=True):
    try:
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    except ImportError:  # Python < 3.7
        from http.server import HTTPServer as ThreadingHTTPServer, BaseHTTPRequestHandler
    S = _Sessions()

    def file_notes(j):
        a = j.get("analysis", {})
        notes = ["%s · %s" % (a.get("acadver", ""), a.get("encoding", ""))]
        if j.get("converter"):
            notes.append("DWG %s 已用 %s 读取" % (DWG_LABEL.get(j.get("dwg_version"), ""), "ODA" if j["converter"] == "oda" else "LibreDWG"))
        if j.get("out_version"):
            notes.append("输出 DWG %s（%s）" % (DWG_LABEL.get(j["out_version"], ""), "ODA" if j.get("out_converter") == "oda" else "LibreDWG"))
        dv = (j.get("verify") or {}).get("dwg")
        if dv:
            notes.append(("DWG 回读：" if dv["ok"] else "DWG 回读未通过：") + dv["readback"])
        notes.extend(j.get("notes", []))
        if a.get("unknown"):
            notes.append("含非标准对象 %s（多为天正对象，内部文字可能处理不到）" % "、".join(
                "%s×%d" % kv for kv in sorted(a["unknown"].items(), key=lambda x: -x[1])[:4]))
        if a.get("sig_blocks"):
            notes.append("签名/印章类图块：%s" % "、".join(dxf_unescape(x) for x in a["sig_blocks"][:6]))
        if a.get("ole"):
            notes.append("OLE 嵌入对象 %d 个" % a["ole"])
        if a.get("geodata"):
            notes.append("含地理位置信息")
        return notes

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False))

        def do_GET(self):
            p = self.path.split("?")[0]
            if p == "/":
                page = GUI_HTML.replace("__OPTS__", json.dumps([list(x) for x in OPTION_INFO], ensure_ascii=False)) \
                    .replace("__CATS__", json.dumps(CAT_NAMES, ensure_ascii=False)) \
                    .replace("__WL__", json.dumps(DEFAULT_CONFIG["whitelist"], ensure_ascii=False))
                return self._send(200, page, "text/html; charset=utf-8")
            if p == "/api/status":
                t = dwg_tools()
                return self._json({"oda": bool(t["oda"]), "libredwg": bool(t["libredwg"]), "dwg": t["write"], "version": VERSION})
            m = re.match(r"^/(dl|report|dlreport)/([0-9a-f]+)$", p)
            if m:
                s = S.data.get(m.group(2))
                if not s or "result" not in s:
                    return self._send(404, "not found", "text/plain")
                if m.group(1) == "report":
                    with open(os.path.join(s["dir"], "report", "脱敏报告.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                src = os.path.join(s["dir"], "out" if m.group(1) == "dl" else "report")
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for root, _, fs in os.walk(src):
                        for f in fs:
                            full = os.path.join(root, f)
                            z.write(full, os.path.relpath(full, src))
                name = "脱敏图纸.zip" if m.group(1) == "dl" else "脱敏报告_内部留存.zip"
                from urllib.parse import quote
                return self._send(200, buf.getvalue(), "application/zip",
                                  {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)})
            self._send(404, "not found", "text/plain")

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n).decode("utf-8"))
                cfg = merge_config(body.get("config") or {})
                logs = []
                if self.path == "/api/scan":
                    sid = uuid.uuid4().hex
                    d = os.path.join(S.root, sid)
                    os.makedirs(os.path.join(d, "in"))
                    files = []
                    for f in body.get("files", []):
                        name = os.path.basename(f["name"])
                        full = os.path.join(d, "in", name)
                        with open(full, "wb") as fo:
                            fo.write(base64.b64decode(f["data"]))
                        files.append((full, name))
                    res = run_pipeline([], None, cfg, dry_run=True, log=logs.append, files=files)
                    S.data[sid] = {"dir": d, "files": files}
                    terms = [{"term": e["term"], "replace": e["replace"], "cat": e["cat"], "rule": e["rule"],
                              "count": e["count"], "locs": e["locs"], "enabled": e["enabled"]} for e in res["mapping"].values()]
                    fl = [{"name": j["rel"], "error": j["error"], "notes": file_notes(j)} for j in res["jobs"]]
                    return self._json({"sid": sid, "terms": terms, "files": fl, "log": logs})
                if self.path == "/api/apply":
                    s = S.data.get(body.get("sid"))
                    if not s:
                        return self._json({"error": "会话已过期，请重新扫描"}, 400)
                    out = os.path.join(s["dir"], "out")
                    rep = os.path.join(s["dir"], "report")
                    shutil.rmtree(out, ignore_errors=True)
                    shutil.rmtree(rep, ignore_errors=True)
                    res = run_pipeline([], out, cfg, report_dir=rep, decisions=body.get("decisions") or {},
                                       log=logs.append, files=s["files"])
                    s["result"] = True
                    fl = []
                    for j in res["jobs"]:
                        v = j.get("verify") or {}
                        warn = []
                        if v.get("binary_residual"):
                            warn.append("二进制数据（天正/代理对象/OLE）中仍有：" + "、".join(x["term"] for x in v["binary_residual"][:6]))
                        fl.append({"name": j["rel"], "error": j["error"], "output": os.path.basename(j.get("output") or ""),
                                   "changes": len(j.get("changes", [])), "geometry": v.get("geometry", ""),
                                   "ok": v.get("ok", False), "residual": len(v.get("residual", [])), "warn": "；".join(warn)})
                    return self._json({"files": fl, "log": logs})
                self._json({"error": "unknown"}, 404)
            except Exception as e:
                self._json({"error": str(e)}, 500)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    print("CAD 图纸信息脱敏工具已启动：%s" % url)
    print("（所有文件只在本机处理。关闭此窗口或按 Ctrl+C 退出）")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(S.root, ignore_errors=True)


# =====================================================================
# 命令行
# =====================================================================

def main(argv=None):
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="CAD 图纸信息脱敏工具 v%s（DXF/DWG）" % VERSION)
    sub = ap.add_subparsers(dest="cmd")

    def common(p):
        p.add_argument("inputs", nargs="+", help="DXF/DWG 文件或文件夹")
        p.add_argument("-c", "--config", help="配置文件（JSON），可用 init-config 生成")
        p.add_argument("-k", "--keywords", help="补充敏感词，逗号分隔，可写 原词=替换词")
        p.add_argument("-m", "--mapping", help="沿用之前的映射表.json，保证多批图纸代号一致")
        p.add_argument("-r", "--report", help="报告目录（默认：输出目录旁的 _脱敏报告）")

    p = sub.add_parser("run", help="执行脱敏")
    common(p)
    p.add_argument("-o", "--out", help="输出目录（默认：输入旁边的“脱敏输出”）")
    p.add_argument("-f", "--format", choices=["same", "dxf", "dwg"], help="输出格式")
    p.add_argument("--dwg-version", choices=["same"] + list(DWG_LABEL)[:6], help="输出 DWG 版本（默认 same：与原图相同）")
    p.add_argument("--converter", choices=["auto", "oda", "libredwg"], help="DWG 转换器（默认 auto：ODA 优先，LibreDWG 兜底）")
    p = sub.add_parser("scan", help="只扫描，生成报告，不修改")
    common(p)
    p = sub.add_parser("gui", help="打开图形界面")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    sub.add_parser("check-dwg", help="查看本机可用的 DWG 转换器")
    p = sub.add_parser("init-config", help="导出默认配置文件")
    p.add_argument("path", nargs="?", default="脱敏配置.json")
    a = ap.parse_args(argv)

    if not a.cmd:
        run_gui()
        return 0
    if a.cmd == "gui":
        run_gui(a.port, not a.no_browser)
        return 0
    if a.cmd == "check-dwg":
        t = dwg_tools(load_config(None))
        print("ODA File Converter：%s" % (t["oda"] or "未找到"))
        lib = t["libredwg"]
        print("LibreDWG：%s" % (("%s（写 DWG：%s）" % (lib["dwg2dxf"], lib["dxf2dwg"] or "无")) if lib else "未找到"))
        print("读 DWG 用：%s；写 DWG 用：%s" % (t["read"] or "无", t["write"] or "无"))
        return 0 if t["write"] else 2
    if a.cmd == "init-config":
        with open(a.path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print("已生成：%s" % a.path)
        return 0
    cfg = load_config(a.config)
    if a.keywords:
        cfg["keywords"] = list(cfg.get("keywords") or []) + [k for k in re.split(r"[,，]", a.keywords) if k.strip()]
    first = os.path.abspath(a.inputs[0])
    base_dir = first if os.path.isdir(first) else os.path.dirname(first)
    prev = None
    if a.mapping and os.path.isfile(a.mapping):
        with open(a.mapping, "r", encoding="utf-8") as f:
            prev = json.load(f)
    if a.cmd == "scan":
        rep = a.report or os.path.join(base_dir, "_脱敏报告(含原文,勿外发)")
        res = run_pipeline(a.inputs, None, cfg, report_dir=rep, dry_run=True, previous_mapping=prev)
    else:
        if getattr(a, "format", None):
            cfg["output_format"] = a.format
        if getattr(a, "dwg_version", None):
            cfg["dwg_version"] = a.dwg_version
        if getattr(a, "converter", None):
            cfg["dwg_converter"] = a.converter
        out = a.out or os.path.join(base_dir, "脱敏输出")
        rep = a.report or os.path.join(out, "_脱敏报告(含原文,勿外发)")
        res = run_pipeline(a.inputs, out, cfg, report_dir=rep, previous_mapping=prev)
    print("")
    print("识别到敏感词 %d 项：" % len(res["mapping"]))
    for e in list(res["mapping"].values())[:60]:
        print("  [%s] %s → %s  （%s，%d 次）" % (CAT_NAMES.get(e["cat"], e["cat"]), e["term"], e["replace"], e["rule"], e["count"]))
    if len(res["mapping"]) > 60:
        print("  ……其余见报告")
    print("报告：%s" % os.path.join(rep, "脱敏报告.html"))
    if a.cmd == "run":
        print("输出：%s" % out)
    bad = [j for j in res["jobs"] if j["error"] or (j.get("verify") and not j["verify"]["ok"])]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
