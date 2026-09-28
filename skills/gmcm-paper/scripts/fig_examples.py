# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude，版本/型号：Claude Opus 5.5，开发机构：Anthropic，版本发布日期：2026 年（具体日期以 Anthropic 官方公布为准）
"""建模论文常用的 7 类图，每类一个函数，照着改成自己的数据即可。

    python3 fig_examples.py            输出到 ../作图示例/

注意：这里的数据全部是随机生成的演示数据，只用来展示画法，不能出现在论文里。
每个函数开头的注释写了这张图要回答什么问题、放在论文哪一节。
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from figstyle import plt, C, GRAY, GRAY_L, INK, INK2, BLUES, MARKERS, FULL, HALF, save, end_label
from matplotlib.colors import LinearSegmentedColormap

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '作图示例')
rng = np.random.default_rng(2026)


def fig_ladder():
    """由浅入深的证据图：模型每升级一层，误差降多少、代价多少。放在每问结果小节开头或模型对比小节。
    回答：为什么要从基础模型升级到复杂模型——每一步都要有数据支撑。"""
    stages = ['L1\n线性回归', 'L2\n加机理项', 'L3\n非线性修正', 'L4\n集成校准']
    rmse = np.array([12.4, 8.1, 5.6, 4.9])
    t = np.array([0.2, 0.9, 3.5, 11.0])
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.4), gridspec_kw={'width_ratios': [1.35, 1]})
    x = np.arange(len(stages))
    a.bar(x, rmse, width=0.56, color=[GRAY_L, BLUES[2], BLUES[3], BLUES[5]], edgecolor='white', linewidth=1)
    for i, v in enumerate(rmse):
        a.text(i, v + 0.3, f'{v:.1f}', ha='center', va='bottom', fontsize=8.5, color=INK)
        if i:                                     # 相邻两级之间写降幅
            a.text(i - 0.5, v + 0.3, f'−{(rmse[i-1]-v)/rmse[i-1]*100:.0f}%', ha='center', va='bottom',
                   fontsize=8, color=C[1])
    a.set_xticks(x); a.set_xticklabels(stages, fontsize=8)
    a.set_ylabel('测试集 RMSE'); a.set_title('(a) 逐层升级的误差', fontsize=9.5)
    a.set_ylim(0, 14.5)
    b.plot(x, t, marker='o', color=C[1])
    for i, v in enumerate(t):
        b.annotate(f'{v:g} s', (i, v), xytext=(0, 6), textcoords='offset points', ha='center', fontsize=8)
    b.set_yscale('log'); b.set_xticks(x); b.set_xticklabels(['L1', 'L2', 'L3', 'L4'])
    b.set_ylabel('求解时间 / s（对数轴）'); b.set_title('(b) 代价', fontsize=9.5); b.set_ylim(0.1, 40)
    b.set_xlim(-0.4, 3.4); b.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:g}'))
    fig.tight_layout(w_pad=2)
    save(fig, os.path.join(OUT, '图1_由浅入深_逐层升级'))


def fig_compare():
    """方法对比：本文方法 vs 强基线，多个场景。放在结果小节。
    回答：本文方法比题目给的方法、比常用方法好多少。基线用灰，本文用蓝。"""
    scen = ['场景 1', '场景 2', '场景 3', '场景 4']
    methods = [('题给方法', GRAY_L), ('贪心', GRAY), ('遗传算法', BLUES[3]), ('本文方法', C[0])]
    vals = np.array([[100, 100, 100, 100], [83, 88, 79, 91], [71, 80, 70, 84], [62, 74, 61, 77]], float)
    fig, ax = plt.subplots(figsize=(FULL, 2.5))
    w = 0.19
    x = np.arange(len(scen))
    for j, (m, col) in enumerate(methods):
        xs = x + (j - 1.5) * w
        ax.bar(xs, vals[j], width=w - 0.02, color=col, label=m, edgecolor='white', linewidth=0.8)
        if j == 3:
            for xi, v in zip(xs, vals[j]):
                ax.text(xi, v + 1.2, f'{v:.0f}', ha='center', fontsize=8, color=INK)
    ax.set_xticks(x); ax.set_xticklabels(scen)
    ax.set_ylabel('总成本（题给方法 = 100）'); ax.set_ylim(0, 112)
    ax.legend(ncol=4, loc='upper center', bbox_to_anchor=(0.5, 1.16))
    save(fig, os.path.join(OUT, '图2_方法对比'))


def fig_sensitivity():
    """单参数灵敏度：参数扫描 + 波动带 + 选定值。放在模型检验/灵敏度分析小节。
    回答：结论对参数取值稳不稳，参数怎么选。"""
    p = np.linspace(0.1, 2.0, 40)
    fig, ax = plt.subplots(figsize=(HALF * 1.45, 2.4))
    for k, (name, a0) in enumerate([('需求 +20%', 1.25), ('基准需求', 1.0), ('需求 −20%', 0.8)]):
        y = a0 * (60 + 25 * (p - 0.9) ** 2) + rng.normal(0, 0.6, p.size)
        s = 2 + 1.5 * np.abs(p - 0.9)
        ax.plot(p, y, color=C[k], marker=MARKERS[k], markevery=6, markersize=3.8)
        ax.fill_between(p, y - s, y + s, color=C[k], alpha=0.12, linewidth=0)
        end_label(ax, p[-1], y[-1], name)
    ax.axvline(0.9, color=INK2, lw=0.8, ls='--')
    ax.text(0.92, ax.get_ylim()[1] * 0.97, '选定 α = 0.9', fontsize=8, color=INK2, va='top')
    ax.set_xlabel('权重系数 α'); ax.set_ylabel('目标函数值')
    ax.set_xlim(0.1, 2.45)
    save(fig, os.path.join(OUT, '图3_单参数灵敏度'))


def fig_heatmap():
    """双参数灵敏度热力图（单色由浅到深）。回答：两个参数同时变时，好区域在哪、有多宽。"""
    a = np.linspace(0.5, 1.5, 9)
    b = np.linspace(10, 50, 9)
    Z = 100 - 30 * (a[None, :] - 1.05) ** 2 * 4 - 0.02 * (b[:, None] - 32) ** 2 + rng.normal(0, 0.4, (9, 9))
    cmap = LinearSegmentedColormap.from_list('b', BLUES)
    fig, ax = plt.subplots(figsize=(HALF * 1.4, 2.6))
    im = ax.imshow(Z, origin='lower', cmap=cmap, aspect='auto',
                   extent=[a[0] - 0.0625, a[-1] + 0.0625, b[0] - 2.5, b[-1] + 2.5])
    i, j = np.unravel_index(Z.argmax(), Z.shape)
    ax.plot(a[j], b[i], marker='*', color='white', markersize=10, markeredgecolor=INK, markeredgewidth=0.6)
    ax.annotate(f'最优 {Z.max():.1f}', (a[j], b[i]), xytext=(8, 8), textcoords='offset points', fontsize=8, color=INK)
    ax.set_xlabel('参数 a'); ax.set_ylabel('参数 b'); ax.grid(False)
    cb = fig.colorbar(im, ax=ax, shrink=0.9); cb.set_label('满意度得分'); cb.outline.set_linewidth(0.5)
    save(fig, os.path.join(OUT, '图4_双参数热力图'))


def fig_convergence():
    """收敛曲线 + 下界。回答：算法收敛了没有、离下界还差多少（有下界才能说“接近最优”）。"""
    it = np.arange(1, 501)
    lb = 1000
    fig, ax = plt.subplots(figsize=(HALF * 1.45, 2.4))
    for k, (name, rate, final) in enumerate([('遗传算法', 60, 1085), ('模拟退火', 120, 1060), ('本文算法', 35, 1021)]):
        y = final + (1600 - final) * np.exp(-it / rate) + rng.normal(0, 2, it.size).cumsum() * 0.02
        y = np.minimum.accumulate(y)
        ax.plot(it, y, color=[GRAY, BLUES[3], C[0]][k], marker=MARKERS[k], markevery=80, markersize=3.8)
        ax.annotate(f'{name} {y[-1]:.0f}', (it[-1], y[-1]), xytext=(it[-1] + 18, [1135, 1075, 1022][k]),
                    textcoords='data', va='center', fontsize=8.5, color=INK,
                    arrowprops=dict(arrowstyle='-', color=GRAY_L, lw=0.6))
    ax.axhline(lb, color=C[1], ls='--', lw=1)
    ax.text(690, lb - 14, f'下界 {lb}', fontsize=8, color=INK2, va='top', ha='right')
    ax.set_xlabel('迭代次数'); ax.set_ylabel('目标函数值'); ax.set_xlim(0, 700); ax.set_ylim(930, 1650)
    save(fig, os.path.join(OUT, '图5_收敛曲线与下界'))


def fig_small_multiples():
    """小多图：多个对象同一坐标，逐个看拟合。回答：模型在每个样本上都好，还是只在平均意义上好。"""
    fig, axes = plt.subplots(2, 3, figsize=(FULL, 3.4), sharex=True, sharey=True)
    t = np.linspace(0, 24, 49)
    for k, ax in enumerate(axes.flat):
        base = 50 + 20 * np.sin((t - 6 - k) / 24 * 2 * np.pi) + 4 * k
        obs = base + rng.normal(0, 3, t.size)
        l1, = ax.plot(t, obs, color=GRAY, lw=0, marker='o', markersize=2.4, label='实测')
        l2, = ax.plot(t, base, color=C[0], lw=1.4, label='模型')
        r2 = 1 - ((obs - base) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()
        ax.set_title(f'站点 {k + 1}　R² = {r2:.2f}', fontsize=8.5)
        ax.set_xticks([0, 6, 12, 18, 24])
    fig.legend([l1, l2], ['实测', '模型'], ncol=2, loc='upper center', bbox_to_anchor=(0.5, 1.04))
    for ax in axes[1]: ax.set_xlabel('时刻（h）')
    for ax in axes[:, 0]: ax.set_ylabel('负荷（kW）')
    fig.tight_layout(h_pad=1.2)
    save(fig, os.path.join(OUT, '图6_小多图逐对象检验'))


def fig_pred_vs_true():
    """预测—实测散点 + 残差分布（两个子图，不用双纵轴）。回答：有没有系统偏差、误差多大。"""
    y = rng.uniform(10, 100, 200)
    yhat = y * 0.97 + 1.5 + rng.normal(0, 4, y.size)
    res = yhat - y
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 2.6), gridspec_kw={'width_ratios': [1, 1]})
    a.scatter(y, yhat, s=9, color=C[0], alpha=0.7, linewidths=0)
    a.plot([0, 110], [0, 110], color=INK2, lw=0.8, ls='--')
    a.text(100, 104, 'y = x', fontsize=8, color=INK2, ha='right')
    rmse = np.sqrt((res ** 2).mean())
    a.text(8, 100, f'RMSE = {rmse:.2f}\nR² = {1 - (res**2).sum()/((y-y.mean())**2).sum():.3f}', fontsize=8.5, va='top')
    a.set_xlim(0, 110); a.set_ylim(0, 110); a.set_xlabel('实测值'); a.set_ylabel('预测值'); a.set_title('(a) 预测—实测', fontsize=9.5)
    a.grid(True, axis='both')
    b.hist(res, bins=24, color=C[0], edgecolor='white', linewidth=0.6)
    b.axvline(res.mean(), color=C[1], lw=1, ls='--')
    b.text(0.97, 0.95, f'残差均值 {res.mean():+.2f}\n标准差 {res.std():.2f}', transform=b.transAxes, ha='right', va='top', fontsize=8, color=INK2)
    b.set_xlabel('残差（预测 − 实测）'); b.set_ylabel('样本数'); b.set_title('(b) 残差分布', fontsize=9.5)
    fig.tight_layout(w_pad=2)
    save(fig, os.path.join(OUT, '图7_预测实测与残差'))


if __name__ == '__main__':
    for f in (fig_ladder, fig_compare, fig_sensitivity, fig_heatmap, fig_convergence, fig_small_multiples, fig_pred_vs_true):
        f()
