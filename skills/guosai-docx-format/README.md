# guosai-docx-format 本地使用说明

把一份 pandoc 生成的中文学术 docx 一键转成全国大学生统计建模大赛格式。

## 安装

1. 解压本 zip 到任意目录，比如 `~/guosai-docx-format/`
2. 确保你已经有 Anthropic 的 docx skill（提供 `unpack.py`、`pack.py`）。放在以下任一位置即可自动识别：
   - `/mnt/skills/public/docx/scripts/office/`
   - `~/docx-skill/scripts/office/`
   - `/opt/skills/docx/scripts/office/`
3. Python 3.9+，无第三方依赖

## 使用

```bash
python3 ~/guosai-docx-format/scripts/apply_guosai_format.py \
    你的论文.docx \
    输出_国赛格式.docx
```

成功的最后一行会输出 `✅ 校验通过`。

## 可选参数

- `--skip-pagebreak` 不在参考文献/附录前加分页符
- `--skip-ref-number` 不给参考文献加 `[1] [2]` 序号

## 一个提醒

生成的 docx 在 Word 里打开后，**按 F9 或右键目录区 → 更新域**，目录才会自动填充。这是 Word TOC 域的标准行为。

## 详细说明

见 `SKILL.md`。
