# -*- coding: utf-8 -*-
"""生成测试用样例图纸（虚构的项目、人员、单位）。"""
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "samples")
os.makedirs(OUT, exist_ok=True)


def idcard(prefix17):
    w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    return prefix17 + "10X98765432"[sum(int(prefix17[i]) * w[i] for i in range(17)) % 11]


def uscc(prefix17):
    chars = "0123456789ABCDEFGHJKLMNPQRTUWXY"
    w = [1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28]
    c = 31 - sum(chars.index(prefix17[i]) * w[i] for i in range(17)) % 31
    return prefix17 + chars[0 if c == 31 else c]


ID = idcard("33010619800101123")
CREDIT = uscc("91330106MA2H3K5L7")

H = [0]


def hd():
    H[0] += 1
    return "%X" % (H[0] + 0x100)


def text(x, y, s, h=3.5, layer="TK", extra=()):
    return [(0, "TEXT"), (5, hd()), (330, "1F"), (100, "AcDbEntity"), (8, layer), (100, "AcDbText"),
            (10, "%.4f" % x), (20, "%.4f" % y), (30, "0.0"), (40, "%.2f" % h), (1, s)] + list(extra) + [(100, "AcDbText")]


def attdef(x, y, tag, default, h=3.5):
    return [(0, "ATTDEF"), (5, hd()), (330, "1F"), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"),
            (10, "%.4f" % x), (20, "%.4f" % y), (30, "0.0"), (40, "%.2f" % h), (1, default), (100, "AcDbAttributeDefinition"),
            (3, tag), (2, tag), (70, "0")]


def attrib(x, y, tag, val, h=3.5):
    return [(0, "ATTRIB"), (5, hd()), (330, "1F"), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"),
            (10, "%.4f" % x), (20, "%.4f" % y), (30, "0.0"), (40, "%.2f" % h), (1, val), (100, "AcDbAttribute"),
            (2, tag), (70, "0")]


def line(x1, y1, x2, y2, layer="A-WALL", xdata=()):
    return [(0, "LINE"), (5, hd()), (330, "1F"), (100, "AcDbEntity"), (8, layer), (100, "AcDbLine"),
            (10, "%.4f" % x1), (20, "%.4f" % y1), (30, "0.0"), (11, "%.4f" % x2), (21, "%.4f" % y2), (31, "0.0")] + list(xdata)


def build(unicode_esc=False):
    H[0] = 0
    P = []
    # HEADER
    P += [(0, "SECTION"), (2, "HEADER"),
          (9, "$ACADVER"), (1, "AC1009" if unicode_esc else "AC1032"),
          (9, "$DWGCODEPAGE"), (3, "ANSI_936"),
          (9, "$INSBASE"), (10, "0.0"), (20, "0.0"), (30, "0.0"),
          (9, "$CLAYER"), (8, "0"),
          (9, "$TDCREATE"), (40, "2460123.4567"),
          (9, "$TDUPDATE"), (40, "2460223.1234"),
          (9, "$TDINDWG"), (40, "3.2516"),
          (9, "$PROJECTNAME"), (1, "杭州明湖花园二期"),
          (9, "$HYPERLINKBASE"), (1, "\\\\FS01\\项目\\明湖花园"),
          (9, "$FINGERPRINTGUID"), (2, "{8E1C1A3B-0F7E-4D0B-9C7A-1C2D3E4F5A6B}"),
          (0, "ENDSEC")]
    P += [(0, "SECTION"), (2, "CLASSES"), (0, "ENDSEC")]
    # TABLES
    P += [(0, "SECTION"), (2, "TABLES"),
          (0, "TABLE"), (2, "LAYER"), (5, "2"), (70, "4")]
    for nm in ("0", "A-WALL", "DIM", "TK", "浙江青禾示例建筑设计研究院有限公司-图框"):
        P += [(0, "LAYER"), (5, hd()), (100, "AcDbSymbolTableRecord"), (100, "AcDbLayerTableRecord"), (2, nm), (70, "0"), (62, "7"), (6, "Continuous")]
    P += [(0, "ENDTAB"),
          (0, "TABLE"), (2, "BLOCK_RECORD"), (5, "1"), (70, "3")]
    for nm in ("*Model_Space", "*Paper_Space", "A2图框", "张伟签名", "院LOGO", "底图"):
        P += [(0, "BLOCK_RECORD"), (5, hd()), (100, "AcDbSymbolTableRecord"), (100, "AcDbBlockTableRecord"), (2, nm),
              (340, "0"), (310, "4241424344454647"), (310, "48494A4B")]
    P += [(0, "ENDTAB"), (0, "ENDSEC")]
    # BLOCKS
    P += [(0, "SECTION"), (2, "BLOCKS")]
    P += [(0, "BLOCK"), (5, hd()), (8, "0"), (2, "*Model_Space"), (70, "0"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (3, "*Model_Space"), (1, ""), (0, "ENDBLK"), (5, hd()), (8, "0")]
    # 图框块：静态标签（块内局部坐标，基点 0,0）
    P += [(0, "BLOCK"), (5, hd()), (8, "0"), (2, "A2图框"), (70, "2"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (3, "A2图框"), (1, "")]
    P += line(0, 0, 180, 0, "TK") + line(0, 60, 180, 60, "TK")
    rows = [("工程名称", 52), ("建设单位", 45), ("设计单位", 38), ("工程编号", 31)]
    for lab, y in rows:
        P += text(2, y, lab)
    roles = [("设  计", 52), ("校  对", 45), ("审  核", 38), ("审  定", 31), ("项目负责人", 24)]
    for lab, y in roles:
        P += text(100, y, lab)
    P += text(2, 24, "图  号") + text(2, 17, "比  例") + text(2, 10, "日  期")
    P += attdef(22, 52, "PROJECTNAME", "") + attdef(122, 52, "SJ", "") + attdef(122, 45, "JH", "") + attdef(122, 38, "SH", "")
    P += [(0, "ENDBLK"), (5, hd()), (8, "0")]
    # 签名块
    P += [(0, "BLOCK"), (5, hd()), (8, "0"), (2, "张伟签名"), (70, "0"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (3, "张伟签名"), (1, "")]
    P += [(0, "LWPOLYLINE"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbPolyline"), (90, "3"), (70, "0"),
          (10, "0.0"), (20, "0.0"), (10, "3.0"), (20, "2.0"), (10, "6.0"), (20, "0.5")]
    P += [(0, "ENDBLK"), (5, hd()), (8, "0")]
    P += [(0, "BLOCK"), (5, hd()), (8, "0"), (2, "院LOGO"), (70, "0"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (3, "院LOGO"), (1, "")]
    P += [(0, "CIRCLE"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbCircle"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (40, "5.0")]
    P += [(0, "ENDBLK"), (5, hd()), (8, "0")]
    # 外部参照
    P += [(0, "BLOCK"), (5, hd()), (8, "0"), (2, "底图"), (70, "4"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (3, "底图"),
          (1, "D:\\项目\\杭州明湖花园二期\\总图\\底图.dwg"), (0, "ENDBLK"), (5, hd()), (8, "0")]
    P += [(0, "ENDSEC")]
    # ENTITIES
    P += [(0, "SECTION"), (2, "ENTITIES")]
    P += line(0, 0, 12000, 0) + line(12000, 0, 12000, 8000) + line(0, 8000, 12000, 8000,
                                                                     xdata=[(1001, "PE_URL"), (1000, "http://oa.example.com/proj/1203"), (1002, "{"), (1000, "明湖花园资料"), (1002, "}")])
    P += [(0, "DIMENSION"), (5, hd()), (100, "AcDbEntity"), (8, "DIM"), (100, "AcDbDimension"), (2, "*D1"),
          (10, "12000.0"), (20, "-800.0"), (30, "0.0"), (11, "6000.0"), (21, "-700.0"), (31, "0.0"), (70, "32"), (1, ""), (3, "Standard"),
          (100, "AcDbAlignedDimension"), (13, "0.0"), (23, "0.0"), (33, "0.0"), (14, "12000.0"), (24, "0.0"), (34, "0.0")]
    P += text(500, 4000, "客厅", 300, "A-ANNO") + text(500, 3500, "C30 混凝土 HRB400", 250, "A-ANNO")
    P += text(500, 3000, "±0.000=黄海高程5.300m", 250, "A-ANNO")
    P += text(500, 2500, "设计：张伟  校对：李娜", 250, "A-ANNO")
    P += text(500, 2000, "X=3345678.123 Y=512345.678", 250, "A-ANNO")
    long_notes = ("{\\fSimSun|b0|i0|c134;设计说明}\\P1. 本工程±0.000相当于黄海高程5.300m，室内外高差0.450m。\\P"
                  "2. 混凝土强度等级：基础C35，梁板柱C30；钢筋采用HRB400，保护层厚度详见结构总说明。\\P"
                  "3. 施工单位应具有相应资质，施工前应会同监理单位核对现场尺寸。\\P"
                  "4. 本图尺寸以毫米计，标高以米计。砌体采用MU10蒸压加气混凝土砌块，M7.5混合砂浆砌筑。\\P"
                  "5. 联系人：张伟，电话：13812345678，传真：0571-87654321，邮箱 zhangwei@example.com\\P"
                  "6. 建设单位：杭州明湖示例置业有限公司（统一社会信用代码 " + CREDIT + "）\\P"
                  "7. 图集参见22G101-1（中国建筑标准设计研究院），防水做法由甲方指定厂家深化。\\P"
                  "8. 现场负责人身份证 " + ID + "，开户账号：6222 0212 0300 1234 567")
    chunks = [long_notes[i:i + 250] for i in range(0, len(long_notes), 250)]
    P += [(0, "MTEXT"), (5, hd()), (100, "AcDbEntity"), (8, "A-ANNO"), (100, "AcDbMText"),
          (10, "14000.0"), (20, "8000.0"), (30, "0.0"), (40, "250.0"), (41, "9000.0"), (71, "1"), (72, "5")]
    for c in chunks[:-1]:
        P += [(3, c)]
    P += [(1, chunks[-1]), (7, "Standard")]
    # 图框插入（模型空间 1:100，插入点 20000,0）——值放在属性和相邻文字里
    ix, iy, s = 20000.0, 0.0, 100.0
    P += [(0, "INSERT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbBlockReference"), (66, "1"), (2, "A2图框"),
          (10, "%.1f" % ix), (20, "%.1f" % iy), (30, "0.0"), (41, "%.1f" % s), (42, "%.1f" % s), (43, "%.1f" % s)]
    P += attrib(ix + 22 * s, iy + 52 * s, "PROJECTNAME", "杭州明湖花园二期", 350)
    P += attrib(ix + 122 * s, iy + 52 * s, "SJ", "张伟", 350)
    P += attrib(ix + 122 * s, iy + 45 * s, "JH", "李娜", 350)
    P += attrib(ix + 122 * s, iy + 38 * s, "SH", "王建国", 350)
    P += [(0, "SEQEND"), (5, hd()), (8, "TK")]
    # 这些值是普通文字，需要靠“标签相邻”识别
    P += text(ix + 22 * s, iy + 45 * s, "杭州明湖示例置业有限公司", 350, "TK")
    P += text(ix + 22 * s, iy + 38 * s, "浙江青禾示例建筑设计研究院有限公司", 350, "TK")
    P += text(ix + 22 * s, iy + 31 * s, "HC2023-JZ-015", 350, "TK")
    P += text(ix + 22 * s, iy + 24 * s, "建施-01", 350, "TK")
    P += text(ix + 22 * s, iy + 17 * s, "1:100", 350, "TK")
    P += text(ix + 122 * s, iy + 31 * s, "陈晓东", 350, "TK")
    P += text(ix + 122 * s, iy + 24 * s, "周敏", 350, "TK")
    P += [(0, "INSERT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbBlockReference"), (2, "张伟签名"),
          (10, "%.1f" % (ix + 140 * s)), (20, "%.1f" % (iy + 52 * s)), (30, "0.0")]
    P += [(0, "IMAGE"), (5, "IMG1"), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbRasterImage"), (10, "0.0"), (20, "0.0"), (30, "0.0"),
          (11, "1.0"), (21, "0.0"), (31, "0.0"), (12, "0.0"), (22, "1.0"), (32, "0.0"), (340, "IMD1")]
    P += [(0, "ENDSEC")]
    # OBJECTS
    P += [(0, "SECTION"), (2, "OBJECTS"),
          (0, "DICTIONARY"), (5, "C"), (100, "AcDbDictionary"), (3, "DWGPROPS"), (350, "DP1"),
          (0, "XRECORD"), (5, "DP1"), (100, "AcDbXrecord"), (280, "1"), (1, "DWGPROPS COOKIE"),
          (2, "杭州明湖花园二期-建施"), (3, "施工图"), (4, "zhangwei"), (6, "青禾院内部"), (7, "明湖 住宅"), (8, "张伟"),
          (9, "12"), (300, "设计院=浙江青禾示例建筑设计研究院有限公司"), (301, "="), (40, "0.0"), (41, "2460123.4"), (42, "2460223.1"),
          (0, "IMAGEDEF"), (5, "IMD1"), (100, "AcDbRasterImageDef"), (90, "0"), (1, "C:\\Users\\zhangwei\\Desktop\\青禾院公章.png"),
          (10, "800.0"), (20, "800.0"),
          (0, "LAYOUT"), (5, hd()), (100, "AcDbPlotSettings"), (1, ""), (2, "\\\\HC-PRINT01\\HP DesignJet T830"), (4, "A2"),
          (6, ""), (7, "D:\\青禾院\\样式\\monochrome.ctb"), (100, "AcDbLayout"), (1, "明湖花园-1F平面")]
    P += [(0, "ENDSEC")]
    P += [(0, "SECTION"), (2, "THUMBNAILIMAGE"), (90, "8"), (310, "0011223344556677"), (0, "ENDSEC")]
    P += [(0, "EOF")]
    return P


def write(path, pairs, enc="utf-8", escape=False, crlf=False):
    nl = "\r\n" if crlf else "\n"
    out = []
    for c, v in pairs:
        v = str(v)
        if escape:
            v = "".join(ch if ord(ch) < 128 or ord(ch) % 3 else "\\U+%04X" % ord(ch) for ch in v)
        out.append("%3d" % c)
        out.append(v)
    with open(path, "wb") as f:
        f.write((nl.join(out) + nl).encode(enc))


write(os.path.join(OUT, "样例_新版UTF8.dxf"), build())
write(os.path.join(OUT, "样例_旧版GBK.dxf"), build(unicode_esc=True), enc="gb18030", escape=True, crlf=True)

def build_sign_table():
    """仿真会签栏：逐字书写/加空格的名字、手写签名笔迹、中英文单位名 + Logo。"""
    H[0] = 0x500
    P = [(0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, "AC1032"), (9, "$DWGCODEPAGE"), (3, "ANSI_936"), (0, "ENDSEC"),
         (0, "SECTION"), (2, "ENTITIES")]

    def ctext(cx, y, s, h=20):
        return [(0, "TEXT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"), (10, "%.3f" % cx), (20, "%.3f" % y),
                (30, "0.0"), (40, "%.1f" % h), (1, s), (72, "1"), (11, "%.3f" % cx), (21, "%.3f" % y), (31, "0.0"), (100, "AcDbText")]

    def lw(pts, layer="SIGN", bulge=None, closed=False):
        out = [(0, "LWPOLYLINE"), (5, hd()), (100, "AcDbEntity"), (8, layer), (100, "AcDbPolyline"), (90, str(len(pts))),
               (70, "1" if closed else "0")]
        for i, (x, y) in enumerate(pts):
            out += [(10, "%.3f" % x), (20, "%.3f" % y)]
            if bulge and i in bulge:
                out += [(42, "0.4142")]
        return out

    def spline(pts):
        out = [(0, "SPLINE"), (5, hd()), (100, "AcDbEntity"), (8, "SIGN"), (100, "AcDbSpline"), (70, "8"), (71, "3"),
               (72, "0"), (73, str(len(pts))), (74, "0")]
        for x, y in pts:
            out += [(10, "%.3f" % x), (20, "%.3f" % y), (30, "0.0")]
        return out

    xs = [0, 130, 340, 550]
    rows_y = [650 - 50 * i for i in range(14)]          # 650 ... 0
    for y in rows_y:
        P += line(0, y, 550, y, "TK")
    for x in xs:
        P += line(x, 0, x, 650, "TK")
    P += ctext(235, 615, "实    名") + ctext(445, 615, "签    名")
    labels = ["审    定", None, "校    对", "项目负责人", None, "专业负责人", "设    计", "绘    图", "方    案"]
    names = ["赵一鸣", "孙    昊", "郑可欣", "何志远", "何志远", None, "林    岚", "林    岚", ""]
    for i in range(9):
        y = 565 - 50 * i
        if labels[i]:
            P += ctext(65, y if i != 3 else y - 25, labels[i])
        if names[i]:
            P += ctext(235, y, names[i])
    # “审 核”、“苏 晴”逐字书写
    P += ctext(45, 515, "审") + ctext(85, 515, "核")
    P += ctext(45, 315, "专业负责人"[0:0] or "") if False else []
    P += ctext(215, 315, "苏") + ctext(255, 315, "晴")
    # 签名笔迹：样条、多段线，有的越过格线
    import math
    for i, y in enumerate([565, 515, 465, 415, 315, 265]):
        pts = [(370 + k * 18, y + 18 * math.sin(k * 1.3 + i)) for k in range(9)]
        P += spline(pts) if i % 2 == 0 else lw(pts)
    P += lw([(380, 430), (420, 380), (470, 410), (520, 375)])           # 跨两行的“何志远”
    # 一个签名是图块
    P += [(0, "INSERT"), (5, hd()), (100, "AcDbEntity"), (8, "SIGN"), (100, "AcDbBlockReference"), (2, "QM7"),
          (10, "400.0"), (20, "220.0"), (30, "0.0")]
    P += ctext(65, 165, "版本号") + ctext(235, 165, "01") + ctext(65, 115, "日    期") + ctext(235, 115, "2025.07")
    P += ctext(65, 65, "执业专用章")
    # 设计单位 + Logo
    P += ctext(80, 950, "设计单位", 30)
    P += [(0, "TEXT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"), (10, "120.0"), (20, "860.0"), (30, "0.0"),
          (40, "30.0"), (1, "云溪市示例建筑设计研究院有限公司"), (100, "AcDbText")]
    P += [(0, "TEXT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"), (10, "120.0"), (20, "825.0"), (30, "0.0"),
          (40, "20.0"), (1, "Yunxi Example Architectural Design Institute Co.,Ltd."), (100, "AcDbText")]
    P += lw([(60, 820), (110, 820), (110, 890), (60, 890)], "LOGO", bulge={0, 1, 2, 3}, closed=True)
    P += [(0, "HATCH"), (5, hd()), (100, "AcDbEntity"), (8, "LOGO"), (100, "AcDbHatch"), (10, "0.0"), (20, "0.0"), (30, "0.0"),
          (2, "SOLID"), (70, "1"), (71, "0"), (91, "1"), (92, "2"), (72, "0"), (73, "1"), (93, "4"),
          (10, "62.0"), (20, "822.0"), (10, "108.0"), (20, "822.0"), (10, "108.0"), (20, "850.0"), (10, "62.0"), (20, "850.0"),
          (97, "0"), (75, "0"), (76, "1"), (98, "1"), (10, "85.0"), (20, "835.0")]
    P += [(0, "TEXT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"), (10, "60.0"), (20, "760.0"), (30, "0.0"),
          (40, "20.0"), (1, "建筑工程甲级资质"), (100, "AcDbText")]
    P += [(0, "TEXT"), (5, hd()), (100, "AcDbEntity"), (8, "TK"), (100, "AcDbText"), (10, "330.0"), (20, "760.0"), (30, "0.0"),
          (40, "20.0"), (1, "证书编号:A133012345"), (100, "AcDbText")]
    # 旁边的设计图形（必须保留）
    P += [(0, "CIRCLE"), (5, hd()), (100, "AcDbEntity"), (8, "A-WALL"), (100, "AcDbCircle"), (10, "900.0"), (20, "300.0"), (30, "0.0"), (40, "80.0")]
    P += lw([(800, 100), (1000, 100), (1000, 200), (800, 200)], "A-WALL", closed=True)
    P += [(0, "ENDSEC"), (0, "SECTION"), (2, "BLOCKS"),
          (0, "BLOCK"), (5, hd()), (8, "0"), (2, "QM7"), (70, "0"), (10, "0.0"), (20, "0.0"), (30, "0.0"), (3, "QM7"), (1, "")]
    P += lw([(0, 0), (20, 15), (40, -5), (70, 10)])
    P += [(0, "ENDBLK"), (5, hd()), (8, "0"), (0, "ENDSEC"), (0, "EOF")]
    return P


write(os.path.join(OUT, "样例_会签栏与单位.dxf"), build_sign_table())

print("样例已生成：", OUT, "身份证", ID, "信用代码", CREDIT)
