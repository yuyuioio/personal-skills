# 固定桥接协议与恢复操作

固定目录默认是 `Z:\workspace\matlab-chatgpt-bridge`。实际协议以该目录的 `chatgpt_matlab_bridge.m` 为准；这里记录的是 2026-10-13 已验证的版本。

## 状态与执行

- `status.json`：包含 `state`（`ready`、`busy`、`stopped`）、`release`、`fixed_folder`、`updated_at_local`。空闲时约每 2 秒更新。使用文件修改时间判断新鲜程度，避免把机器本地时间误当 UTC。
- `jobs/<task_id>/`：每个任务一个目录；任务 ID 以字母开头，仅使用字母、数字、下划线和连字符。
- `task.m`：MATLAB 脚本。请求中的脚本名必须以字母开头，仅使用字母、数字、下划线并以 `.m` 结尾，不允许绝对路径或目录分隔符。
- `request.json`：最后发布，示例：

```json
{"task_id":"matlab_draw_20261013_uniqueid","script":"task.m"}
```

- `result.json`：任务执行时先写 `running`，结束时写 `completed` 或 `failed`，包含 `log`、`error`、`release`、`updated_at_local`。
- 一旦任务目录存在 `result.json`，桥接会跳过该目录，不能复用任务 ID。任务中断后遗留 `running` 时先检查其输出，避免重复执行有副作用的代码。
- 桥接串行处理任务，在独立函数工作区中调用 `run(scriptPath)`；并非 MATLAB 基础工作区。因此输入应来自文件，不能假设能读取用户在命令窗口创建的变量。
- 一般保持一个 MATLAB 会话运行此桥接。多个 MATLAB 会话同时监视同一目录没有跨进程互斥保证。

## 使用 helper

选择环境里实际可用的 Python 3。此电脑已测试 `C:\Python314\python.exe`；其他对话不必硬编码这个解释器。helper 只使用 Python 标准库，不需要安装 MATLAB Engine。

```powershell
& 'C:\Python314\python.exe' '<技能目录>\scripts\bridge_job.py' status
& 'C:\Python314\python.exe' '<技能目录>\scripts\bridge_job.py' submit --script '<已写好的绘图脚本.m>' --input '<用户授权的数据.xlsx>'
& 'C:\Python314\python.exe' '<技能目录>\scripts\bridge_job.py' wait --task-id '<submit 返回的 task_id>' --timeout 30
```

`--input` 可以重复。输入文件按文件名复制到任务目录，脚本统一保存为 `task.m`。若文件名冲突，helper 会拒绝提交；先改用明确、唯一的暂存文件名。`--root` 可放在子命令前，覆盖默认固定目录。

脚本示例：

```matlab
jobDir = fileparts(mfilename('fullpath'));
data = readtable(fullfile(jobDir,'measurement.xlsx'),'Sheet','JV');
outDir = fullfile(jobDir,'outputs');
if ~isfolder(outDir), mkdir(outDir); end
% 按实际列名、单位和分组创建图形，不假定任意 Excel 都有相同结构。
```

helper 返回 JSON。`wait` 退出码：0=completed；1=MATLAB failed；2=参数、权限或读取错误；3=等待超时。`completed` 只证明 MATLAB 没有抛出异常，不代替数据及图像检查。

## 恢复连接时才使用

正常启动提示：

```text
ChatGPT fixed MATLAB bridge started: Z:\workspace\matlab-chatgpt-bridge
```

若 MATLAB 已打开但桥接未启动，确认配置后请用户在 MATLAB 中执行：

```matlab
addpath('Z:/workspace/matlab-chatgpt-bridge');
chatgpt_matlab_bridge('start')
```

用户明确要求停止或改变自动启动时使用：

```matlab
chatgpt_matlab_bridge('stop')    % 只停止当前会话
chatgpt_matlab_bridge('disable') % 停止并禁止后续自动加载
chatgpt_matlab_bridge('enable')  % 恢复自动加载并立即启动
```

自动启动入口是 `C:\Users\13204\Documents\MATLAB\startup.m` 中的受管理代码块。更换电脑或 MATLAB 配置后读取实际 `userpath`、`which('startup')` 和安装记录，不复制旧对话临时目录作为长期依赖。
