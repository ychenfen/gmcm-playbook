#!/usr/bin/env python3
"""队友 Word/WPS 稿的小修工具，全部另存新文件。

    python3 docx_tools.py stats 论文.docx                 # 公式/图/表/批注数、我们/本文、作者属性
    python3 docx_tools.py toc-break 论文.docx -o 新.docx   # 目录前插分页符，目录单独成页
    python3 docx_tools.py strip-comments 论文.docx -o 新.docx  # 删除全部批注（先确认批注都处理完）

改完用 stats 对比前后：公式数、图片数、表格数应不变。目录页码要在 WPS/Word 里"更新域"。
"""
import argparse
import copy
import sys

from docx import Document
from docx.oxml.ns import qn

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def stats(path):
    d = Document(path)
    body = d.element.body
    text = "\n".join(p.text for p in d.paragraphs)
    for t in d.tables:
        for r in t.rows:
            for c in r.cells:
                text += "\n" + c.text
    comments = 0
    for rel in d.part.rels.values():
        if rel.reltype.endswith("/comments"):
            comments = len(rel.target_part.element.findall(qn("w:comment")))
    cp = d.core_properties
    return {
        "段落": len(d.paragraphs),
        "公式": len(body.findall(f".//{{{M_NS}}}oMath")),
        "图片": len(body.findall(".//" + qn("w:drawing"))),
        "表格": len(body.findall(".//" + qn("w:tbl"))),
        "批注": comments,
        "目录域": len(body.findall(".//" + qn("w:sdt"))),
        "我们": text.count("我们"),
        "本文": text.count("本文"),
        "作者": cp.author,
        "最后修改者": cp.last_modified_by,
    }


def is_page_break_para(p):
    # 只认段内的分页符；上一段的 pageBreakBefore 是"在它自己前面分页"，不算
    return any(br.get(qn("w:type")) == "page" for br in p.iter(qn("w:br")))


def toc_break(src, dst):
    d = Document(src)
    body = d.element.body
    sdts = [e for e in body if e.tag == qn("w:sdt") and
            e.find(".//" + qn("w:docPartGallery")) is not None and
            "Table of Contents" in (e.find(".//" + qn("w:docPartGallery")).get(qn("w:val")) or "")]
    if not sdts:
        sys.exit("没找到 Word 目录域（w:sdt Table of Contents）；手工目录请在 WPS 里插分页符")
    toc = sdts[0]
    prev = toc.getprevious()
    if prev is not None and prev.tag == qn("w:p") and is_page_break_para(prev):
        print("目录前已有分页，未改动")
    else:
        p = body.makeelement(qn("w:p"), {})
        r = p.makeelement(qn("w:r"), {})
        br = r.makeelement(qn("w:br"), {qn("w:type"): "page"})
        r.append(br)
        p.append(r)
        toc.addprevious(p)
        print("已在目录前插入分页符")
    d.save(dst)


def strip_comments(src, dst):
    d = Document(src)
    body = d.element.body
    n = 0
    for tag in ("w:commentRangeStart", "w:commentRangeEnd"):
        for e in list(body.iter(qn(tag))):
            e.getparent().remove(e)
            n += 1
    for ref in list(body.iter(qn("w:commentReference"))):
        run = ref.getparent()
        run.remove(ref)
        if run.tag == qn("w:r") and not [c for c in run if c.tag != qn("w:rPr")]:
            run.getparent().remove(run)
        n += 1
    for rid, rel in list(d.part.rels.items()):
        if rel.reltype.endswith("/comments") or rel.reltype.endswith("/commentsExtended") \
                or rel.reltype.endswith("/commentsIds") or rel.reltype.endswith("/people"):
            d.part.drop_rel(rid)
    d.save(dst)
    print(f"已删除批注锚点 {n} 个")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stats", "toc-break", "strip-comments"])
    ap.add_argument("docx")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    if a.cmd == "stats":
        for k, v in stats(a.docx).items():
            print(f"{k}: {v}")
        return
    if not a.output or a.output == a.docx:
        sys.exit("请用 -o 指定新文件名，不覆盖原件")
    before = stats(a.docx)
    (toc_break if a.cmd == "toc-break" else strip_comments)(a.docx, a.output)
    after = stats(a.output)
    for k in ("公式", "图片", "表格"):
        if before[k] != after[k]:
            sys.exit(f"{k}数量变了：{before[k]} -> {after[k]}，请检查")
    print("公式/图片/表格数量未变")


if __name__ == "__main__":
    main()
