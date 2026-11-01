# 来源与初始范围

初始盘点日期：2026-10-16，Asia/Singapore。

科学技能来源仓库：https://github.com/K-Dense-AI/scientific-agent-skills

本机基线提交：`49c6e97`。该提交下 3 个已有 skill 的 `SKILL.md` 被本地修改：`literature-review`、`markitdown`、`pdf`，并新增匹配说明。

该仓库有 5 个未跟踪的 skill 目录：`data-pro-jv`、`data-pro-thickness-calibration`、`endnote-summary`、`reverse-engineer-anything`、`web-automation`。未跟踪意味着本地新增，不代表已核实全部内容的原创归属。

`matlab_draw` 来自独立本地仓库，初始提交为 `6f2a405`。本版本库从当前安装内容建立统一快照，不改变上述原仓库的分支或远程地址。

保留科学技能来源仓库的 MIT 许可。各 skill 自带的许可与归属说明继续适用。现有 `endnote-summary` 测试随同保存；依赖清单仅作来源上下文留存，不自动安装其中的软件包。

`data-pro-jv` v2.5 保存当前实际安装版本：Jsc/Voc 总体CV≤0.8%、FF≤1.3%、PCE≤1.2%且距候选最大值≤2.5个百分点，保留并列最大值；参数表统一为编号、Jsc、Voc、FF、PCE、Pmax、Imax、Vmax、Rs、Rsh、Isc、日期（补全单位），首页含四项独立筛选及PCE同一入选集合的两份总结；并区分 YUYUIOIO270K 与 Yuyuioio 电脑的归档路径。同样品同点按PCE/FF择优步骤保持严格5%边界。`tests/data-pro-jv` 保存逐点择优、分条件独立筛选及新边界的32项回归测试。测试使用合成输入，不含实验数据或生成的工作簿。
