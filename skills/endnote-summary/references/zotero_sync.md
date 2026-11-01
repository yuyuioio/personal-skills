# 识别电脑并保存到已有 Zotero 文献

## 当前电脑

每次执行先读取 `[Environment]::MachineName`（PowerShell 7）或 `platform.node()`，在结果与清单中记录实际名称。

- `YUYUIOIO270K`：当前电脑；2026-11-01 实测名称。
- `Yuyuioio`：用户之前的电脑，大小写不敏感匹配。
- 其他名称：记录实际名称，按本机当前环境重新发现路径和 Zotero 连接；不要冒用这两台机器的已知路径。

电脑名称用于分清环境，不是凭据或权限。所有机器都从本机 Zotero 的状态接口、配置及实际附件 URL 发现数据目录；不能把 `Yuyuioio` 的盘符、用户名、存储路径或“已经同步成功”记录套到 `YUYUIOIO270K`，反之亦然。Windows 命令显式使用 `C:\Program Files\PowerShell\7\pwsh.exe`。

## 默认范围与匹配

用户已明确要求：生成总结后直接存到 Zotero 的同名已有文献下。执行本技能时，这项默认保存操作已在任务范围内，无需每篇重复确认；仅在找不到唯一条目、身份冲突或确实需要用户完成访问操作时询问。用户当次要求只生成文件/手动附件则服从当次要求。

先使用可用 Zotero 插件的 `status --json`，随后检索已核实 DOI 和原题名。若无插件，直接只读探测 `http://127.0.0.1:23119/api/`，必要时读取本机实际配置；不得声称只读 API 支持写入。

优先核对 DOI，再比较规范化完整题名。允许大小写、Unicode/标点、标题外层 `< >` 和末尾 `.pdf` 这样的导入格式差异；不能用短前缀、相似主题或 PDF 文件名直接认定同篇。条目缺 DOI 时，唯一完整题名可匹配，能用其现有 PDF 与本次源 PDF 的 SHA-256 核对时一并核对。多条匹配、DOI 冲突、多个库不明确时停止写入并列出候选；不要猜选，也不创建新的主书目条目。

默认保存到本地个人文库的既有主条目；用户指定群组库时需使用该库实际 ID 与可写权限，不将群组条目存到个人库充数。保留已有 PDF、笔记、标签和书目信息，不借本次保存顺便“修复”其标题或补全元数据。

## 附件形式和执行

保留原来的“原始题名＋DOI”本地 Markdown 与 `figures/` 包。为避免只同步 `.md` 后相对图片失效，默认另外生成**内嵌全部原图的单文件 HTML**，将其作为同一主条目的**导入文件附件**保存。默认只新增这一份可直接阅读的总结附件；不是外部文件链接，也不把总结重新识别为论文。需要 Markdown 源件时可继续交付本地包，不无故增加重复附件。

`scripts/zotero_sync.py` 提供只读匹配、HTML 生成、原生保存脚本生成及保存后验证；使用 Python 3.10+。HTML 渲染优先复用已有 `Markdown`，缺少时使用 `scripts/_vendor/` 中随包保留的 Markdown 3.9（含许可），其余逻辑使用标准库，不为这一步重复联网安装。

```text
python scripts/zotero_sync.py prepare --manifest "本次文件夹/paper-HASH.match.json"
```

该命令记录电脑、目标条目 key、匹配依据、Markdown/HTML 哈希及嵌入图像清单，生成 `zotero-sync-plan.json` 与 `zotero-attach.js`；**prepare 不写 Zotero，不代表保存成功**。输入应为完成科学阅读、图表检查并已 package 的总结。

有正式写附件能力的 Zotero 工具时优先使用它，并验证 parent key 和导入副本；现有 Zotero 插件只有检索/书目导入能力而不能给已有条目加附件时，使用 Zotero 自带的 Tools/工具 → Developer/开发者 → Run JavaScript：将本次已审读的 `zotero-attach.js` 放入编辑区并执行。脚本经 `Zotero.Attachments.importFromFile` 保存，运行前再次核对电脑、父条目题名和 DOI；按内容比较已有 HTML，完全相同则复用，不新增。该方式不直接修改 SQLite，不安装持久脚本服务或开放额外网络端口，也不需要导出 cookies/API 密钥。

桌面自动化只能操作这一窗口，粘贴/快捷键前核对焦点，临时使用剪贴板时恢复原内容；不要关闭用户的其他窗口。运行结束通过本地 API 复查，不以“点了执行”作为成功依据。同原因失败最多再诊断/修正一次；仍不可执行则保留本地结果并说明实际缺口。

```text
python scripts/zotero_sync.py verify --plan "本次文件夹/zotero-sync-plan.json"
```

验证必须确认：附件存在于预期父条目；`linkMode` 为 `imported_file`；导入副本与 HTML 的 SHA-256 一致；每个内嵌图像解码后的哈希与原图一致。验证通过才记 `zotero.writeback_status: verified`，保存回执中的机器名、父 key、附件 key、文件哈希和 `zotero://select/library/items/KEY`。原生脚本有结果但验证失败时保持未验证，先查当前子附件，不能盲目重复新增。

HTML 正文可以保持“本次将保存到 Zotero”的表述；已完成状态以 `zotero-sync-receipt.json` 和本地 API 读取为准，不把成功宣称预先写进即将导入的文件造成循环依赖。

## 本地保存与云同步的区别

成功导入只证明当前电脑 Zotero 中已有总结附件。它交给 Zotero 现有设置进行元数据/文件同步；不修改用户既有 WebDAV、配额或附件保留策略。未实际验证服务器或第二台电脑收到时，`cloud_sync_status` 保持 `not_verified`，交付写“已保存到本机 Zotero，跨设备同步未验证”，不能说旧电脑已收到、云上传完成或附件永久保留。使用了 Zotero 插件时，在交付中链接实际使用的插件技能。

## 兼容的 EndNote 方式

只有用户明确要求 EndNote 手动附件时才按旧流程交付 `.md` 与图片包；只有明确请求 EndNote 自动写回时才读 `desktop_writeback.md`。这些兼容模式不覆盖当前默认的 Zotero 保存，也不授权修改 EndNote 数据库或制造重复书目。
