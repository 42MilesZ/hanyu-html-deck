# Hanyu HTML Deck（本地演示台）

[中文](README.md) · [English](README.en.md)

面向 AI 生成 HTML 演示文稿的本地优先框架。

本地演示台同时提供一个可直接复制的演示模板和一个独立 skill。核心 HTML 不需要安装、账号或网络；双击文件即可演示。开启本地服务后，可使用手机提词器、遥控、源文件写回和导出。

## 是什么

本地演示台提供的是演示能力与制作流程：翻页、分步动画、讲稿、备注、手机提词、源文件写回和导出。

它不是一套幻灯片视觉模板，不提供主题皮肤、配色方案或成套版式。仓库里的 `assets/hanyu-html-deck/index.html` 是一个可运行的起点，其中的示例页只是页面骨架；真正的版面由 AI 按每份内容重新组织。如果需要的是现成好看的版式套件，这个项目不解决这个问题。

## 界面预览

<table>
  <tr>
    <td width="50%" align="center"><img src="support/readme-assets/workspace.png" alt="完整演示台" width="420"><br><sub>完整演示台 · Complete workspace</sub></td>
    <td width="50%" align="center"><img src="support/readme-assets/ai-generate.png" alt="AI 生成整场演示" width="420"><br><sub>AI 生成整场演示 · Full-deck generation</sub></td>
  </tr>
  <tr>
    <td width="50%" align="center"><img src="support/readme-assets/direct-edit.png" alt="在页面上直接修改" width="420"><br><sub>在页面上直接修改 · Direct canvas editing</sub></td>
    <td width="50%" align="center"><img src="support/readme-assets/export-deliver.png" alt="导出与交付" width="420"><br><sub>导出与交付 · Export-ready delivery</sub></td>
  </tr>
  <tr>
    <td width="50%" align="center"><img src="support/readme-assets/closing.png" alt="演示封尾" width="420"><br><sub>演示封尾 · Closing slide</sub></td>
    <td width="50%" align="center"><img src="support/readme-assets/phone-prompter.png" alt="手机提词与遥控" width="180"><br><sub>手机提词与遥控 · Phone prompt &amp; control</sub></td>
  </tr>
</table>

## 适合什么情况

- 使用 Codex、Claude Code 等 AI 编程工具制作 HTML 演示文稿。
- 希望把页面、讲稿和修改备注放在同一个文件中。
- 正式演示时需要手机提词和遥控，但不希望依赖公网服务。
- 需要从浏览器把文字修改安全地写回原始 HTML。

## 功能边界

| 功能 | 只打开 HTML | 需要本地服务 |
|---|:---:|:---:|
| 浏览、翻页、总览、演示模式 | ✓ | ✓ |
| 页面内分步动画与悬停交互 | ✓ | ✓ |
| 编辑讲稿与备注并保存在浏览器 | ✓ | ✓ |
| 记住讲稿面板和备注抽屉状态 | ✓ | ✓ |
| 导出讲稿、复制改动的备注 | ✓ | ✓ |
| 手机提词器与手机遥控 | | ✓ |
| 把讲稿、备注和画布文字写回源文件 | | ✓ |
| 导出每页图片、导出 PDF、导出单独发送版 | | ✓ |

本地服务只在当前局域网内工作，不连接公共中继，不上传讲稿。手机与电脑不在同一网络的情况不在本项目范围内。

## 快速开始

直接复制给 AI：

```text
请读取 https://github.com/42MilesZ/hanyu-html-deck 并使用其中的 Hanyu HTML Deck Skill，把［内容或文件］制作成一份面向［受众／场合］的［页数］页 HTML 演示稿，并输出到［目标目录］。重要信息和逐页讲稿使用中英双语。
```

或手动创建：

```bash
git clone https://github.com/42MilesZ/hanyu-html-deck.git
cd hanyu-html-deck
python3 scripts/create_deck.py ~/Documents/my-deck
```

然后：

1. 双击 `my-deck/启动本地演示台.command`：它会启动本地服务，并打开演示稿。
2. 修改文件尾部的 `DECK.name` 与 `DECK.key`。
3. 用模板里的页面骨架替换示例内容。
4. 只想离线看一眼时，直接双击 `index.html` 也可以，此时不写回源文件。

核心 HTML 可在 macOS、Windows 和 Linux 的现代浏览器中使用。0.1 版的本地服务、启动文件与导出流程只在 macOS 上验证过：图片、PDF 与发送版导出依赖 macOS 自带的 `sips`，在 Windows 与 Linux 上不可用；这些系统上可用 `python3 scripts/prompter_server.py` 启动服务使用手机提词与写回。

## 安装 Skill

Skill 让 AI 编程工具直接按本项目的约定生成演示稿。两种用法：

- 装成常驻 skill：把仓库里的 `SKILL.md` 连同仓库一起放到 AI 工具读取 skill 的目录（例如 `~/.claude/skills/hanyu-html-deck/`），并在其中保留 `assets/` 与 `scripts/`，Skill 里的相对路径才成立。
- 不安装也能用：让 AI 读取仓库里的 `SKILL.md`，再说明目标目录即可。

调用时给出内容、场合与页数，并明确要求使用本地演示台 Skill。

### 与 PPT / Slides Skill 组合

本地演示台可以和已有的 PPT、slides、演讲结构或视觉设计 skill 一起使用。前者负责内容取舍、叙事节奏与页面创意，本地演示台负责把结果装进可演示、可提词、可写回、可导出的 HTML 运行框架。一个常见顺序是：

1. PPT / slides skill 整理结构、页序与每页结论。
2. 视觉设计 skill 决定每页的视觉主体、版式与动效。
3. 本地演示台 Skill 以 `assets/hanyu-html-deck/index.html` 为底座完成页面、逐页讲稿和交互。

这些能力也可以放进同一个主 skill 中使用：在主 `SKILL.md` 里写明内容、视觉与演示台的执行顺序，并引用各自已有的规则和资源；最终始终由本地演示台模板承接运行与导出。这样只需调用一个 skill，也不会重复维护多份演示引擎。

例如：

> 使用我的 slides 内容规则完成 6 页结构，再按视觉设计规则制作页面，最后用 Hanyu HTML Deck 生成可直接演讲的 HTML；工具界面使用英文，重要内容和逐页讲稿使用中英双语。

### 语言约定

- Deck 的非内容性文字默认使用英文，包括工具栏、速度单位（如 `min`、`chars/min`）、所有 hover 说明、导出菜单和状态提示。
- PPT 内容以主要受众的语言为主；标题、结论、数据或核心卖点等重要信息使用中英双语，英文保持短而可扫读，默认使用 `200` 字重；作为主视觉的英文品牌名或产品名可使用 `600`。
- 每页演讲稿使用中英双语，中文与对应英文分别成段并依次讲述；时长估算会同时计算两种语言。

## 讲稿与备注

底部区域默认只显示一行表头。按 `N` 或点击中间把手可展开讲稿。讲稿使用自然段纯文本，不要求目的、主次或项目列表。

展开后，讲稿栏右下角有一个侧栏图标，点击后备注抽屉从右侧推入，再点一次收起。拖动抽屉左边缘可以左右调整备注区宽度，宽度会被记住。备注可用于修改意见、补充说明或个人提醒。收起抽屉只切换视图，内容不会删除。

讲稿面板是否展开、备注抽屉是否打开会分别写入 localStorage，并按 `DECK.key` 隔离。

导出菜单中：

- `Export script`：下载包含全部页面讲稿的 Markdown 文件。
- `Copy changed notes`：只复制用户改过的备注，按页分组，便于粘贴给 AI。
- `Export page images`：逐页截图成 PNG，需要本地服务与 Playwright。
- `Export PDF`：先逐页截图再合成 PDF，版面与动效终态一致。
- `Export standalone HTML`：单文件 HTML，内联字体与图片，剥除备注和写回代码。
- `Use 1:1 pixels`：关闭画布缩放，供 Figma 插件或 DOM 抓取工具读取 1920 × 1080 的真实坐标。

菜单里每一项悬停约 0.2 秒会显示一句说明。

## 手机提词器

先双击 `启动本地演示台.command`，再点击演示稿右上角的手机图标。界面会显示当前局域网地址和二维码。网络发生变化后，二维码会自动刷新。

推荐连接顺序：

1. 手机和电脑连接同一个可信 Wi-Fi。
2. 没有可用 Wi-Fi 时，开启手机热点，并让电脑连接这个热点。

手机端默认显示讲稿；点击顶部 `Script / Notes` 可切换。两栏分别保留每一页的滚动位置。手机可跟随电脑翻页，也可切换成自由浏览。

正式演示前 5–10 分钟：

1. 扫码打开提词器。
2. 用手机前后翻两页，确认电脑同步。
3. 关闭手机和电脑的 VPN 或代理。
4. 避免自动锁屏，并让手机保持供电。

## 本地服务与依赖

手机提词、遥控和源文件写回只需要 Python 3，QR 生成器已经随项目提供。

图片和 PDF 导出还需要：

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

发送版 HTML 不需要 Playwright。发送版会内联字体和图片，并剥除备注与浏览器写回代码。

## 浏览器写回

- 讲稿与备注的改动会立即保存在浏览器中；本地服务在跑时，停止输入 3 秒后自动写回 `index.html`，不需要点保存。
- 服务没在跑时不写回：改动实时存在浏览器里（刷新不丢），保存状态会说明原因；服务起来后再改任意一个字即自动补写。
- 为什么要凭据：浏览器里的任意网页都能伪装成本地文件（`Origin: null`）向本机服务发请求，只靠"来自本机"判断挡不住它。服务启动时会把一次性凭据写进 `index.html`（停止时自动清除），写回、导出与手机提词都要求它，其他网页拿不到。
- 因此页面要在服务启动之后打开。若页面先开着、服务后启动，保存状态会提示刷新一下页面。启动脚本本身会等服务就绪再打开演示稿。
- 面板表头共用一个保存状态：`Saved` 表示讲稿与备注都已写回，`Saving…` 表示改动已在浏览器中、正等待写回，断开时显示 `Offline` 或 `Reconnect`。悬停会列出尚未写回的页面与内容类型。
- 讲稿与备注各有一个历史按钮和独立版本时间线，可回到任一历史版本或默认稿。
- 双击画布文字可直接修改，失焦后写回源文件。
- 写回只接受本机且持凭据的请求；写回前会核对页数、页面结构，用 HTML 分词器按标签与属性白名单校验内容，再用临时文件原子替换。

## 键盘

- `← / →`：上一页 / 下一步或下一页
- `P` 或 `F`：演示模式
- `O`：总览
- `N`：展开或收起讲稿
- `R`：切换为 1:1 像素
- `Esc`：退出当前模式

## 仓库里有哪些文件

`scripts/create_deck.py` 会把普通用户真正需要的模板、字体、本地服务和说明复制到新项目中。源码仓库将维护文件收拢在 `support/`，它们不会进入生成出的 Deck：

- `support/tests/`：检查页面与讲稿一一对应、状态分开保存、局域网边界和产品文案，避免后续修改破坏已有功能。
- `support/evals/`：检查 AI 是否能按 Skill 的约束生成合格的 Deck。
- `support/THIRD_PARTY_NOTICES.md`：记录内置字体与 QR 生成器的第三方许可；生成 Deck 时会复制到其根目录。
- `.github/workflows/ci.yml`：每次提交后自动运行测试。

## 开源许可

项目原创代码、模板和 skill 使用 [MIT License](LICENSE)。字体和 QR 生成器的许可见 [第三方声明](support/THIRD_PARTY_NOTICES.md)。
