# 来源与初始范围

初始盘点日期：2026-10-16，Asia/Singapore。

科学技能来源仓库：https://github.com/K-Dense-AI/scientific-agent-skills

本机基线提交：`49c6e97`。该提交下 3 个已有 skill 的 `SKILL.md` 被本地修改：`literature-review`、`markitdown`、`pdf`，并新增匹配说明。

该仓库有 5 个未跟踪的 skill 目录：`data-pro-jv`、`data-pro-thickness-calibration`、`endnote-summary`、`reverse-engineer-anything`、`web-automation`。未跟踪意味着本地新增，不代表已核实全部内容的原创归属。

`matlab_draw` 来自独立本地仓库，初始提交为 `6f2a405`。本版本库从当前安装内容建立统一快照，不改变上述原仓库的分支或远程地址。

保留科学技能来源仓库的 MIT 许可。各 skill 自带的许可与归属说明继续适用。现有 `endnote-summary` 测试随同保存；依赖清单仅作来源上下文留存，不自动安装其中的软件包。

`data-pro-jv` v2.4 保存当前实际安装版本，包含同样品同点按 PCE/FF 择优、各筛选表底部参数均值及配套脚本；`tests/data-pro-jv` 保存本次逐点择优和四项筛选的 28 项回归测试。测试使用合成输入，不含实验数据或生成的工作簿。
