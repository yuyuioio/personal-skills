# 身份、命名和手动交付契约

## 身份与书目

完整 SHA-256 标识某一 PDF 的字节；DOI 标识出版物。预印本、接受稿、出版社版本及批注副本可有不同哈希。不要把 DOI 相同说成 PDF 字节相同。EndNote 记录号须与所属 `.enl` 配对。

`prepare --bibliography` 接受 UTF-8 JSON：`title`、`doi`、`doi_status`、`doi_evidence`、`authors`、`year`、`journal`、`sources`。字符串未知留空，列表未知为 `[]`。保留原始题名，不用翻译题名代替原文。

`sources` 默认包含自动获取/复用的主全文及各 SI 清单，记录 URL、文件、哈希、版本、下载与实际阅读状态，字段见 [acquisition.md](acquisition.md)。SI 以本篇 DOI 关联而非制造独立 DOI；主 PDF 哈希不能代替 SI 文件哈希。

- DOI 状态为 `missing`、`candidate`、`unresolved` 或 `verified`。
- `verified` 必须有 DOI 及证据，例如出版社 URL 与对应题名/作者，或确立本篇身份的 PDF 首页定位。脚本只验证结构，代理核验事实。
- `doi_candidates` 保留元数据和前两页的候选及上下文，不自动选第一个。引文 DOI、乱码及未经核验的断行不能作确定值。
- 有候选无确定 DOI 用 `unresolved`；未找到用 `missing`，说明未找到而非断言论文不存在 DOI。
- `sources` 记录出版社/Crossref 查询等来源。元数据查询不用上传全文，解析成功不等于身份核验。

## 输出

默认每次总结用 `prepare --paper-folder --output-dir 存储根路径 --bibliography bibliography.json` 建立新的 `原文标题__10.xxxx_suffix/` 文件夹；清单中 `storage.layout: title_doi_folder` 标识这一布局。主总结命名为 `原文标题__10.xxxx_suffix.md`，与本次证据文件一并位于该文件夹。普通重复总结的文件夹加 `__2`、`__3` 序号，保留先前结果。旧清单未设置这一布局时也使用同一主 Markdown 文件名规则；新总结必须使用独立文件夹布局。v2.2 已交付的“总结.md”不自动改名；后续打包使用实际返回的新文件路径。

| 文件 | 用途 | 添加到 EndNote |
| --- | --- | --- |
| `原文标题__DOI.md` | 中文总结，完整标题、DOI、源哈希和状态；位于标题＋DOI文件夹中 | 是，作为该条目附件 |
| `paper-HASH.source.md` | 带物理页码的提取文本 | 否 |
| `paper-HASH.match.json` | 身份、证据、候选、输出路径/哈希和匹配状态 | 否，保留追溯 |
| `paper-HASH.notes.txt` | 请求时生成的短笔记 | 可自行粘贴 |

文件夹名和文件名把 Windows 禁用的 `< > : " / \ | ? *` 和控制字符换成 `_`，清理末尾空格/点及设备名。完整题名、DOI 保存在元数据与正文；不能从 `_` 可靠反向恢复 DOI。

无 DOI 的文件夹：`原文标题__无DOI/`；选定但未核验：`原文标题__候选DOI__DOI待核验/`；候选未选定：`原文标题__DOI待核验/`。未确认题名用原 PDF 名称主体临时命名并在正文注明，不编造题名或 DOI。

路径过长时先缩短文件夹中的题名，为主 Markdown 文件名保留原始题名和 DOI；仍超限时缩短文件名中的题名并告知。完整题名不变；极端长 DOI 的路径标签会缩短并加标签哈希，完整 DOI 保留在正文与元数据。目录过长会提示换短存储根路径。普通重复总结新建目录；只有修改本次已有总结才使用 `--overwrite`，打包仍保护同目录的无关文件和其他来源，必要时给总结文件增加源短哈希。页码以物理 PDF 页为准，可同时注明印刷页码。

## 状态和可选只读匹配

默认不读取 EndNote：`endnote.status: not_checked`、`record_number: null`、`writeback_status: not_attempted`、`delivery_mode: manual_attachment`。重生成时本次交付清除旧写回成功标记，以前记录存入 `previous_deliveries`。

用户提供 XML 时可只读匹配，不写库。拒绝 DTD/实体、越出 `.Data/PDF` 的内部路径、远程 file URI。相同 PDF 哈希或已核验 DOI 是强候选；多强候选或 DOI/哈希冲突为 `ambiguous`；唯一强候选且有库及记录号为 `matched`；只有规范化题名匹配为 `review_required`；无候选为 `not_found`。匹配只对导出快照成立，XML 可过时或省略非 PDF 附件，不能证明附件注册。

## 手动添加

按完整 DOI/原题名找到正确条目，在条目的 File Attachments/Attach File 选择主 `.md` 并保存；选择复制为相对附件可由库管理副本。Markdown 由系统关联编辑器打开，不是书目交换格式。不要用 RIS/XML 重导入更新条目，也不要手动复制到 `.Data/PDF` 假装附件注册。

历史写回只在用户明确再次要求自动导入时适用，见 `references/desktop_writeback.md`。依据：[EndNote 文件附件](https://docs.endnote.com/docs/endnote/2025/v1/windows/en/content/03editref/linking_a_file_toan_enref.htm)、[Windows 文件命名](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)、[Crossref API](https://github.com/Crossref/rest-api-doc)。
