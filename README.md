# gmcm-playbook

华为杯中国研究生数学建模竞赛的可复用打法，整理自 2026 年第二十三届 A 题的完整参赛过程。

| 目录 | 内容 |
|---|---|
| `LESSONS.md` | 复盘：真正产生价值的事、走过的弯路、工程坑、下次开局清单 |
| `skills/gmcm-paper/` | Claude Code skill：全流程打法（`SKILL.md`）、写作与合规参考、检查与清理脚本、TikZ 过程图模板 |
| `skills/guosai-docx-format/` | 全国大学生统计建模大赛的 DOCX 排版技能及脚本、样式资源；不要套用到其他赛事 |
| `skills/mcm-humanizer/` | MCM/ICM 英文论文表达润色；保留事实与技术含义，不保证任何检测器结果 |
| `skills/competition-model-quality-freeze/` | 数模实验验证、结果冻结、复现及交付门槛检查 |
| `skills/cumcm-delivery-compliance/` | CUMCM 风格论文、AI 使用说明、代码附录及提交包合规检查 |
| `skills/MODELING_SKILLS_MANIFEST.json` | 2026-10-27 本地五套技能快照的逐文件大小和 SHA256 |
| `case-2026A/` | 案例：附件程序、实验与论文流水线代码、LaTeX 论文源码、数据图 |

## 安装 skill

```bash
cp -R skills/gmcm-paper ~/.claude/skills/
```

以后在 Claude Code 里提到"华为杯""研究生数学建模""提交包""AI 使用说明"等关键词，就会自动加载这个 skill。也可以直接说"用 gmcm-paper skill"。

另外四套技能也保存在 `skills/<技能名>/`，可按需复制到对应工具的个人 skills 目录；本次归档不修改本机已安装技能。两套交付检查技能保留原始 `disable-model-invocation: true` 设置，使用时按工具支持的方式手动调用。每套技能的适用赛事、依赖与使用方法以其 `SKILL.md` 为准，不能混用赛事格式。

五套技能包含各自现有的参考资料、脚本和模板。此次快照排除了缓存、`.DS_Store`、Python 字节码和旧 `.bak` 文件；保留其他原件，未将私人聊天、账号配置、项目原始数据或整个记忆目录纳入归档。部分原始技能使用机器相关路径或外部项目引用，换机器使用前需核对，不代表已安装其依赖或验证全部建模流程。

## 下次比赛怎么开始

1. 先读 `LESSONS.md` 的第四节"下次开局就做的事"。
2. 按 `skills/gmcm-paper/SKILL.md` 的时间线推进，每个阶段过验收门槛。
3. 提交前：
   ```bash
   python3 skills/gmcm-paper/scripts/clean_meta.py 论文.pdf -o 队号.pdf
   python3 skills/gmcm-paper/scripts/submission_check.py 队号.pdf --identity 学校 队号 姓名...
   ```

## 不在仓库里的东西

- 官方赛题材料包、计算图数据、官方评估程序（组委会版权，每年不同）
- 1,400 个最终方案文件（约 79 MB）、实验 runs（约 750 MB）、论文最终 PDF/Word（含封面身份信息）
- 这些在本机项目目录和独立恢复副本里，路径见本机 `MANIFEST.md`

脚本依赖：Python 3.9+、python-docx、PyMuPDF（`clean_meta.py` 处理 PDF 时用）、poppler（`pdfinfo`/`pdffonts`/`pdftotext`）。
