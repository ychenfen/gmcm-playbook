# 图表数据版本

本组图对应 2026-09-23 晚间计算结束、完整回收后，于 21:42:15 完成官方复评的最终结果。独立验收要求与当前候选池一致，未处理新候选为 0。基准为官方单核；P1/P2 的 k=1 按题目定义设为 1，P3 图中保留官方 P2/P3 评估所得的实际 1 核比值，不能混用这两个口径。

## 本轮交付数据

- `bounds_gap`、`algo_compare` 中的组合选优曲线、`algo_wins`、`speedup_p12`、`speedup_heatmap`、`p3_compare` 使用本轮 `deliverables/evals/`。
- `miss_breakdown` 使用与这批 P3 4 核方案逐文件哈希一致的 `deliverables/analysis/cache_diag_k4.json`；100 例均重评通过。不能继续使用旧 `runs/cache_diag_k4.json` 当当前最优方案的诊断。
- 完整选择在 `deliverables/selected_tasks.json`，数值与附录校验在 `deliverables/verification.json`；`pending_current_tasks` 为空。1,400 主结果与 500 配对已验证，本轮新评 183、复用 1,717。
- 缓存诊断首轮 99/100；case_021 的官方评估子进程曾非零退出，原始错误快照保存在 `archives/cache_diag_20260923_2145_failed.json`。单独复跑成功后，100/100 的 makespan、方案哈希与最终交付一致；原错误消息被旧诊断包装截短，未确定首次失败根因，不能宣称从未发生失败。
- 最终 summary SHA-256：`5a24e1feb673d1059adc9c3766b2fa951c989ba9570c498d0df46613758fc549`。

## 保留的历史与静态对照

- `dataset_profile` 来自原始输入结构。
- `size_threshold`、`traffic_AB`、`spill_B`、`cache_vs_ddr` 来自扫描方案配对，`algo_compare` 的三条基础算法曲线来自各算法扫描结果；不是最终组合方案的消融。
- `timeline_AB`、`lockstep` 保留前期冻结方案的机理对照，来源保存在 `runs/fig_data/`；图注明确它们并非当前最优方案。
- `cache_sensitivity` 保留前期扫描方案上的参数敏感性实验，未对新的合并/交叉复评方案重跑；不能推断新方案已普遍饱和。
- `framework` 为原有技术路线图，本轮未修改。

图表检查（2026-09-23 21:48）：15 张数据图重新生成，保留 framework 共 16 个 PDF；逐一验证单页、检测到的字体全部嵌入，报告为 `deliverables/analysis/pdf_validation.json`。从本轮 PDF 重新渲染 speedup_p12、p3_compare、algo_wins、miss_breakdown 并逐张目检，文字/图例/数值无裁切或重叠；四张核验图保存在 `archives/closeout_qa_20260923/`。未将其余 12 张的结构检查冒充逐张目检。

注意：来源图按最后的结果来源统计，成组合并/交叉复评不能归入局部搜索；P3 比值为 T无L2/TCache，大于 1 表示缓存场景较快。
