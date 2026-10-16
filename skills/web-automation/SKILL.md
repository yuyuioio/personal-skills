---
name: web-automation
description: 通过 CDP 协议控制本机 Edge 浏览器完成任意网页操作——打开页面、读取文本/HTML、点击、批量点击、填写表单、勾选、下拉选择、截图、结构化提取，以及"按答案库自动作答网页试卷"。当用户说"帮我点这个网页"、"把这个表单填了"、"把页面内容抓下来"、"自动答题"、"完成网页考试"、"操作浏览器"时使用。需要先有一个通过 --remote-debugging-port 启动的受控 Edge 实例。
---

# 网页自动化工具包（CDP + Edge）

## 这套工具解决什么

普通打开的 Edge **无法**被程序接管。只有在启动时带 `--remote-debugging-port` 的
Edge 才开放 CDP 接口，可以用 WebSocket 发指令：读 DOM、点击、填表、截图。

Node.js ≥ 21 内置 `WebSocket` 和 `fetch`，所以**不需要 npm install 任何依赖**。

## 目录结构

```
web-automation/
├── SKILL.md              本文件
├── README.md             快速上手
├── web.mjs               通用网页 CLI ← 最常用
├── lib/cdp.mjs           CDP 连接公共模块
├── edge/
│   ├── start-edge.ps1    启动受控 Edge（带调试端口）
│   └── edge-profile/     受控 Edge 的独立配置目录（登录态存这里，勿删）
├── exam/
│   ├── extract.mjs       从试卷页提取题目
│   ├── inject.mjs        按答案表自动勾选
│   └── verify.mjs        复核勾选结果
├── bank/
│   ├── answer_key.csv    答案库（1364 题，含题干/选项/答案）
│   ├── answer_key.xlsx   同上，Excel 版
│   ├── build_key.py      从原始题库 Excel 重建答案库
│   └── search_key.py     在答案库中搜索题目
├── answers.json          示例答案表（通识类 45 题）
└── exam_questions.json   示例提取结果
```

**工具包绝对路径：`C:\Users\13204\Desktop\web-automation\`**
（下文命令中的 `TOOLKIT` 均指该目录）

## 前置条件（每次开工先检查）

1. **受控 Edge 在跑**（最关键）
   检查：`node TOOLKIT/web.mjs list`
   若报「调试端口未就绪」，启动它：
   ```
   pwsh -File TOOLKIT/edge/start-edge.ps1
   ```
   该脚本用**独立配置目录** `edge/edge-profile`，所以：
   - **登录态会跨重启保留**（不用反复登录）
   - 不会干扰用户平时用的 Edge

   > **复用别的配置目录**：`pwsh -File TOOLKIT/edge/start-edge.ps1 -ProfileDir "D:\某处\profile"`
   > **同一端口只允许一个受控 Edge**：若 `web.mjs list` 已能通，就不要再启动第二个
   > （会抢 9222 端口）。开着的窗口被用户关掉后，重启时用同一个 `-ProfileDir`
   > 即可保留登录态。

2. **Node.js ≥ 21**：`node --version`
3. **登录**：若目标站点需要登录，请**用户在那个受控窗口里自己登录**
   （不要索取账号密码）。登录态存在 `edge-profile`，后续复用。

## web.mjs 命令速查

```
node web.mjs list                            列出所有标签页
node web.mjs nav <url> [等待ms]              打开网页（默认等 4000ms）
node web.mjs text [选择器]                   读文本（默认整页）
node web.mjs html [选择器]                   读 HTML（默认整页）
node web.mjs eval "<js>"                     在页面执行 JS
node web.mjs count <选择器>                  统计元素个数
node web.mjs click <选择器>                  点击第一个
node web.mjs clickAll <选择器>               点击全部
node web.mjs fill <选择器> <值>              填输入框（触发 input/change）
node web.mjs select <选择器> <值>            选下拉项
node web.mjs check <选择器>                  勾选 radio/checkbox
node web.mjs extract <选择器> [out.json]     结构化提取
node web.mjs shot <out.png>                  整页截图
```

工作中常见的探索顺序：

```bash
node web.mjs list                       # 1. 确认页面和调试端口
node web.mjs text                       # 2. 看页面有什么内容
node web.mjs count "input[type=radio]"  # 3. 数一数结构
node web.mjs html ".some-block"         # 4. 看具体结构
node web.mjs click "button.submit"      # 5. 动手
node web.mjs shot out.png               # 6. 截图确认（可选）
```

## 答题流水线（exam/）

适用：网页试卷是单选/判断题、选项是 radio 的结构。

```
① node TOOLKIT/exam/extract.mjs exam_questions.json     # 提取题目
② （用 bank/search_key.py 匹配题干 → 生成 answers.json） # 匹配答案
③ node TOOLKIT/exam/inject.mjs answers.json             # 自动勾选
④ node TOOLKIT/exam/verify.mjs answers.json             # 复核
```

`answers.json` 格式很简单：

```json
{ "1005495": "F", "1005496": "B", "1005497": "D" }
```

键是题目的 `data-id`，值是选项值（A/B/C/D/正确/错误 之类，按页面实际 `value`）。

匹配答案时用搜索脚本：

```bash
python TOOLKIT/bank/search_key.py "值班电话" "失火罪" "带钉鞋"
```

## ⚠️ 关键坑（都是踩过的）

### 1. 选择器：不要用含方括号的 `name` 属性
题目 radio 的 name 形如 `question[1005495]`。若拼选择器时漏掉闭合的 `]`，
`querySelector` 会**静默返回 null**（45 题全部 not-found，排查了很久）。

**正确做法**：用 `data-id`，值就是纯数字。

```js
// ✘ 易错
document.querySelector('input[name="question[' + qid + '"][value="' + val + '"]')
// ✔ 推荐
document.querySelector('input[data-id="' + qid + '"][value="' + val + '"]')
```

**通用教训**：在 JS 里拼选择器时，优先用 `JSON.stringify(sel)` 嵌入，
不要手工拼接引号。

### 2. 答案库的「选项」字段含换行 → 别用 grep 按行读
CSV 里一个字段可能跨多行，`grep` / `read` 按行读会失真（会把一道题的选项
拆成好几"行"，答案字母跑到别的行上）。**必须**用 pandas 读：
`search_key.py` 已经处理好了。

### 3. 选项顺序可能与题库不同 → 按内容匹配，不要直接搬字母
题库里答案是「B.切断电源」，网页上「切断电源」可能排在别的字母。
应当**匹配选项文本**，再换算成网页上的字母。

### 4. 不要自动交卷
「交卷」不可逆。流程固定为：**勾选 → verify 复核 → 报告给用户 → 等用户确认后再交**。
除非用户明确说"直接交卷"。

### 5. 保存/提交是否有副作用要先确认
点击"提交"、"删除"、"支付"类按钮前先明确告知用户。

### 6. 沙箱授权
若工作区 `C:\AI\DeepSeek` 的 ACL 有问题（表现为
`SetNamedSecurityInfoW failed (Win32 5): grantWrite`），则**每条 pwsh 命令
都需要用户手动批准**。此时应尽量把多个步骤合并成一条命令，减少弹窗。

### 7. 桌面等任务区外的路径需要越权
`workspace-write` 只允许写 `C:\AI\DeepSeek`。写桌面/用户目录会报
`sandbox: file access denied`，需要用 `danger-full-access` 重试一次。
**技巧**：先在允许的工作区内造好文件，再用**一条**复制命令搬到目标位置，
这样只需一次授权。

## 省 token 原则（重要）

这次会话花 token 最多的地方，是把整张试卷和整个题库原文搬进了对话。

1. **脚本本地干活，只回显结论**：优先让脚本打印 `45/45 done` 这类摘要。
2. **大结果写文件，不进对话**：DOM/题目先落盘 JSON，只打印条数和差异。
3. **不要 dump 整页**：用 `count` / `text "选择器"` 精确取，不要 `html` 整页。
4. **合并命令**：一次 pwsh 调用跑完多个步骤。
5. **复用既有产物**：`answer_key.csv`、`edge-profile` 登录态不要重复构建。
6. **大任务可交给 subagent**，让它在自己上下文里试错，只回传结果。

## 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| `调试端口未就绪` | 受控 Edge 没跑 → `start-edge.ps1` |
| `WebSocket 连接失败` | Edge 被关了 → 重启受控 Edge |
| 选择器返回 null | 见「关键坑 1」，检查引号/方括号；先 `count` 验证选择器 |
| 点击没反应 | 试点它的 `label` 父元素；或 `eval` 里手动派发事件 |
| 需要重新登录 | `edge-profile` 被删或站点过期 → 让用户在受控窗口登录 |
| 想接管用户已开着的 Edge | **做不到**，必须用带调试端口的实例；不要试着去 kill 用户的 Edge |
| 中文乱码 | 读写文件统一 UTF-8；CSV 用 `encoding="utf-8-sig"` |

## 安全与边界

- 不索取、不记录用户的账号密码；让用户自己在可见的受控窗口登录。
- 破坏性操作（提交、删除、付款）前必须确认。
- 这是用户自己机器上的自动化工具，用途由用户负责。
