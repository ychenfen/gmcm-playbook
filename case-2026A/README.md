# 案例：2026 华为杯 A 题 通用神经网络处理器下的多核调度

论文题目：共享带宽多核 NPU 的结构自适应切图调度与缓存时序分析

## 问题与方法（一段话）

输入是 100 张分块计算图，要求在 1–5 核上给出切图（每个操作属于哪个子图）和各核的子图执行顺序，并由官方评估程序模拟出 Makespan。场景 A 中每个子图是一个独立 Task，跨子图的数据都要经过 DDR；场景 B 中同核子图合并为一个 Task，跨核依赖另加 500 周期同步；问题三在场景 B 上再加共享只读 L2 Cache。方法是：先按连通结构分类，再用三种构造（分量装箱与拓扑区间切分 LPT(α)、层带 × 核划分 BAND(W)、通信感知表调度与相位构造 PHASE(λ)）在参数网格上逐用例选优，然后做成组合并、局部搜索、问题二与问题三交叉复评和核数补齐，最后由评估程序裁决。论文证明了 4 个命题：路径下界、强 NP 难、三种构造的无环性、Q_B ≤ Q_A。

## 结果

| | 2 核 | 3 核 | 4 核 | 5 核 |
|---|---|---|---|---|
| 问题一 平均加速比 | 1.85 | 2.55 | 3.16 | 3.67 |
| 问题二 平均加速比 | 1.98 | 2.78 | 3.43 | 3.98 |
| 问题三 只读 Cache | 1.98 | 2.78 | 3.47 | 4.05 |

问题三同核数缓存加速比从 1 核的 1.001 升到 5 核的 1.020，单例最高 1.343。

## 目录

| 路径 | 内容 |
|---|---|
| `solution/` | 附件程序：`solve.py`（按题目附录 B 的输入输出格式）、`reproduce.py`、`nmcs/`（三种构造）、`expected.csv`。最终方案文件 `plans/` 未放入仓库 |
| `research/` | 实验与流水线：刻画（`characterize.py`、`connectivity.py`）、下界（`ideal_bound.py`、`ideal_sync.py`）、算法（`algos*.py`）、扫描（`sweep*.py`）、后处理（`coarsen*.py`、`localsearch.py`、`crosseval.py`、`crossfinal.py`、`monotone.py`）、冻结（`finalize.py`、`verify_delivery.py`）、论文数字（`paper_numbers.py`、`numbers_tex.py`、`appendix_tex.py`）、作图（`make_figures.py`、`extra_figures.py`）、Word 转换（`make_docx.py`）、文本检查（`paper_lint.py`、`ai_flavor.py`） |
| `paper/tex/` | LaTeX 源码（GMCMthesis 2026 模板）：`main.tex`、`sections/`、`tables/`、`tikz/`、`numbers.tex`（由脚本生成，正文用 `\V{键}` 引用） |
| `paper/fig/` | 数据图（PDF + PNG），`PROVENANCE.md` 记录每张图的数据来源 |
| `paper/WORKFLOW.md` | 写作与交付工作流、每节质量门槛 |
| `paper/lessons_from_2025A.md` | 2025 年 A 题四篇优秀论文拆解 |
| `paper/formulation.md` | 模型形式化草稿 |

## 复现须知

需要官方赛题材料包（`code/`、`data/`、`config.txt`），它不在仓库里。脚本里的路径以当时的项目根目录 `A_work/` 为基准，材料包在 `A_work/pkg/`。编译论文：进入 `paper/tex/` 执行 `latexmk -xelatex main.tex`，图的路径是 `../fig/`。

注意：最终提交的论文是队友在 WPS 里改写过的版本，这里的 LaTeX 源码是改写之前的版本，措辞和最终稿不完全相同，数字一致。
