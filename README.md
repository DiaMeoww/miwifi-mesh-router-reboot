# MiWiFi/Redmi 小米路由器定时重启脚本使用说明

这个说明对应同目录下的 `miwifi_weekly_reboot.py`。

## 1. 项目介绍

小米路由器主路由可以设置定时重启，但如果有无线 Mesh 子路由，子路由无法跟随主路由重启。长时间使用不重启时，子路由可能会爆内存，导致网络卡顿。

此项目用于解决无线 Mesh 路由器的定时重启问题。你可以通过本地局域网里的小服务器或 NAS，配合青龙面板定时运行，也可以让脚本长时间运行，从而达到自动执行 Python 脚本定时重启路由器的目的。

## 2. 功能说明

脚本会通过小米/Redmi 路由器 Web 管理接口登录路由器，然后调用重启 API。

脚本有两种运行模式：

- `RUN_MODE = 0`：启动脚本后立刻执行一次重启，然后退出。
- `RUN_MODE = 1`：启动脚本后等待代码里设定的计划时间，到点后执行重启，并继续等待下一次计划时间。

如果使用青龙面板定时启动，则使用模式 `0`。此时青龙面板会在 cron 规则下定时启动此脚本，执行后脚本停止。

如果不使用定时启动，则使用模式 `1`。此脚本会一直运行，直到设置时间执行一次重启。

当前默认值是：

```python
RUN_MODE = 0
```

## 3. 修改配置

打开 `miwifi_weekly_reboot.py`，找到“用户配置区”：

```python
RUN_MODE = 0
MIWIFI_PASSWORD = "请在这里填写路由器管理密码"
MIWIFI_HOST = "http://192.168.x.x"
MIWIFI_USERNAME = "admin"
SCHEDULE_WEEKDAY = "monday"
SCHEDULE_HOUR = 4
SCHEDULE_MINUTE = 59
MIWIFI_USE_PROXY = False
```

需要修改的内容：

- `MIWIFI_PASSWORD`：改成你的路由器管理密码。
- `MIWIFI_HOST`：填写路由器登录网址，格式为 `http://192.168.x.x`。
- `RUN_MODE`：改成 `0` 或 `1`。
- `SCHEDULE_WEEKDAY`：计划执行星期，默认 `monday`，表示周一。
- `SCHEDULE_HOUR`：计划执行小时，24 小时制。
- `SCHEDULE_MINUTE`：计划执行分钟。

如果你要每周一早晨 4:49 执行，可以这样设置：

```python
RUN_MODE = 1
SCHEDULE_WEEKDAY = "monday"
SCHEDULE_HOUR = 4
SCHEDULE_MINUTE = 49
```

## 4. 运行脚本

在 PowerShell 里执行：

```powershell
python miwifi_weekly_reboot.py
```

如果 `RUN_MODE = 0`，脚本会立刻执行一次重启。

如果 `RUN_MODE = 1`，PowerShell 窗口需要保持打开，脚本才会一直等待计划时间。

## 5. 测试登录

如果只想测试密码和接口是否能登录，不想重启路由器，可以执行：

```powershell
python miwifi_weekly_reboot.py --test-login
```

测试登录成功时，只会显示登录成功，不会执行重启。

## 6. 日志说明

脚本不会在本地生成 `.log` 文件。

运行过程中的提示只会显示在当前 PowerShell 窗口里。

## 7. 注意事项

- 路由器重启期间会短暂断网。
- 密码会明文保存在 `miwifi_weekly_reboot.py` 里，不要把这个文件发给别人。
- 默认会绕过系统代理直连路由器。如果路由器 API 必须走代理，才把 `MIWIFI_USE_PROXY` 改成 `True`。
- 计划执行模式依赖电脑持续运行。如果电脑关机、休眠，脚本不会在关机或休眠期间执行。
