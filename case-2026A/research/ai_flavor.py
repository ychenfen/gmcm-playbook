# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Code，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方发布记录为准）
"""中文论文 AI 高频词密度检查。用法: python3 src/ai_flavor.py 文件.tex|.md|.txt [...]

词表 = 用户 CLAUDE.md 的禁用词 + 从 2025 A 题四篇优秀论文统计出的高频虚词。
参照：2025 优秀论文正文密度 P4=16.9、P1=25.0、P2=33.7、P3=37.1（每万字）。目标 < 16.9。
只做提示，不自动改写；"显著/有效"在给出数字或检验时可以保留。
"""
import re, sys

BANNED = ["值得注意的是", "综上所述", "不难发现", "由此可见", "基于以上分析", "具有重要意义",
          "日益增长的", "具有广泛的应用前景", "提供了新思路", "提供了新视角", "奠定了坚实",
          "突破性", "首创", "卓越", "创新性地", "充分证明", "有机统一", "让我们"]
WATCH = ["显著", "有效", "协同", "智能", "深入", "全面", "不仅", "更重要的是", "首先", "其次", "最后"]


def check(path):
    t = open(path, encoding='utf-8').read()
    t = re.sub(r'%.*', '', t)                                        # 去 LaTeX 注释
    t = re.sub(r'\\begin\{(lstlisting|verbatim|minted)\}.*?\\end\{\1\}', '', t, flags=re.S)
    n = len(re.findall(r'[\u4e00-\u9fff]', t)) or 1
    print(f"== {path}  汉字 {n}")
    total = 0
    for group, words in (("禁用", BANNED), ("留意", WATCH)):
        for w in words:
            c = t.count(w)
            if c:
                total += c
                lines = [i + 1 for i, l in enumerate(t.split('\n')) if w in l][:6]
                print(f"  [{group}] {w:<8} {c:>3} 次  行 {lines}")
    d = total / n * 1e4
    verdict = "达标" if d < 16.9 else "超过 P4 基准，需要改"
    print(f"  密度 {d:.1f}/万字  ({verdict})")


if __name__ == '__main__':
    for p in sys.argv[1:]:
        check(p)
