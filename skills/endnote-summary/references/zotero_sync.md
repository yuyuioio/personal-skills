# 识别电脑并保存到已有 Zotero 文献

## 当前电脑

每次执行先读取 `[Environment]::MachineName`（PowerShell 7）或 `platform.node()`，在结果与清单中记录实际名称。

- `YUYUIOIO270K`：当前电脑；2026-11-01 实测名称。
- `Yuyuioio`：用户之前的电脑，大小写不敏感匹配。
- 其他名称：记录实际名称，按本机当前环境重新发现路径和 Zotero 连接；不要冒用这两台机器的已知路径。

电脑名称用于分清环境，不是凭据或权限。所有机器都从本机 Zotero 的状态接口、配置及实际附件 URL 发现数据目录；不能把 `Yuyuioio` 的盘符、用户名、存储路径或“已经同步成功”记录套到 `YUYUIOIO270K`，反之亦然。Windows 命令显式使用 `C:\Program Files\PowerShell\7\pwsh.exe`。

## 默认范围与匹配

用户已明确要求：生成总结后直接存到 Zotero 的同名已有文献下。执行本技能时，这项默认保存操作已在任务范围内，无需每篇重复确认；仅在找不到唯一条目、身份冲突或确实需要用户完成访问操作时询问。用户当次要求只生成文件/手动附件则服从当次要求。

先使用可用 Zotero 插件的 `status --json`，随后检索已核实 DOI 和原题名。若无插件，直接只读探测 `http://127.0.0.1:23119/api/`，必要时读取本机实际配置。Zotero 7–9 的本地 API 只读；Zotero 10+ 提供需授权的官方本地写入与文件上传，不把旧版本限制套到新版。

优先核对 DOI，再比较规范化完整题名。允许大小写、Unicode/标点、标题外层 `< >` 和末尾 `.pdf` 这样的导入格式差异；不能用短前缀、相似主题或 PDF 文件名直接认定同篇。条目缺 DOI 时，唯一完整题名可匹配，能用其现有 PDF 与本次源 PDF 的 SHA-256 核对时一并核对。多条匹配、DOI 冲突、多个库不明确时停止写入并列出候选；不要猜选，也不创建新的主书目条目。

默认保存到本地个人文库的既有主条目；用户指定群组库时需使用该库实际 ID 与可写权限，不将群组条目存到个人库充数。保留已有 PDF、笔记、标签和书目信息，不借本次保存顺便“修复”其标题或补全元数据。

## 每次先检查已有正文文件

匹配条目后，先运行只读检查（DOI 未知时省略 `--doi`）：

```text
python scripts/zotero_sync.py probe --title "完整原始题名" --doi "已知DOI" --out "本次工作目录/zotero-source-check.json"
```

此命令列出已有PDF附件的真实路径、文件存在性、PDF可打开性、页数、哈希及首页文本，区分 `readable_pdf`、`missing`、`unreadable`。解析器缺失属于工具问题，不应误报为PDF损坏。随后根据首页核验题名/DOI、区分正文与SI、确认版本；可用正文直接读取并记为 `reused_local`，不重复下载。扫描PDF首页无提取文本仍可能可读，应视觉核验/按需OCR，不能仅因没有文本就重新下载。

`probe` 的可读PDF清单不自动代表正文已核验，也不代表已完整阅读。仅有记录而本地文件缺失时，先尝试Zotero现有正常附件下载能力；仍不可用再获取出版社/公开全文。正文复用不免除核查出版社SI列表；已存在同版本SI可复用，缺失项仍按获取流程下载。

## 附件形式和执行

保留原来的“原始题名＋DOI”本地 Markdown 与 `figures/` 包，并另外生成**内嵌全部原图的单文件 HTML**。默认将 **MD 与 HTML 两份总结都作为同一主条目的导入文件附件保存**，不是外部文件链接，也不新建主书目。

MD 必须保留相对图片引用，并将其引用的图片按相同相对路径保存到该MD附件的存储目录。先使用原生API注册并导入MD，再仅复制计划中逐项核验的资源到这个已注册附件旁；不能只向storage复制一个未注册文件充当入库，也不将全文、SI和临时脚本无差别带入MD附件。HTML仍内嵌所有图片，可独立阅读。两份按内容分别去重：已有相同HTML时复用它并补MD，反之亦然；已有MD同内容但图片缺失时补齐资源，图片冲突则停止并报告，不覆盖不明内容。

`scripts/zotero_sync.py` 提供已有PDF检查、只读匹配、HTML 生成、MD/HTML双附件原生保存脚本生成及保存后验证；使用 Python 3.10+。PDF检查复用已有`pypdf`；HTML 渲染优先复用已有 `Markdown`，缺少时使用 `scripts/_vendor/` 中随包保留的 Markdown 3.9（含许可），其余逻辑使用标准库，不为这一步重复联网安装。

### 已配置 Zotero 10 的默认保存

```text
python scripts/zotero_local_api.py status
python scripts/zotero_sync.py save --manifest "本次文件夹/paper-HASH.match.json"
```

`save` 依次 prepare、核验目标、通过官方 API 分别保存/复用 HTML 与 MD 两份子附件，为已注册MD复制相对图片资源，然后读取验证；不需要打开“执行 JavaScript”。已有相同 SHA-256 的导入附件直接复用，不重复新增；不覆盖不同内容附件、不新建主书目、不更改其元数据。也可先 `prepare --manifest ...` 再 `save --plan zotero-sync-plan.json`，prepare 本身不代表保存成功。

客户端固定使用 `http://127.0.0.1:23119/api/`、个人库 `users/0`；校验本机、Zotero-Server-ID、父条目完整题名及 DOI。上传采用官方三阶段流程：新建 imported_file 子附件、申请上传、传输字节、注册文件。失败保留 pending journal，重试前检查目标条目，避免重复空附件；401/403/412 或身份冲突不静默重试、不自动重授权，不回退到 JavaScript 窗口。

Windows 的本地授权凭据位于 `%LOCALAPPDATA%/CodexZotero/local-api.json`，密钥以当前 Windows 用户的 DPAPI 加密，不输出密钥、不放入文章文件夹或 Git、不复制 Zotero 配置中的原始密钥。官方授权本身可写所有用户有权编辑的库，不具备单条目权限；本客户端只开放已匹配父条目下的文件附件新增/上传，**不开放通用任意写入、删除或数据库接口**。

### 一次性授权与撤销

2026-11-06 已在 YUYUIOIO270K / Zotero 10.0.7 配置应用 `Codex endnote-summary attachment writer` 的“始终允许”，并实测实际 SI 附件上传、SHA-256 验证和重复请求复用。每次仍以 `status` 与当前服务返回值为准；此记录不证明其他电脑/文库已授权。

仅当用户要求在新电脑/文库设置持久接口，或明确要求重新授权时，运行：

```text
python scripts/zotero_local_api.py configure
```

它调用官方 `/api/local/authorize`，在 Zotero 原生提示中显示上述应用名；“始终允许”才会保存持久凭据。单次“允许”不能声称持久配置成功；拒绝后不重试。授权被撤销时停止写入并说明需重新设置，不每篇重复弹框。可在 Zotero 设置→高级→清除写入授权撤销（这会清除全部本地授权），或仅删除客户端加密凭据停用此客户端，不改变同步服务/账号设置。

### 旧版本的明确回退

旧版 Zotero 或本地写入不可用时，先说明具体缺口。只有明确选择旧路径才用 `prepare --legacy-script` 生成 `zotero-attach.js`，在已核对焦点的 Tools→Developer→Run JavaScript 中通过原生 importFromFile 分别保存MD和HTML并复制MD图片资源；该API自行管理事务，不外套嵌套事务；不能因为没找到密钥就默认走代码窗口。临时剪贴板须恢复，不关闭其他用户窗口，同原因最多修正一次。

### 验证与回执

`save` 自动执行 verify；也可单独运行：

```text
python scripts/zotero_sync.py verify --plan "本次文件夹/zotero-sync-plan.json"
```

验证必须分别确认：MD和HTML均存在于预期父条目；两者`linkMode`均为`imported_file`；各导入副本与对应源文件的SHA-256一致；HTML每个内嵌图像的解码哈希与原图一致；MD每个相对图片链接在其附件目录内可解析且哈希一致。新计划`required_formats`为`["html", "markdown"]`，只有两份及资源都通过才记`zotero.writeback_status: verified`；任一缺失或错误均不得宣称双格式入库成功。回执`attachments.html`和`attachments.markdown`分别记录附件key、路径、哈希及验证状态，保留机器名、父key和`zotero://select/library/items/KEY`。旧版无`required_formats`计划仅按旧HTML范围核验，不冒称新增MD。API 返回成功不足以替代验证。HTML 内的保存状态以最终 `zotero-sync-receipt.json` 为准，避免导入文件预先宣称成功。

官方资料：[Zotero 10 Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)、[文件上传](https://www.zotero.org/support/dev/web_api/v3/file_upload)。不得对外暴露端口；不需额外插件或后台服务。

## 本地保存与云同步的区别

成功导入只证明当前电脑 Zotero 中已有总结附件。它交给 Zotero 现有设置进行元数据/文件同步；不修改用户既有 WebDAV、配额或附件保留策略。未实际验证服务器或第二台电脑收到时，`cloud_sync_status` 保持 `not_verified`，交付写“已保存到本机 Zotero，跨设备同步未验证”，不能说旧电脑已收到、云上传完成或附件永久保留。使用了 Zotero 插件时，在交付中链接实际使用的插件技能。

## 兼容的 EndNote 方式

只有用户明确要求 EndNote 手动附件时才按旧流程交付 `.md` 与图片包；只有明确请求 EndNote 自动写回时才读 `desktop_writeback.md`。这些兼容模式不覆盖当前默认的 Zotero 保存，也不授权修改 EndNote 数据库或制造重复书目。
