# Hanyu HTML Deck 引擎维护约定

本文件只适用于修改当前目录内的模板、引擎 JS、导出脚本、画布写回、手机提词或本地服务。普通演示稿制作使用仓库根目录的 `SKILL.md`，不需要读本文件。

这是引擎资产的内部说明。`scripts/create_deck.py` 必须在复制新 deck 时排除本文件。

## 1. 核心结构不变量

- 布局盒固定为 1920×1080，`fitSlide()` 只缩放视觉。`#stage { overflow:hidden; }` 不得删除，否则窄视口会产生横向滚动。
- 每页保持 `.slide > .canvas + aside`，`.canvas` 紧跟 `<aside>`。服务端使用这个兄弟锚点定位写回边界。
- 每页必须有唯一且不随页序变化的 `data-slide-id="slide-NNN"`。新增页分配新 ID，不因插入、归档或重排给旧页重新编号。
- 每页始终有一个 `.ns` 和一个 `.nc`，顺序与页数一致。
- 表格源码显式包含 `<tbody>`，SVG 的 `<path>` 使用成对标签。源文与浏览器序列化结果保持一致，避免第一次写回产生无关 diff。

## 2. 动画、翻页与导出终态

- 入场动画挂 `.slide.on`，不挂 `.current`。`.on` 在离场 450ms 内仍然存在，确保快速翻页时动画不跳到终态。
- 初始隐藏态与 keyframes 只出现在 `.slide.on` 或 `.slide.current` 下，并为 `.ovItem`、`body.exporting` 和 `body.raw` 提供完整终态。
- `export_pages.py` 截图前注入 FF_CSS，将动画和过渡压到 1ms。不依赖自然等待动画结束。
- `data-steps` 默认以 420ms 间隔自动推进，`data-autostep` 只覆盖间隔；所有演讲者输入都直接翻页。导出时用运行态 `data-stepfreeze="1"` 冻结自动推进，不把它写进业务页面。
- 自动化实例在 `navigator.webdriver` 下不上报、不监听手机翻页。需要测试联动时显式使用 `?pr=1`。

## 3. 画布就地编辑与序列化

- 画布编辑区在 `CVEDIT-START` 与 `CVEDIT-END` 标记之间。`build_send.py` 必须剔除该区。
- 双击画布进入编辑，Enter 转为 `<br>`，Esc 放弃本次改动，paste 与 drop 只保留纯文本。
- `serializeCanvas` 必须剔除所有运行时注入的 DOM。新增页脚、拆字 span、预览标记或临时层时，同步更新序列化剔除列表。
- 画布写回前检查 div 开闭配平、内容长度下限和浏览器上报页数。浏览器 DOM 只是打开时快照，页数不一致就拒绝覆盖源文件。
- 定位画布结尾使用 `</div>\s*<aside>` 兄弟锚点，不通过正则计数嵌套 `<div>`。

## 4. 讲稿、备注与历史

- `deck-content.json` 是讲稿与备注的编辑态真源；`index.html` 中的 `.ns/.nc` 只作为断开本地服务时的离线种子。导出脚本必须先用内容仓覆盖种子。
- 浏览器与 AI 都通过 `prompter_server.py` 的 `/content/patch` 写入。AI 先运行 `deck_content.py show` 读取字段修订号，再用 `deck_content.py patch` 提交；不得直接改 `deck-content.json` 或把 `.ns/.nc` 当作协作写入口。
- 同一页的讲稿与备注是两个独立字段。浏览器聚焦时持有 8 秒短租约并续期；写入带字段修订号。423/409 时保留浏览器草稿，不静默覆盖另一方更新。
- `/events` 的 `content` 事件把成功写入推给其他浏览器。没有本地草稿且字段未聚焦时立即刷新；有本地草稿时不覆盖。
- 讲稿使用 `canonNs` 判定改动，必须保留段落 class 和行内加粗。备注使用 `canon`。不退回纯文本比较，否则只改层级、分段或加粗会被误判为无改动。
- 粘贴讲稿时先识别嵌套列表和行首缩进，再净化字号、字色、背景和斜体。备注只保留段落与加粗。
- 完全清空一栏也是有效修改。使用再次规范化为空的 `<p><br></p>` 写回，并清理本地待保存标记。
- 服务端拒绝必须进入 `Error` 终态并显示原因，不得永久停在 `Saving…`。
- 讲稿和备注各自保存一条上限 30 条的时间线，同页同栏一分钟内的改动合并。恢复历史前先保存当前稿。
- 时间轴页片段的几何宽度下限为 32px；达到下限的短页固定宽度，剩余宽度继续按讲稿时长分配。当可用宽度小于页数 × 32px 时等分降级，不允许片段重叠或溢出。

## 5. localStorage 与迁移

所有键使用 `DECK.key` 前缀。主要键包括：

- `.draft.<tab-id>.<slide-id>.script` / `.draft.<tab-id>.<slide-id>.note`：尚未同步的浏览器草稿；每次页面实例使用新 ID，刷新会复制上一实例草稿，复制标签页也会分叉而不共用写键；同时自动迁移旧共享键与 `.s.N/.c.N`。
- `.cache.<slide-id>.<field>` / `.revision.<slide-id>.<field>`：这个浏览器最后见过的共享内容与字段修订号；服务离线时刷新仍用它恢复。
- `.history.<slide-id>.script` / `.history.<slide-id>.note`：两栏历史。
- `.archived` / `.archived.source`：归档页和源文基线。
- `.ui.panelExpanded` / `.ui.notesDrawerOpen`：面板状态。
- `.rate` / `.nh` / `.dw`：语速、面板高度和抽屉宽度。

页序变化不再使讲稿、备注或历史错位，它们按稳定页 ID 关联。其他浏览器状态仍使用 `DECK.key` 前缀；只修改个别页时使用幂等的一次性迁移标记。localStorage 通过安全包装访问，禁用存储或配额耗尽时降级到内存，不让页面白屏。

## 6. 本地服务安全边界

- 写侧与桌面端点 `/archive`、`/content`、`/content/lease`、`/content/patch`、`/canvas`、`/export`、`/notes`、`/flip`、`/info`、`/qr.svg` 要求回环请求且携带凭据。`/seed` 仅保留旧 deck 兼容，不作为新写入口。
- 凭据在服务启动时写入 `var TOKEN = '…'; /* HANYU_TOKEN */` 锚点行，停止时清空。不经过 `file://` 查询或 fragment 传递，macOS `open` 会丢失它们。
- 所有请求检查 `Host` 是否指向本机，只回显白名单 `Origin`，未登记路径默认拒绝。
- 服务实现 `do_OPTIONS` 放行 CORS 预检。`file://` deck 发送 JSON POST 会先发 OPTIONS。
- `/seed` 和 `/notes` 使用同一套 HTML 分词器白名单，不用正则解析属性。`/canvas` 允许 div，改为拒绝危险标签、`on*=` 事件属性、不配平结构和异常长度。
- 内容写回使用单一串行锁和临时文件 `os.replace` 原子替换；字段租约只驻留内存，服务重启后自动释放。
- 手机讲稿只在可信局域网传输，不接入公网中继、公共 MQTT 或托管提词页。

## 7. 手机提词、同步与预览缓存

- 服务经 SSE `/events` 向桌面端发 `cmd`，向手机端发 `state`、`notes` 和 `preview`。
- 手机翻页与键盘使用同一个 `next()/prev()` 路径；总览跳页直接 `go(page)`。
- 同步序号 `seq` 从启动时的 Unix 秒数开始并单调递增，page/step 跨重启持久化。不从 0 重新计数，避免重启后手机回到第一页。
- 手机缩略图从 `导出图片/` 按 mtime 生成 640px 缓存。分步预览由 `export_steps.py` 生成，缺少时回退普通页面缩略图。
- 只有用户打开手机提词器后才在后台准备缩略图与分步帧。画布写回或归档变化后防抖重建，失败不影响讲稿、备注和遥控。

## 8. 脚本责任

- `create_deck.py`：复制干净模板，不带凭据、运行产物、本文件或模板运行过的内容仓，并从新 deck 的 HTML 种子重新初始化 `deck-content.json`。
- `deck_content.py`：初始化/读取内容仓，并让 AI 通过本地服务安全提交带修订号的字段更新。
- `export_pages.py`：先加载内容仓，再导出活动页终态和 notes.json，跳过归档页。
- `export_steps.py`：通过引擎的 `window.hanyuFreezeStepsForExport()` 冻结自动计时器，再导出分步帧缓存。
- `build_img_pdf.py`：将导出图片合成纯图 PDF。
- `build_pdf.py`：生成页面与讲稿对照 PDF。
- `build_send.py`：先将内容仓水合进 HTML，再剔除归档页、`.nc`、CVEDIT 代码和本地请求，压缩并内联图像与字体。
- `prompter_server.py`：本地写回、提词、遥控、事件流和导出调度。

## 9. 修改引擎后的验收

```text
□ 默认、总览、演示、1:1、讲稿面板和备注抽屉模式正常
□ 画布修改只产生预期源文 diff，运行时 DOM 没有被写回
□ 讲稿与备注的文本、分段、层级和加粗可以保存、清空、恢复和重连
□ 浏览器与 AI 可分别改不同字段；同字段租约与 409 修订冲突均不丢本地草稿
□ 刷新、服务重启、页序调整后仍按 data-slide-id 加载同一页内容
□ 页数不一致、危险标签、事件属性和异常长度会被拒绝
□ CORS 预检、Host 校验、Origin 白名单和凭据校验生效
□ 手机提词、遥控、SSE 重连和分步预览正常
□ 归档页在翻页、页码、时间轴、手机和所有导出中排除，恢复后顺序复原
□ 发送版不含归档页、.nc、CVEDIT、凭据和本地服务请求
□ create_deck.py 产物不含 AGENTS.md、凭据、运行状态和导出中间物
```
