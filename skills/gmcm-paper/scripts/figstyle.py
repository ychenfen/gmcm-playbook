# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""论文作图统一风格。用法：在自己的作图脚本开头

    import sys; sys.path.insert(0, '<本文件所在目录>')
    from figstyle import plt, C, GRAY, FULL, HALF, save, end_label

之后照常用 matplotlib 画图，最后 save(fig, '输出目录/图名') 同时导出 PDF（插论文）和 PNG（预览）。

约定：
- 西文和数字 Times New Roman，中文宋体；自动识别 Mac / Windows / Linux 的字体，找不到时给出提示。
- 宽度按 A4 版心：通栏 FULL=6.0 英寸，半栏 HALF=2.9 英寸。LaTeX 里用 width=\\textwidth 或 0.48\\textwidth 插入，
  图里的字号就和正文小五号接近，不会被缩放得看不清。
- 颜色按固定顺序取 C[0], C[1], ...（蓝、橙、青、黄、粉、紫），已用色盲模拟检查过相邻可分。
  青、黄、粉在白底上对比度不到 3:1，用到它们时必须同时用不同标记形状或直接标注文字。
  对照组/基线一律用 GRAY，本文方法用 C[0]，让读者一眼看出主角。
- 不画双纵轴、不画 3D 饼图、不画雷达图；量纲不同就分子图。
"""
import os, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

C = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#4a3aa7']
GRAY, GRAY_L = '#9a9892', '#cfcdc6'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3de'
BLUES = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
MARKERS = ['o', 's', '^', 'D', 'v', 'P']
FULL, HALF = 6.0, 2.9

_CANDIDATES = {
    'latin': [('/System/Library/Fonts/Supplemental/Times New Roman.ttf', 'Times New Roman'),
              ('C:/Windows/Fonts/times.ttf', 'Times New Roman'),
              ('/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf', 'Times New Roman')],
    'cjk': [('/System/Library/Fonts/Supplemental/Songti.ttc', 'Songti SC'),
            ('C:/Windows/Fonts/simsun.ttc', 'SimSun'),
            ('/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc', 'Noto Serif CJK SC'),
            ('/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc', 'Noto Serif CJK SC')],
}


def _songti_regular():
    """Mac 的 Songti.ttc 第一个字重是 Black（特粗），matplotlib 只读第一个。用 fontTools 把常规体抽出来缓存到本机。"""
    src = '/System/Library/Fonts/Supplemental/Songti.ttc'
    dst = os.path.join(os.path.expanduser('~'), '.cache', 'figstyle', 'SongtiSC-Regular.ttf')
    if os.path.exists(dst) or not os.path.exists(src):
        return dst if os.path.exists(dst) else None
    try:
        from fontTools.ttLib import TTCollection
        for f in TTCollection(src).fonts:
            if f['name'].getDebugName(1) == 'Songti SC' and f['name'].getDebugName(2) == 'Regular':
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                f.save(dst)
                return dst
    except ImportError:
        print('[figstyle] 未安装 fontTools（pip install fonttools），Mac 上中文会用特粗宋体。', file=sys.stderr)
    return None


def _pick(kind):
    if kind == 'cjk':
        reg = _songti_regular()
        if reg:
            font_manager.fontManager.addfont(reg)
            return font_manager.FontProperties(fname=reg).get_name()
    for path, name in _CANDIDATES[kind]:
        if os.path.exists(path):
            try:
                font_manager.fontManager.addfont(path)
                return name
            except Exception:
                continue
    return None


_latin, _cjk = _pick('latin'), _pick('cjk')
if not _cjk:
    print('[figstyle] 没找到宋体，中文可能显示成方框。请在 _CANDIDATES 里加上本机中文字体路径。', file=sys.stderr)

plt.rcParams.update({
    'font.family': [f for f in (_latin, _cjk) if f] or ['DejaVu Sans'],
    'mathtext.fontset': 'stix', 'axes.unicode_minus': False, 'pdf.fonttype': 42,
    'font.size': 9, 'axes.titlesize': 9.5, 'axes.labelsize': 9, 'xtick.labelsize': 8.5, 'ytick.labelsize': 8.5,
    'legend.fontsize': 8.5, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2, 'ytick.color': INK2,
    'axes.linewidth': 0.7, 'xtick.major.width': 0.7, 'ytick.major.width': 0.7, 'xtick.major.size': 2.5,
    'ytick.major.size': 2.5, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True,
    'axes.grid.axis': 'y', 'axes.axisbelow': True, 'grid.color': GRID, 'grid.linewidth': 0.5,
    'legend.frameon': False, 'lines.linewidth': 1.6, 'lines.markersize': 4.5, 'figure.dpi': 150,
    'savefig.bbox': 'tight', 'savefig.pad_inches': 0.03, 'axes.titlelocation': 'left', 'axes.titlepad': 5,
})


def save(fig, path_no_ext, png_dpi=220):
    """导出 PDF（矢量，插进论文）和 PNG（预览、放 Word）。"""
    d = os.path.dirname(path_no_ext)
    if d:
        os.makedirs(d, exist_ok=True)
    fig.savefig(path_no_ext + '.pdf')
    fig.savefig(path_no_ext + '.png', dpi=png_dpi)
    plt.close(fig)
    print('  写出', path_no_ext + '.pdf / .png')


def end_label(ax, x, y, text, color=INK, dy=0):
    """在折线末端直接标注系列名，代替或补充图例。"""
    ax.annotate(text, (x, y), xytext=(5, dy), textcoords='offset points', va='center', color=color, fontsize=8.5)
