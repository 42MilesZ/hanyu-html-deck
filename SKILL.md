---
name: hanyu-html-deck
description: Use when creating or revising a local-first HTML presentation with speaker notes, an optional notes drawer, export tools, source write-back, or a phone teleprompter.
---

# Hanyu HTML Deck（本地演示台）

使用本 skill 创建或修改 HTML 演示文稿时，以本 skill 目录内的 `assets/hanyu-html-deck/index.html` 为底座，不从空白页面重新搭引擎。下文的相对路径都以本 skill 目录（即仓库根）为起点；skill 装在别处时，先定位到该目录再执行命令。

模板提供的是演示引擎与页面骨架，不是要照搬的视觉方案。示例页只作结构参考，版面按当次内容重新组织。

本 skill 可以与已有的 PPT / slides 内容 skill、演讲结构 skill 或视觉设计 skill 串联，也可以由一个主 skill 统一路由。组合时让其他 skill 负责内容与视觉判断，本 skill 负责最终 HTML 结构、讲稿、交互、写回和导出；引用已有规则，不在本 skill 内复制它们。

## 开始前

1. 如果目标目录还没有演示稿，在本 skill 目录下运行：

   ```bash
   python3 scripts/create_deck.py /目标目录
   ```

生成目录只包含可运行 Deck，不复制本仓库的维护说明、许可证汇总或内部合同。功能边界与使用方法以仓库根目录的 `README.md` 为准。

## 能力边界

- 本 skill 负责 1920 × 1080 HTML 演示引擎、讲稿与备注、制作端大纲、章节时间轴、归档、手机提词、源文件写回和导出。
- 它不提供主题皮肤、成套视觉模板或业务版式。内容取舍、叙事和视觉设计由相应 skill 决定，本 skill 只承接最终运行结构。
- 六页示例是最小可运行骨架，不是需要复用的视觉模板。制作新稿时按真实内容重写画布结构。

## 页面制作

- 所有页面使用 `.slide > .canvas + aside` 结构，`.canvas` 紧跟 `<aside>`（写回按这个约定定位，别打破）。
- 每页必须有唯一且稳定的 `data-slide-id`；新增页使用新 ID，插入、重排或归档时不重编号旧页。
- 每页用 `data-part` 声明一级章节，用 `data-outline` 提供制作端简短页名。两者驱动左侧大纲和底部章节时间轴。
- 页面正文服务于演讲，不把讲稿压到画布上。
- Deck 的非内容性文字默认使用英文，包括工具栏、速度单位（`min` / `chars/min`）、hover 说明、导出菜单与状态提示。
- PPT 内容以主要受众的语言为主；每页选择最重要的 1–2 处（通常是标题、关键结论、核心卖点或关键数据）使用中英双语，英文短而可扫读，不把每个辅助标签都机械翻译一遍。
- 讲稿写在 `.ns` 中，使用中英双语自然段；中文与对应英文分别成段，每个意思单独成段，不强制项目列表。
- 备注写在 `.nc` 中。它既可保存修改意见，也可保存补充说明或个人提醒。
- 每页都有且只有一个 `.ns` 和一个 `.nc`，顺序不变；`.ns` 是演讲者讲稿，`.nc` 是出处、问题、参数和个人提醒。
- `deck-content.json` 是讲稿与备注的协作真源，HTML 中的 `.ns/.nc` 只是离线种子。不要直接编辑内容仓。
- AI 修改讲稿或备注时，本地演示台必须保持运行；先执行 `python3 scripts/deck_content.py show` 经服务读取修订号，再用 `patch --slide-id ... --field script|note --base-revision ... --value-file ...` 提交。
- 普通入场挂在 `.slide.on` 下，并为 `.ovItem`、`body.exporting` 和 `body.raw` 提供静态终态。
- 页内自动状态使用 `data-steps`、`data-step` 与可选的 `data-autostep`。演讲者输入只负责翻页；需要独立停留讲述的状态拆成单独页面。

## 交互与状态

- 讲稿面板默认收起到表头；备注抽屉默认关闭。
- 两种状态按 `DECK.key` 分别写入 localStorage，不互相覆盖。
- 归档页码使用 `<key>.archived`，对应源文件基线使用 `<key>.archived.source`；只有基线仍匹配当前源文件时才采用浏览器缓存，避免旧会话反向覆盖新状态。
- localStorage 一律走模板内的安全包装，不裸调用：禁用存储或配额写满时要降级，不能白屏。
- 讲稿与备注各自维护版本历史，不共用一条时间线；所有草稿、缓存与历史按稳定页 ID 和字段关联。
- 讲稿与备注的输入立即保存到浏览器，停止输入 3 秒后通过 `/content/patch` 写回 `deck-content.json`；把一栏删空也必须作为有效修改写回。
- 浏览器聚焦字段时使用 8 秒短租约，写入携带字段修订号；423/409 时保留本地草稿，不静默覆盖另一方更新。
- 两栏共用表头的 `Saved` / `Saving…` / `Offline` / `Reconnect` / `Error` 状态；服务端拒绝写回时必须显示具体原因，不能继续伪装成 `Saving…`。写回前清理粘贴产生的非白名单格式，但保留文字、段落、列表和基本强调。
- 手机端默认打开讲稿；备注通过 `Script / Notes` 切换显示。
- 制作端大纲只在默认模式显示；底部时间轴按 `data-part` 形成章节底面，页面片段至少 32px，空间不足时等分降级。语速只改变时长数字，不改变时间轴长度。
- 时间轴悬停预览直接克隆当前页 DOM，不依赖导出缓存；打开手机提词器后才在后台准备手机缩略图与分步帧。
- 手机端只使用同一局域网。首选同一 Wi-Fi；没有可用网络时，使用手机热点并让电脑连接。
- 不接入公网中继、公共 MQTT 或托管提词页。

## 本地服务

本地服务负责手机提词、遥控、源文件写回、图片/PDF/发送版导出。修改这部分时保留以下边界：

- 写侧与桌面控制端点（包括 `/archive`、`/content`、`/content/lease`、`/content/patch`、`/canvas`、`/export`、`/notes`、`/flip`、`/info`、`/qr.svg`）要求回环请求且携带访问凭据。
- 凭据由服务启动时写进 `index.html` 的 `/* HANYU_TOKEN */` 锚点行、停止时清空。不要改成经打开地址传递：macOS 的 `open` 会丢掉 `file://` URL 上的 query 与 fragment，页面永远拿不到。
- 手机侧端点（`/p`、`/notes.json`、`/events`、`/thumbs`、`/steps`、`/goto`、`/phone-heartbeat`）接受回环或携带凭据；凭据只经二维码交给手机，接口不回传含凭据的链接。
- 所有请求校验 `Host` 是否指向本机（堵 DNS rebinding），并只回显白名单内的 `Origin`；未登记的路径默认拒绝。
- 写回内容用 HTML 分词器逐 token 校验标签与属性白名单，不用正则——正则的属性区会被引号里的 `>` 截断，事件属性会漏过去。
- 写回必须先核对页数与结构，按 div 开闭配平定位区块，再用临时文件原子替换。
- 手机讲稿只在局域网传输，不上传到第三方服务。
- 自动化截图默认不向手机上报翻页；显式加 `?pr=1` 才启用联动。

## 完成前检查

1. 在本 skill 目录（仓库内）开发时，运行 `python3 -m unittest discover -s support/tests -v`。
2. 在桌面视口检查默认、总览、演示、讲稿展开、备注抽屉，并确认控制台无报错。
3. 在手机视口检查讲稿/备注切换、翻页、自由浏览和滚动位置。
4. 启动本地服务，验证二维码、事件流、以及非回环请求与注入载荷都被拒绝。
5. 归档一页后确认正常翻页、手机提词与各类导出都跳过它，恢复后顺序复原。
6. 导出发送版，确认归档页、`.nc` 备注、画布写回代码都已剥除，且不再向本地服务发请求。

修改模板、引擎、本地服务或导出脚本时，还必须读取 `assets/hanyu-html-deck/AGENTS.md` 的维护合同。
