# 个人 Skill 版本库

保存本机新增或修改过的 skill。Git 记录每次保存的差异，GitHub 私有仓库提供远程备份。

## 已纳入

`data-pro-jv`、`data-pro-thickness-calibration`、`endnote-summary`、`matlab_draw`、`literature-review`、`markitdown`、`pdf`、`reverse-engineer-anything`、`web-automation`。

其中部分是第三方 skill 的本地修改版或本地新增安装项，不能仅凭未跟踪状态认定为本人原创。来源见 [docs/provenance.md](docs/provenance.md)，许可证见 `third_party/`。

## 保存当前版本并上传

在本仓库目录打开终端，运行：

```powershell
python scripts/skill_versions.py save -m "说明本次修改" --push
```

该命令从实际使用的 skill 目录读取最新文件，保存版本并上传。直接在 GitHub 上修改备份，不会自动改变本机正在使用的 skill。仅保存本地版本时省略 `--push`。

## 查看历史与当前差异

```powershell
python scripts/skill_versions.py history
python scripts/skill_versions.py status
git log --oneline -- skills/endnote-summary
git show 版本号 -- skills/endnote-summary
```

`status` 比较实际使用目录和本地备份；`git status` 则检查备份仓库本身。

## 恢复某个 skill

先从历史记录选择版本号，预览将恢复的文件：

```powershell
python scripts/skill_versions.py restore --skill endnote-summary --ref 版本号
```

确认后执行恢复：

```powershell
python scripts/skill_versions.py restore --skill endnote-summary --ref 版本号 --apply
python scripts/skill_versions.py save -m "恢复 endnote-summary 到指定版本" --push
```

恢复前会完整备份当前 skill 到 `.local-backups/`，再恢复该版本的文件，清除该 skill 中较新版多出的有效文件。原有 `.git`、缓存和本地环境不参与版本恢复。不要在 skill 正执行任务时恢复。相关测试和其他 skill 不会随单个 skill 一起回退，涉及依赖变更时应一并检查。

若新对话仍显示旧说明，重新开启对话以重新加载 skill。回退以新提交记录，历史不会被删除。新写的 skill 需先加入 `local-sources.json`，并更新示例清单和来源说明。

## 换电脑与范围

安装 Git、Python 3.12 或以上版本并登录 GitHub。克隆私有仓库后，将 `sources.example.json` 复制为 `local-sources.json`，填写本机实际目录。该文件不上传。

仓库保存 skill 的说明、脚本、配套资源和现有相关测试；不包含第三方仓库全部内容、插件缓存、实验结果或本机账号凭据。`inventory.json` 记录快照文件的 SHA-256。

初始提交是当前已安装版本的基线，无法恢复此前从未保存过的历史版本。本仓库默认手动保存；修改后需要运行保存命令，或请 Codex 代为保存和上传。
