# 达妮卡桌宠 · DanicaPet

> 跑在 Windows 桌面上的《原神》达妮卡桌宠：双击 Q 弹互动、DeepSeek 联网闲聊、长期记忆、天气与新闻播报。
> 纯 Python + PySide6 实现，免安装，整个文件夹复制走就能用。

![达妮卡](assets/idle.png)

## 功能

- **Q 弹互动**：双击触发弹跳动画与头顶气泡，三选一——随机台词 / 今日 token 与余额 / 日期天气
- **情绪形态**：8 秒内连点 5 次切生气形态，5 秒后自动恢复
- **走神**：双击有 20% 概率无反应；连续两次走神后，第三次必定触发专属台词
- **拖拽与气泡**：左键拖动并记忆位置；气泡跟随人物，贴近屏幕右缘自动翻到左侧
- **右键菜单**：联网对话、对话回顾面板（默认 5 轮 / 可展开 20 轮 / 可导出）、刷新 token 与余额、看天气、换回常态、重建桌面快捷方式、退出
- **全屏隐藏**：前台全屏（含 D3D 独占、演示模式）时自动隐藏并暂停气泡，退出全屏 0.6 秒内恢复，最大化窗口不误触发
- **记忆系统**：`memory.json` 保存最近 20 条上下文与最多 30 条长期事实；`history.log` 全量流水，只增不减

## 快速开始（源码运行）

```bat
python -m venv .venv
.venv\Scripts\activate
pip install PySide6
python app.py
```

需保证 `assets/` 与 `zstd/` 与 `app.py` 同级。

## 打包

```bat
pip install pyinstaller
pyinstaller DanicaPet.spec
```

产物在 `dist\DanicaPet\`，双击 `DanicaPet.exe` 即可。

## 接入 DeepSeek（可选）

对话与余额需要 API Key，按以下优先级读取（前面的优先）：

1. 同目录 `config.json` 中的 `"api_key": "sk-..."` —— 没装 DSH 的人用这条
2. 环境变量 `DEEPSEEK_API_KEY`
3. `%USERPROFILE%\.dsh\.credentials.yaml` 中的 `DEEPSEEK_API_KEY` —— 装了 DeepSeek Harness 并登录过就自动有

不填同样可用：双击互动、天气、新闻都正常，仅联网对话与余额不可用。新闻与天气走公开接口，不需要 Key。

## 配置 `config.json`

```json
{
  "city": "烟台",
  "lat": 37.4638,
  "lon": 121.4479,
  "show_stats": true,
  "show_weather": true,
  "bubbles": null
}
```

| 键 | 含义 |
| --- | --- |
| `city` / `lat` / `lon` | 天气城市与坐标；在对话里直接说城市名会自动改写这里 |
| `show_stats` | 关掉后双击不再抽到 token / 余额 |
| `show_weather` | 关掉后不自动播报天气 |
| `bubbles` | 自定义台词数组，`null` 使用内置 12 句 |

## 数据文件

全部保存在 `%LOCALAPPDATA%\desktop-pet\`：

| 文件 | 作用 |
| --- | --- |
| `pos.json` | 上次拖动的窗口位置 |
| `memory.json` | 参与对话的上下文与长期事实（删掉即失忆） |
| `history.log` | 完整对话流水（JSON 行，不受删除 `memory.json` 影响） |

API Key 只在内存中使用，不写日志、不落盘。

## 目录结构

```
app.py                主程序
DanicaPet.spec        PyInstaller 打包配置
version_info.txt      exe 版本信息
icon.ico              应用图标
assets/               人物素材与交互配置
zstd/                 zstd.exe（解压 DSH 会话日志用）
使用说明.txt          面向使用者的简版说明
功能说明.md           完整功能与实现说明
安装快捷方式.cmd      仅创建桌面快捷方式，不启动程序
```

## 已知问题

- Windows Defender 可能报 `Trojan:Win32/Bearfoos.B!ml`，这是 PyInstaller 打包的常见误报；把解压目录加入排除项即可。
- 个别自绘全屏的程序可能逃过全屏判定，反馈具体程序名可针对性修复。

## 免责声明

所有分享资源仅用于个人学习，禁止商用；版权归属原权利人。若存在侵权，请联系删除。
下载与使用该资源带来的一切风险由使用者自行承担，分享者不承担任何法律责任。