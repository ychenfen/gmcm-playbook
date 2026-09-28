# 附件：多核切图与调度程序

环境：Python 3.10 及以上，只用标准库。需要赛题官方材料包（含 `code/` 与 `data/`）。输入计算图格式见赛题附录 B.3，输出方案格式见附录 B.5。

## 目录

| 路径 | 内容 |
|---|---|
| `solve.py` | 求解入口：给定计算图与核数，输出附录 B.5 格式的方案文件 `<case>_multicore_res.json`（顶层只有 `node_to_subgraph` 与 `core_schedules`） |
| `reproduce.py` | 复现入口：把 `plans/` 中的最终方案交给官方评估程序，与 `expected.csv`（论文附录数字）逐项比对 |
| `nmcs/` | 三种构造算法：分量装箱与拓扑区间切分、层带×核划分、通信感知表调度与相位构造 |
| `plans/` | 论文最终方案，`p{问题}_k{核数}_{用例}.json`，共 1,400 个 |
| `expected.csv` | 论文附录中的 Makespan、总额外搬运量与命中率 |
| `research_code/` | 完整实验代码（参数扫描、成组合并、局部搜索、交叉复评、核数补齐、终版复评、统计与作图） |

## 用法

求解（问题 1/2/3 通用），在官方材料包根目录下执行，`<附件>` 为本目录：

```
python <附件>/solve.py data/case_001.json -n 4 --problem 1
python code/multicore_cut_evaluate_problem_1.py data/case_001.json --config data/config.txt
```

第一条命令与官方示例生成器的约定相同：配置默认取 `data/config.txt`，方案默认写到 `data/case_001_multicore_res.json`，第二条命令省略方案参数即可直接评估。其他选项：`--config` 指定配置文件，`-o` 指定方案文件路径，`--pkg` 在别的目录运行时指定材料包根目录，`-j` 并行评估进程数，`--fewer-cores` 同时尝试少用核心并补空核。求解过程中每个候选的评估值另存为 `<case>_p<问题>_k<核数>_report.json`。

赛题附录 B.7 的最小示例可直接验证：`python <附件>/solve.py minimal_graph.json -n 2 --problem 1 --config data/config.txt` 输出 `{"node_to_subgraph": {"11": 0}, "core_schedules": [[0], []]}`，三个问题的评估结果均为 Makespan = 6、新增搬运量 0。

复现论文附录（全部 1,400 项约需数小时，可按问题、用例、核数分批）：

```
python <附件>/reproduce.py            # 在材料包根目录下执行，或用 --pkg 指定
python reproduce.py --pkg <pkg> --problems 1 --cores 4 --cases case_001 case_002
```

## 与论文结果的关系

`solve.py` 使用代表性参数与成组合并，单个用例一般在数分钟内完成。论文的最终方案还经过更大的参数网格、局部搜索（随机种子与时间预算见 `research_code/ls_driver2.py`）、问题二与问题三之间的交叉复评和核数补齐，因此 `solve.py` 的结果可能略逊于附录。附录中的每个数字都可由 `reproduce.py` 从最终方案文件精确复现。

## AI 工具使用

全部程序文件开头均按竞赛规定注明了人工智能工具的使用情况。
