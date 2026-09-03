# Hanyu HTML Deck 引擎维护契约

## 1. 角色、范围与事实源

本文件是 Hanyu HTML Deck 共享引擎的维护契约。只有在修改模板引擎、内容仓、本地服务、画布写回、手机提词、导出链路或生成流程时读取；普通演示稿制作读取承载当前资产的上层制作合同：独立项目中为根目录 `SKILL.md`，Visual Design Skill 中为 `references/ppt-html-deck.md`。

Hanyu HTML Deck 独立项目是引擎代码、维护契约和测试的事实源；`visual-design/assets/hanyu-html-deck/` 是随 skill 分发的镜像。通用引擎行为先在独立项目实现和验收，再同步镜像，不在两边分别演进。公开引擎保留用于文档和回归测试的六页最小产品演示，但 Visual Design Skill 的额外模板库、视觉规则、真实项目图片、业务版式和模板 Note 不进入公开引擎。

`<repo-or-skill-root>/scripts/create_deck.py` 必须排除本文件。生成出的业务 Deck 不需要读取引擎维护契约。

## 2. 页面身份与源文结构

- 布局盒固定为 1920×1080，`fitSlide()` 只缩放视觉。`#stage { overflow:hidden; }` 不得删除，否则窄视口会产生横向滚动。
- 每页保持 `.slide > .canvas + aside`，`.canvas` 紧跟 `<aside>`；服务端依赖这个兄弟锚点定位写回边界。
- 每页必须有非空、唯一且创建后不变的 `data-slide-id`。新页推荐使用 `slide-NNN`，但代码不得把格式当作合法性条件。
- 禁止用当前页序生成持久化 ID。浏览器和 Python 内容仓必须在恢复草稿或写入前拒绝缺失、重复 ID，插页、重排和归档不得改变旧页面 ID。
- 每页始终有一个 `.ns` 和一个 `.nc`，顺序与页数一致。表格显式包含 `<tbody>`，SVG `<path>` 使用成对标签，避免浏览器首次序列化产生无关 diff。

## 3. 画布编辑与序列化

- 画布编辑区位于 `CVEDIT-START` 与 `CVEDIT-END` 标记之间，`build_send.py` 必须完整剥除该区。
- 双击画布进入编辑，Enter 转为 `<br>`，Esc 放弃本次改动，paste 与 drop 只保留纯文本。
- `serializeCanvas` 必须移除所有运行时注入节点和属性。新增页脚、拆字 span、预览标记或临时层时，同步更新序列化剔除逻辑。
- 画布写回前检查页面数量、div 配平、危险标签、事件属性和异常长度；浏览器 DOM 只是打开时快照，页数不一致时拒绝覆盖。
- 定位画布结尾使用 `</div>\s*<aside>` 兄弟锚点，不用正则计数嵌套 `<div>`。

## 4. 讲稿、备注与协作一致性

- `deck-content.json` 是讲稿与备注的编辑态真源；`index.html` 中的 `.ns/.nc` 只是离线种子，导出脚本先用内容仓水合种子。
- 浏览器与 AI 都经 `prompter_server.py` 的 `/content/patch` 写入。AI 先用 `deck_content.py show` 读取字段修订号，再用 `deck_content.py patch` 提交；不得直接编辑内容仓。
- 讲稿和备注是独立字段。浏览器聚焦时持有 8 秒短租约并续期，写入携带字段修订号；423/409 时保留本地草稿，不静默覆盖更新。
- `/events` 的 `content` 事件只在目标字段没有本地草稿且未聚焦时刷新浏览器。
- 草稿、缓存、修订号和历史全部按稳定 slide ID 与字段关联。旧 `.s.N/.c.N` 只作为一次性迁移来源，不得成为新的持久化键。
- `canonNs` 必须保留讲稿段落类型与行内加粗；备注使用 `canon`。清空一栏也是有效修改，以 `<p><br></p>` 安全写入并清理 pending 状态。
- 服务端拒绝必须进入 `Error` 终态并显示原因，不能永久停在 `Saving…`。
- 图片、PDF 与发送版从磁盘内容仓生成；启动这些导出前必须保存当前草稿、等待既有写入链、完成最新 patch，并确认没有 dirty draft、租约冲突、修订冲突、离线或凭据错误。失败时停止导出，不得固化旧讲稿。

## 5. 导航、动画与静态终态

- 入场动画挂在 `.slide.on`，不挂 `.current`；旧页保持完整不透明托底，直到新页 canvas 的真实入场结束。
- 初始隐藏态与 keyframes 只出现在 `.slide.on` 或 `.slide.current` 下，并为 `.ovItem`、`body.exporting` 和 `body.raw` 提供完整终态。
- `data-steps` 默认按 420ms 自动推进，`data-autostep` 只覆盖间隔；所有演讲者输入只翻页。导出使用运行态 `data-stepfreeze="1"` 冻结计时器，不把它写进业务页面。
- 快速连按进入导航队列；倒翻与连续翻页都不得产生透明空窗、共享对象消失帧或旧回调破坏新状态。
- `export_pages.py` 截图前注入 FF_CSS，将动画和过渡压到 1ms，不依赖自然等待。
- 自动化实例在 `navigator.webdriver` 下不上报、不监听手机翻页；需要测试联动时显式使用 `?pr=1`。

## 6. 制作端大纲与章节时间轴

- `data-part` 驱动一级章节，`data-outline` 提供制作端简短页名；归档页同时从大纲、时间轴和活动序列排除。
- 大纲只在默认制作态显示，开关与宽度分别存入 `.ui.outlineOpen` 和 `.ui.outlineWidth`；演示、总览、1:1、导出与发送版隐藏。
- 时间轴始终占满标题、语速和保存状态之间的可用宽度；语速只改变时长数字，不改变几何长度。
- 页面片段宽度下限为 32px；短页达到下限后固定，剩余空间继续按讲稿时长分配。可用宽度小于页数 × 32px 时等分降级，不允许重叠或溢出。
- 时间轴悬停预览克隆当前真实 canvas，不依赖可能过期的导出缩略图。

## 7. localStorage、安全与交付边界

- 所有键使用 `DECK.key` 前缀。主要状态包括 `.draft.<tab-id>.<slide-id>.<field>`、`.cache.<slide-id>.<field>`、`.revision.<slide-id>.<field>`、`.history.<slide-id>.<field>`、`.archived`、`.archived.source`、`.ui.*`、`.rate`、`.nh` 与 `.dw`。
- localStorage 通过安全包装访问；禁用存储或配额耗尽时降级到内存，不让页面白屏。
- 写侧与桌面端点要求回环请求并携带凭据。凭据只写入 `var TOKEN = '…'; /* HANYU_TOKEN */` 锚点，停止服务时清空；不经 `file://` query 或 fragment 传递。
- 所有请求校验 Host，只回显白名单 Origin；`do_OPTIONS` 处理 `file://` JSON POST 的 CORS 预检，未登记路径默认拒绝。
- 内容写回使用 HTML tokenizer 白名单、单一串行锁和 `os.replace` 原子替换；字段租约只驻留内存，服务重启后释放。
- 手机讲稿只在可信局域网传输，不接入公网中继、公共 MQTT 或托管提词页。
- 发送版必须剥离归档页、`.nc`、CVEDIT、凭据和本地服务请求，并水合最新内容仓。
- `create_deck.py` 排除 AGENTS、模板运行过的内容仓、凭据、缓存、导出图片、发送版和 PDF 产物；从 HTML 种子重新初始化 `deck-content.json`，同时复制项目 `LICENSE`。字体和 vendored 依赖保留各自许可证。

## 8. 改动影响地图

| 修改对象 | 必须联动检查 |
|---|---|
| 页面 DOM | 画布写回、内容水合、序列化、总览、发送版 |
| 页面 ID | 浏览器草稿、缓存、历史、内容仓、插页与重排 |
| 讲稿/备注保存 | 租约、修订冲突、SSE、清空、导出前刷新 |
| 翻页/动画 | 键盘、手机遥控、自动步骤、倒翻、快速连按、静态终态 |
| 大纲/时间轴 | 章节、归档、窄视口、语速、hover 预览 |
| 运行时 DOM | `serializeCanvas`、写回 diff、总览、截图、发送版 |
| 本地端点 | token、Host、Origin、CORS、白名单与原子写入 |
| 生成脚本 | 凭据清除、内容仓初始化、LICENSE、运行残留 |
| 导出脚本 | 最新内容水合、归档过滤、隐私剥离、动画终态 |

## 9. 文件责任

- `index.html`：浏览器运行态、制作界面、导航、编辑与导出触发顺序。
- `scripts/deck_content.py`：内容仓初始化、读取、水合和带修订号的 AI patch。
- `scripts/prompter_server.py`：本地信任边界、串行写入、租约、事件流和导出调度。
- `scripts/deck_source.py`：HTML 源文结构、归档和发送版过滤。
- `scripts/export_pages.py` / `export_steps.py`：活动页终态与分步帧渲染。
- `scripts/build_img_pdf.py` / `build_pdf.py`：图片版和讲稿对照 PDF。
- `scripts/build_send.py`：内容仓水合、隐私剥离和单文件资产内联。
- 根目录 `scripts/create_deck.py`：从规范资产生成干净、合规的新 Deck。

## 10. 完成门槛

修改引擎后必须运行承载仓库规定的完整测试，并至少验证：

```text
□ 缺失或重复 data-slide-id 在 Python 与浏览器两侧均被拒绝，且编辑初始化未发生
□ 插页、重排、刷新和服务重启后，讲稿、备注、草稿与历史仍关联同一页面
□ 浏览器与 AI 可改不同字段；同字段租约和 409 冲突均不丢本地草稿
□ 清空内容可落盘；输入后立即导出时 /content/patch 先于 /export
□ 默认、大纲、总览、演示、1:1、讲稿面板和备注抽屉无控制台异常与布局破坏
□ 短页时间轴保持 32px；极窄空间等分且无重叠；语速不改变轴长
□ 快速连按、倒翻、自动步骤与导出终态无透明空窗或状态跳变
□ 页数不一致、危险标签、事件属性、错误 Host/Origin 和无凭据请求被拒绝
□ 手机提词、遥控、SSE 重连、归档和分步预览正常
□ 发送版不含归档页、.nc、CVEDIT、凭据或本地服务请求，并包含最新讲稿
□ create_deck.py 产物含 LICENSE 与新内容仓，不含 AGENTS、凭据、缓存或导出产物
□ 真实浏览器截图已检查；git diff --check 通过
```
