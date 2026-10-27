#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_guosai_format.py —— 主驱动，把 pandoc 生成的 docx 改造成国赛格式

用法:
    python3 apply_guosai_format.py <input.docx> <output.docx>

工作流程：
    1. 调用 docx skill 的 unpack.py 解包到临时目录
    2. 用 assets/ 里调好的样式文件覆盖 word/styles.xml, word/numbering.xml
    3. 把 footer1.xml 放进 word/ 并注册到 .rels 和 Content_Types
    4. 依次跑 6 个 step 脚本处理 document.xml
    5. sectPr 加 footerReference；在 bookmarkStart 引言前插入目录页
    6. 调 pack.py 打包、校验

要求：
    - docx skill 可访问（脚本会自动探测路径）
    - Python 3.9+，无额外第三方依赖
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
ASSETS_DIR = SKILL_DIR / "assets"


def find_docx_skill() -> Path:
    """找 docx skill 里的 unpack.py / pack.py 位置。"""
    candidates = [
        Path("/mnt/skills/public/docx/scripts/office"),
        Path.home() / "docx-skill" / "scripts" / "office",
        Path("/opt/skills/docx/scripts/office"),
    ]
    for c in candidates:
        if (c / "unpack.py").exists() and (c / "pack.py").exists():
            return c
    raise FileNotFoundError(
        "找不到 docx skill 的 unpack.py/pack.py。请安装 docx skill 或把它放到以下任一位置:\n"
        + "\n".join(f"  - {c}" for c in candidates)
    )


def register_footer(unpacked: Path):
    """在 rels 和 Content_Types.xml 中注册 footer1.xml。"""
    # 1. 复制 footer1.xml
    shutil.copy(ASSETS_DIR / "footer1.xml", unpacked / "word" / "footer1.xml")

    # 2. document.xml.rels 里加关系（如果还没有）
    rels_path = unpacked / "word" / "_rels" / "document.xml.rels"
    rels = rels_path.read_text(encoding="utf-8")
    if 'rId200' not in rels:
        rels = rels.replace(
            "</Relationships>",
            '  <Relationship Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/footer" Id="rId200" Target="footer1.xml"/>\n</Relationships>'
        )
        rels_path.write_text(rels, encoding="utf-8")

    # 3. [Content_Types].xml 里加 footer override + png/jpeg default
    ct_path = unpacked / "[Content_Types].xml"
    ct = ct_path.read_text(encoding="utf-8")
    if "footer1.xml" not in ct:
        ct = ct.replace(
            '<Override PartName="/word/footnotes.xml"',
            '<Override PartName="/word/footer1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>\n'
            '  <Override PartName="/word/footnotes.xml"'
        )
    if 'Extension="png"' not in ct:
        ct = ct.replace(
            '<Default Extension="odttf"',
            '<Default Extension="png" ContentType="image/png"/>\n'
            '  <Default Extension="jpeg" ContentType="image/jpeg"/>\n'
            '  <Default Extension="odttf"'
        )
    ct_path.write_text(ct, encoding="utf-8")


def replace_styles(unpacked: Path):
    """用 assets 里调好的 styles.xml / numbering.xml 覆盖。"""
    shutil.copy(ASSETS_DIR / "styles.xml", unpacked / "word" / "styles.xml")
    shutil.copy(ASSETS_DIR / "numbering.xml", unpacked / "word" / "numbering.xml")


def add_footer_reference(unpacked: Path):
    """在 sectPr 里加 footerReference（必须在 footnotePr 之前）。"""
    doc_path = unpacked / "word" / "document.xml"
    content = doc_path.read_text(encoding="utf-8")
    if "footerReference" in content:
        return
    content = content.replace(
        '<w:sectPr>\n      <w:footnotePr>',
        '<w:sectPr>\n      <w:footerReference w:type="default" r:id="rId200"/>\n'
        '      <w:footnotePr>'
    )
    doc_path.write_text(content, encoding="utf-8")


def run_step(step_script: str, unpacked: Path):
    """运行单个 step 脚本。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / step_script), str(unpacked)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERR: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)
    print(result.stdout.rstrip())


def main():
    ap = argparse.ArgumentParser(description="把 pandoc 生成的 docx 改造成国赛格式")
    ap.add_argument("input", help="输入的 .docx 文件")
    ap.add_argument("output", help="输出的 .docx 文件")
    ap.add_argument(
        "--skip-pagebreak", action="store_true",
        help="不在参考文献/附录前加分页符（默认加）"
    )
    ap.add_argument(
        "--skip-ref-number", action="store_true",
        help="不给参考文献加 [N] 序号"
    )
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    if not input_path.exists():
        print(f"错误: 找不到文件 {input_path}", file=sys.stderr)
        sys.exit(1)

    docx_office = find_docx_skill()
    unpack_py = docx_office / "unpack.py"
    pack_py = docx_office / "pack.py"

    with tempfile.TemporaryDirectory(prefix="guosai_") as tmp:
        unpacked = Path(tmp) / "unpacked"

        print("[1/12] 解包 " + input_path.name)
        subprocess.run([sys.executable, str(unpack_py), str(input_path), str(unpacked)],
                       check=True)

        print("[2/12] 替换样式和编号配置")
        replace_styles(unpacked)

        print("[3/12] 注册页脚 footer1.xml")
        register_footer(unpacked)

        print("[4/12] 修复标题样式和编号")
        run_step("step1_fix_headings.py", unpacked)

        print("[5/12] 修复公式下标/上标")
        run_step("step2_fix_math.py", unpacked)

        print("[6/12] 图表标题加编号前缀")
        run_step("step3_caption_prefix.py", unpacked)

        print("[7/12] 表格行防跨页")
        run_step("step4_cantsplit.py", unpacked)

        if not args.skip_pagebreak:
            print("[8/12] 参考文献/附录另起一页")
            run_step("step5_pagebreak.py", unpacked)

        if not args.skip_ref_number:
            print("[9/12] 参考文献加 [N] 序号")
            run_step("step6_ref_number.py", unpacked)

        print("[10/12] 重组封面区（赛事抬头/主标题/副标题/摘要）")
        run_step("step0_rebuild_cover.py", unpacked)

        print("[11/12] 插入目录页")
        run_step("step7_insert_toc.py", unpacked)

        print("[12/12] sectPr 挂 footerReference")
        add_footer_reference(unpacked)

        print(f"\n打包输出到 {output_path}")
        result = subprocess.run(
            [sys.executable, str(pack_py), str(unpacked), str(output_path),
             "--original", str(input_path)],
            capture_output=True, text=True
        )
        print(result.stdout)
        if "All validations PASSED" in result.stdout:
            print("✅ 校验通过")
        else:
            print("⚠️ 校验有警告，请检查输出:")
            print(result.stderr)


if __name__ == "__main__":
    main()
