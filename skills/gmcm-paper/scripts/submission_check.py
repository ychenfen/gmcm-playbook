#!/usr/bin/env python3
"""提交前 PDF 体检：属性、字体、残留、身份信息、目录页码、页脚页码、摘要页数。

用法:
    python3 submission_check.py 论文.pdf --identity 张三 李四 某某大学 队号
    python3 submission_check.py 论文.pdf --cover-pages 1 --json report.json

依赖 poppler 命令行工具（pdfinfo / pdffonts / pdftotext，brew install poppler）。
退出码：有 FAIL 为 1，否则为 0。
"""
import argparse
import json
import re
import subprocess
import sys

LEFTOVERS = ["错误！未找到引用源", "错误!未找到引用源", "未定义书签", "Error! Reference",
             "??", "【待", "待填写", "TODO", "XXX", "请填写"]
META_KEYS = ["Author", "Title", "Subject", "Keywords", "Creator", "Producer"]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def page_texts(pdf, n):
    return [run(["pdftotext", "-layout", "-f", str(i), "-l", str(i), pdf, "-"]) for i in range(1, n + 1)]


def squeeze(s):
    return re.sub(r"[\s  ​]", "", s)


def footer_number(text):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        return None
    m = re.fullmatch(r"-?\s*(\d{1,3})\s*-?", lines[-1])
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--identity", nargs="*", default=[], help="学校、队号、姓名等，只允许出现在封面页")
    ap.add_argument("--cover-pages", type=int, default=1, help="允许出现身份信息的前几页（官方封面）")
    ap.add_argument("--max-abstract-pages", type=int, default=2)
    ap.add_argument("--json", help="把结果另存为 JSON")
    a = ap.parse_args()

    res = []  # (level, item, detail)

    def add(level, item, detail=""):
        res.append((level, item, detail))

    import os
    if not os.path.isfile(a.pdf):
        sys.exit(f"找不到文件：{a.pdf}")
    info = run(["pdfinfo", a.pdf])
    meta = {k: "" for k in META_KEYS}
    for line in info.splitlines():
        k, _, v = line.partition(":")
        if k in meta:
            meta[k] = v.strip()
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    add("INFO", "页数", str(pages))
    if meta["Author"]:
        add("FAIL", "PDF 作者属性非空", f"Author={meta['Author']!r}，用 clean_meta.py 清理")
    for k in ("Title", "Subject", "Keywords"):
        if meta[k]:
            add("WARN", f"PDF {k} 属性非空", meta[k])
    if meta["Creator"] or meta["Producer"]:
        add("INFO", "生成工具", f"Creator={meta['Creator']!r} Producer={meta['Producer']!r}")

    fonts = run(["pdffonts", a.pdf]).splitlines()[2:]
    not_emb = [l for l in fonts if l.split() and len(l.split()) >= 5 and l.split()[-5] != "yes"]
    add("FAIL" if not_emb else "PASS", "字体全部嵌入", "; ".join(x.split()[0] for x in not_emb[:5]))

    texts = page_texts(a.pdf, pages)
    for pat in LEFTOVERS:
        hit = [i + 1 for i, t in enumerate(texts) if pat in t]
        if hit:
            add("FAIL" if pat != "??" else "WARN", f"残留文本 {pat!r}", f"PDF 第 {hit[:10]} 页")

    for s in a.identity:
        hit = [i + 1 for i, t in enumerate(texts) if s in squeeze(t) and i >= a.cover_pages]
        add("FAIL" if hit else "PASS", f"身份信息 {s!r} 不出现在封面之后", f"出现在 PDF 第 {hit} 页" if hit else "")

    printed = [footer_number(t) for t in texts]
    num_pages = [(i + 1, p) for i, p in enumerate(printed) if p is not None]
    if num_pages:
        first_pdf, first_no = num_pages[0]
        gaps = [(i, p) for i, p in num_pages if p != first_no + (i - first_pdf)]
        add("PASS" if not gaps else "WARN", "页脚页码连续",
            f"从 PDF 第 {first_pdf} 页开始编 {first_no}" + (f"；不连续处 {gaps[:5]}" if gaps else ""))
    else:
        add("WARN", "未识别到页脚页码")
    to_pdf = {p: i for i, p in num_pages}  # 印刷页码 -> PDF 页

    toc_idx = [i for i, t in enumerate(texts) if re.search(r"^\s*目\s*录\s*$", t, re.M)]
    if not toc_idx:
        add("WARN", "未找到目录页")
    else:
        start = toc_idx[0]
        abstract_pages = start - a.cover_pages
        add("PASS" if abstract_pages <= a.max_abstract_pages else "WARN", "摘要页数",
            f"{abstract_pages} 页（封面后到目录前）")
        toc_txt, j = "", start
        while j < pages and (j == start or re.search(r"\.{5,}\s*\d+\s*$", texts[j], re.M)) and j < start + 4:
            toc_txt += texts[j]
            j += 1
        entries = re.findall(r"^\s*(\S.*?)\s*[.·…]{4,}\s*(\d+)\s*$", toc_txt, re.M)
        bad = []
        for title, no in entries:
            no = int(no)
            key = squeeze(title)
            pdf_i = to_pdf.get(no)
            if pdf_i is None or key not in squeeze(texts[pdf_i - 1]):
                where = [p for p, i in to_pdf.items() if key in squeeze(texts[i - 1]) and i - 1 >= j]
                bad.append(f"{title}: 目录写 {no}，实际 {where[:3]}")
        add("PASS" if entries and not bad else ("WARN" if not entries else "FAIL"),
            f"目录页码（{len(entries)} 条）", "；".join(bad[:8]) + ("；目录可能未更新，在 WPS/Word 里右键目录→更新域" if bad else ""))

    body = "".join(texts)
    add("INFO", "人称用词", f"我们 {body.count('我们')} 处，本文 {body.count('本文')} 处（获奖论文普遍混用，仅供参考）")

    order = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3}
    for lv, item, detail in sorted(res, key=lambda r: order[r[0]]):
        print(f"[{lv}] {item}" + (f" — {detail}" if detail else ""))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump([dict(level=l, item=i, detail=d) for l, i, d in res], f, ensure_ascii=False, indent=1)
    sys.exit(1 if any(r[0] == "FAIL" for r in res) else 0)


if __name__ == "__main__":
    main()
