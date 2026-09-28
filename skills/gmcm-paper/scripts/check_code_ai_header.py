# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""检查程序文件开头是否有附件4 第5条要求的 AI 辅助注释。

用法:
  python3 check_code_ai_header.py 代码目录 [更多目录或文件 ...]
      只检查，不改文件。列出缺注释或注释缺项的文件。
  python3 check_code_ai_header.py 代码目录 --add "工具名称" "版本/型号" "开发机构" "发布日期"
      给缺注释的文件在开头补上注释（保留 #! 和编码声明行）。改之前会把原文件存成 同名.bak。
      已有注释的文件不动。.ipynb 只报告，不自动改，请手动在第一个代码单元加注释。

判定：文件前 15 行内出现「人工智能工具辅助」，并且写了名称、版本/型号、开发机构、发布日期四项。
"""
import os, re, sys, json, shutil

EXT_COMMENT = {'.py': '#', '.r': '#', '.jl': '#', '.sh': '#', '.m': '%', '.c': '//', '.cpp': '//',
               '.h': '//', '.hpp': '//', '.java': '//', '.js': '//', '.ts': '//', '.go': '//', '.rs': '//',
               '.cs': '//', '.scala': '//', '.sql': '--', '.lua': '--', '.ipynb': None}
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.ipynb_checkpoints', 'venv', '.venv', 'env', 'site-packages'}
FIELDS = {'名称': r'工具[:：]|名称', '版本/型号': r'版本|型号', '开发机构': r'机构|公司', '发布日期': r'日期'}


def head_text(path):
    if path.endswith('.ipynb'):
        try:
            nb = json.load(open(path, encoding='utf-8'))
            for c in nb.get('cells', []):
                if c.get('cell_type') == 'code':
                    return ''.join(c.get('source', []))
        except Exception:
            return ''
        return ''
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            return ''.join(f.readline() for _ in range(15))
    except Exception:
        return ''


def status(path):
    h = head_text(path)
    if not re.search(r'人工智能工具辅助|人工智能工具的辅助', h):
        return '缺注释'
    miss = [k for k, pat in FIELDS.items() if not re.search(pat, h)]
    return ('缺项：' + '、'.join(miss)) if miss else 'OK'


def files_under(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, fs in os.walk(p):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in sorted(fs):
                if os.path.splitext(f)[1].lower() in EXT_COMMENT:
                    yield os.path.join(root, f)


def add_header(path, name, ver, org, date):
    c = EXT_COMMENT[os.path.splitext(path)[1].lower()]
    header = (f'{c} 本程序及代码是在人工智能工具辅助下完成的。\n'
              f'{c} 人工智能工具名称：{name}，版本/型号：{ver}，开发机构/公司：{org}，版本发布日期：{date}\n')
    raw = open(path, encoding='utf-8', errors='surrogateescape').read()
    lines = raw.splitlines(keepends=True)
    keep = 0
    while keep < len(lines) and keep < 2 and (lines[keep].startswith('#!') or re.match(r'#.*coding[:=]', lines[keep])):
        keep += 1
    shutil.copy2(path, path + '.bak')
    open(path, 'w', encoding='utf-8', errors='surrogateescape').write(''.join(lines[:keep]) + header + ''.join(lines[keep:]))


def main(argv):
    add = None
    if '--add' in argv:
        i = argv.index('--add')
        add, argv = argv[i + 1:i + 5], argv[:i]
        if len(add) != 4:
            print('--add 需要四个参数：工具名称 版本/型号 开发机构 发布日期'); return 2
    if not argv:
        print(__doc__); return 2
    bad, total, fixed = [], 0, 0
    for f in files_under(argv):
        total += 1
        s = status(f)
        if s == 'OK':
            continue
        if add and s == '缺注释' and not f.endswith('.ipynb'):
            add_header(f, *add); fixed += 1
            print(f'  已补注释  {f}（原文件存为 .bak）')
            continue
        bad.append((f, s))
    for f, s in bad:
        print(f'  [{s}] {f}')
    print(f'\n共检查 {total} 个程序文件，补注释 {fixed} 个，仍有问题 {len(bad)} 个'
          + ('（附件4 第5条：缺注释视为违规，会被取消评奖资格）' if bad else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
