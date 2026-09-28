#!/usr/bin/env python3
"""清空 DOCX / PDF 的作者等身份属性，另存为新文件（不覆盖原件）。

用法:
    python3 clean_meta.py 论文.docx            # -> 论文_clean.docx
    python3 clean_meta.py 论文.pdf -o 最终.pdf

DOCX：清 core.xml 的作者、最后修改者、标题、主题、关键词、类别、备注，app.xml 的 Company/Manager。
PDF：清 Info 字典与 XMP，并以 garbage=4 整体重写，旧属性不会残留在增量更新里（需要 PyMuPDF）。
WPS 导出的 PDF 常把 WPS 账号昵称写进 Author，属于身份信息，提交前必须清。
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile

CORE_FIELDS = ["dc:creator", "cp:lastModifiedBy", "dc:title", "dc:subject", "cp:keywords",
               "cp:category", "dc:description", "cp:contentStatus"]
APP_FIELDS = ["Company", "Manager"]


def blank_xml(xml, tags):
    for t in tags:
        xml = re.sub(rf"(<{t}\b[^>]*>)(.*?)(</{t}>)", r"\1\3", xml, flags=re.S)
    return xml


def clean_docx(src, dst):
    tmp = tempfile.mktemp(suffix=".docx")
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/core.xml":
                data = blank_xml(data.decode("utf-8"), CORE_FIELDS).encode("utf-8")
            elif item.filename == "docProps/app.xml":
                data = blank_xml(data.decode("utf-8"), APP_FIELDS).encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, dst)
    with zipfile.ZipFile(dst) as z:
        core = z.read("docProps/core.xml").decode("utf-8") if "docProps/core.xml" in z.namelist() else ""
    left = [t for t in ("dc:creator", "cp:lastModifiedBy") if re.search(rf"<{t}\b[^>]*>[^<]+</{t}>", core)]
    return left


def clean_pdf(src, dst):
    import fitz  # PyMuPDF
    d = fitz.open(src)
    d.set_metadata({k: "" for k in ["author", "title", "subject", "keywords", "creator", "producer"]})
    d.del_xml_metadata()
    d.save(dst, garbage=4, deflate=True)
    d.close()
    d = fitz.open(dst)
    left = [k for k, v in (d.metadata or {}).items() if v and k in ("author", "title", "subject", "keywords")]
    d.close()
    return left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    root, ext = os.path.splitext(a.file)
    dst = a.output or f"{root}_clean{ext}"
    if os.path.abspath(dst) == os.path.abspath(a.file):
        sys.exit("输出路径不能与原件相同")
    ext = ext.lower()
    if ext == ".docx":
        left = clean_docx(a.file, dst)
    elif ext == ".pdf":
        left = clean_pdf(a.file, dst)
    else:
        sys.exit("只支持 .docx / .pdf")
    print(f"已写出 {dst}" + (f"；仍有残留字段 {left}" if left else "；作者等属性已清空"))
    sys.exit(1 if left else 0)


if __name__ == "__main__":
    main()
