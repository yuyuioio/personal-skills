# 文献阅读方法整合来源

核对日期：2026-10-06。整合 33 个去重技能的阅读方法/条件性资料获取能力。此表记录本地来源版本，不声称外部服务当前已连接。普通阅读直接使用本技能内的方法；按任务加载阅读、证据评估或综合参考，不依次调用 33 个技能。

采用独立编写的流程和检查项，保留原技能及其许可。未复制专有文档技能的整本手册或代码，未将其他技能的凭据读取、上传、生成图片、发布、写库要求设为本技能默认步骤。

| 来源技能 | 本地来源版本 | 整合位置/层次 | 采用的方法 |
| --- | --- | --- | --- |
| bgpt-paper-search | 1.1 | 条件性检索 | 全文实验信息结构化发现，回原文核验 |
| citation-management | 2.1 | 核心阅读 | DOI、题名、作者、版本对应核验与来源留存 |
| database-lookup | 1.6 | 条件性检索 | 文章实体与公共数据 accession 核对、限定范围 |
| documents | 未声明 | 稿件阅读 | 官方文档技能的读取/渲染原则，非默认生成 Word |
| docx | 2.1 | 稿件阅读 | Word 稿件结构、修订、表格、图注与按需视觉核验 |
| epigraphdb-skill | 未声明 | 学科限定检索 | 公共 GWAS/MR/文献路径，保留范围与关联边界 |
| exa-search | 1.2 | 条件性检索 | 学术来源范围与原始来源优先的网页发现 |
| experimental-design | 1.2 | 核心阅读 | 实验单位、控制、批次、重复、随机化及伪重复 |
| folklore-variant-evidence | 1.0 | 学科限定检索 | 公开变异的来源文献和明确解析状态，无患者资料 |
| hugging-science | 1.3 | 学科限定检索 | 科学 ML 论文的模型/数据/方法来源核对，不运行模型 |
| hypothesis-generation | 2.2 | 核心阅读 | 观察/假说/预测区分、竞争解释与区分性验证 |
| liteparse | 1.2 | 核心阅读 | 布局/坐标与局部 OCR，数字 PDF 避免无谓 OCR |
| literature-review | 1.9 | 核心阅读 | 范围、纳排、证据表、主题综合；系统综述仅明确要求时 |
| markdown-mermaid-writing | 1.1 | 核心阅读 | 可独立阅读的 Markdown、比较表、按需机制流程说明 |
| markitdown | 2.3 | 核心阅读 | 文档转换与学术总结分离，保留源身份与提取限制 |
| networkx | 1.2 | 可选关系综合 | 引文图发现路线，图节点保留 DOI，中心性不等于质量 |
| notion-research-documentation | 未声明 | 条件性资料来源 | 已有授权笔记的带来源比较，不自动发布页面 |
| open-notebook | 1.3 | 条件性资料来源 | 已有来源笔记库问答，服务配置独立于技能存在 |
| paper-lookup | 2.2 | 条件性检索 | 定向 DOI/全文/引文发现，保存查询与实际访问范围 |
| paperclip | 1.3 | 条件性检索 | 全文/行级证据定位，区分摘要与全文实际可得性 |
| paperzilla | 1.0 | 条件性检索 | 相关文献推荐的理由及原文来源，不自动提交反馈 |
| parallel-web | 1.3 | 条件性检索 | 按需搜索/提取，深研究仅请求时，无后台监控 |
| pdf | 1.3 | 核心阅读 | 按页文本、关键页面视觉核验、表格/OCR；同时核对本地和官方 PDF 变体 |
| peer-review | 2.2 | 核心阅读 | 主张—证据定位、复现性、建设性局限与验证建议 |
| pyzotero | 1.2 | 条件性资料来源 | 用户现有 Zotero 库只读条目/全文发现 |
| research-lookup | 1.5 | 条件性检索 | 近期/奠基/方法/矛盾证据，不强制深研究或固定数量 |
| scholar-evaluation | 2.2 | 核心阅读 | 证据先于质量打分，不以期刊和引用数代理科学质量 |
| scientific-critical-thinking | 1.3 | 核心阅读 | 因果、混杂、替代解释和证据边界 |
| scientific-visualization | 1.2 | 核心阅读 | 审查图表截轴、归一化、缺失、色标、处理与单位 |
| scientific-writing | 2.1 | 核心阅读 | 清晰中文科学表达、事实与推断分离、不造数据/文献 |
| statistical-analysis | 1.2 | 核心阅读 | 效应大小、n、SD/SE/CI、显著性与拟合限制 |
| uncertainty-and-units | 1.1 | 核心阅读 | 量纲/单位、误差定义、原值与转换保留 |
| Zotero | 未声明 | 条件性资料来源 | 本地索引全文与元数据，未安装缓存不宣称可调用 |

版本差异：pdf 同时核对共享本地版本和官方 PDF 技能；documents 来自官方文档插件。其他重复文件仅作为来源快照，不把旧备份优先于现行共享文件。

阅读层方法已合并到 reading_workflow.md / critical_appraisal.md；检索、服务连接和关系综合方法位于 search_and_synthesis.md。集成不等于复制服务实现或提供不存在的连接。

## 图表读取辅助（2026-10-15）

- 随包保留固定版本 OpenAI 官方 `pdf` 技能于 [pdf_support.md](pdf_support.md)，以页面渲染优先、文本不代替版面、成图视觉核对辅助文献读取。原始内容未修改，来源提交与哈希见 `pdf_support_source.json`；Apache-2.0 许可见 `pdf_support_LICENSE.txt`。本技能的目录和附件契约优先于该通用 PDF 技能的产物惯例。
- 当前环境的 `pdf` / `pdf:pdf` 可用于读取；本包 `scripts/figure_assets.py` 提供已核验 PDF 的确定性裁剪、来源哈希和包内图片链接检查。
- `scientific-critical-thinking` 用于主张—证据、控制、替代解释；`scientific-visualization` 按需审查截轴、色标、归一化和图像处理。裁剪原图不调用生成式绘图技能，不用重绘替代原始证据。

这些是后续读取的支持资源和调用规则；图表科学含义仍需结合实际正文和 SI 判断，文件或脚本存在本身不是阅读完成的证明。
