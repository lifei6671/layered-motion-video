# Cover Studio 浅色编辑器实施记录

## M0 — 审计与实施基线

2026-10-22，starting HEAD 见 `.cache/cover-studio-rebuild-baseline/HEAD.txt`。
该目录保存开工时的 staged/unstaged patch、完整 Git status、Cover Studio 源码 ZIP 和 SHA-256 清单。
恢复时只取 ZIP 中需要的文件；不要对整个仓库执行 reset。未提交、未推送。
已有 `.agents/skills/static-comic-video/`、根 README、DESIGN、docs、`.gitignore` 等修改均排除。
Stitch 目录、`templates/editor-build-required.html`、`tests/test_editor_build.py` 是开工前未跟踪文件，保留其原始内容。

| 当前事实 | 实际来源 | 决策 |
| --- | --- | --- |
| Flask 本机服务，默认 8765，start.bat → app.py | app.py / start.bat | 继续复用服务及启动方式 |
| 首页 Fabric.js 7.4，esbuild 0.28.2，原生 JS | fabric-poc/package.json / src/main.js | 新 React 编辑器独立构建，原 Fabric 入口保留 |
| 画面由 Fabric canvas 绘制，PNG 为 toDataURL | fabric-poc/src/main.js | 共享 React CoverArtwork，交互覆盖层独立 |
| 封面没有 Remotion 入口；视频渲染器锁定 4.0.515 | .agents/skills/static-comic-video/renderer/static-comic/package.json | 新增同版本 renderStill 适配器，不修改视频渲染器 |
| scene v2 含百分比定位、画幅变体、5 个基础层及 extras/groups | scene_models.py / free_layer_models.py | 迁移当前画幅为逻辑像素，保留原场景，原文件不覆盖 |
| data/designs/*.json，revision 冲突检查、原子写入 | scene_store.py | 新文档隔离到 data/documents，沿用原子写盘/素材 ID |
| data/preset.json 为 Pillow 模板 | app.py | 保持 /api/preset、/api/render 及 /legacy 原协议 |
| fonts 一级目录为家族；支持六种格式和元数据索引 | font_catalog.py / font_variants.py | 复用索引、字体文件白名单及 cmap 缺字检查 |
| 字体真实样张使用 Pillow，画布 FontFace | font_preview.py / fabric-poc/src/main.js | 搜索列表复用真实样张，选中/画布/Remotion 加载同一文件 |
| 旧版有选择/拖动/吸附/层级/样式/历史，无自动保存 | fabric-poc/src/main.js / history-manager.mjs | 复用几何吸附与历史模块；新增保存队列及恢复草稿 |
| unittest、Node test、Playwright 浏览器验证 | tests/ / fabric-poc/tests/ / run_checks.py | 旧接口回归 + 新模型/交互/正式导出与预览对比 |

设计稿 `stitch_cover_studio_editor/screen.png` 为 1600×1315；code.html 使用 56px header、72px rail、220px resource panel、约 290px inspector。
浅色 token 复用 DESIGN.md；保留中文、蓝色选中态、点阵工作区、悬浮工具条和底部缩放。
有意修正设计稿画布裁切：默认 fit 显示完整 16:9，滚动仅出现在手动放大后。

## 文件级阶段计划

| 阶段 | 文件 / 处理方式 | 验证与验收 |
| --- | --- | --- |
| M0 | 本记录、.cache 基线；只读审计现有模块 | Git 状态、源文件、设计图实际查看 |
| M1 | 新增 editor/src/model.ts、migration.ts、CoverArtwork.tsx、fonts.ts；复用 history-manager / snapping-engine | TS、迁移及几何模型测试；共享画面截图 |
| M2 | 新增 EditorHeader / ToolSidebar / ResourcePanel / CanvasWorkspace / FloatingToolbar / InspectorPanel、editor.css | 1366×768、1440×900、1920×1080 截图，设计 QA |
| M3 | 新增 InteractionOverlay、controller.ts；复用历史与吸附纯函数 | 不同 zoom 拖动、resize、IME 事件、键盘、undo/redo |
| M4 | 新增字体选择器与属性组件；复用 /api/fonts、font-preview、font、font-coverage | 字体切换、字重、文字测量、描边/阴影实际渲染 |
| M5 | 新增 document_store.py、cover_document.py、react_editor.py；app.py 接线；新增 remotion.tsx/render.mjs/build.mjs | 防抖/失败/冲突/重开恢复、模板复制、PNG/JPEG 实际尺寸 |
| M6 | 新增 editor/tests、tests/test_cover_document.py、run_editor_checks.py、design-qa.md | 新旧测试、预览/正式导出像素对比、流水线读取输出 |

## 交付边界

- 所有画面变化在浏览器即时完成；服务端仅承担资源、存储及明确发起的正式导出。
- 新文档带 schemaVersion、逻辑尺寸、图层顺序、像素 frame、字体文件 ID 与完整样式；旧百分比不进入新交互计算。
- Remotion 只渲染 CoverArtwork，导出前等待字体与图片，并执行字形覆盖检查；辅助线、选框、工具条不会导出。
- 历史中的 id/revision 不回退；保存成功响应只更新元数据，不覆盖保存期间的新编辑。
- 视觉/自动化通过不能替代用户对最终界面的主观验收；真实系统中文输入法与 composition 事件模拟分别报告。

## 阶段结果

M0: PASS。源码与设计稿已实际检查，基线归档完成，标题使用会话原始创建日期（Asia/Shanghai 1022）写入并核验。
以下结果为 2026-10-22 本机 Windows / Microsoft Edge 实际执行。源码位于本目录；生成的截图、构建和测试输出按既有约定忽略，不纳入提交。

| 阶段 | 实际修改文件与架构变化 | 已实现 / 实际验收 | 截图证据 | 限制 / 依赖 |
| --- | --- | --- | --- | --- |
| M0 PASS | 本记录；基线 ZIP、patch、SHA 清单 | Flask/Fabric/Pillow/scene/font/启动/测试全部审计，开工前工作与并行修改隔离 | `../.cache/cover-studio-rebuild-baseline/editor-before.png` | 基线仅回滚本模块，不 reset 用户仓库 |
| M1 PASS | `editor/src/{model.ts,migration.ts,CoverArtwork.tsx,fonts.ts,remotion.tsx}`；`cover_document.py` | v3 像素模型、旧百分比迁移、纯 React 画面、字体/图片加载、独立交互层；类型/模型测试及正式图像通过 | [纯画面](output/editor-checks/browser-artwork.png) | 原模板当前画幅迁移；完整旧 scene 只读归档 |
| M2 PASS | `editor/src/Editor.tsx`、`components/{EditorHeader,ToolSidebar,ResourcePanel,CanvasWorkspace,FloatingToolbar,InspectorPanel}.tsx`、`editor.css`、`static/editor/*.jpg` | 浅色工作台、所有主入口接线、三种桌面窗口、完整 16:9 fit、工具条与缩放 | [1366](output/editor-checks/M2-1366x768.png) · [1440](output/editor-checks/M2-1440x900.png) · [1920](output/editor-checks/M2-1920x1080.png) | 按任务修正原稿裁切；真实可用字体替代稿中未提供字体 |
| M3 PASS | `controller.ts`、`InteractionOverlay.tsx`、`CanvasWorkspace.tsx`、`FloatingToolbar.tsx` | 单击选择、双击文字、composition、拖动/八向 resize、吸附、隐藏/锁定/排序、空格平移、快捷键、单次拖动历史、折行末行命中 | [图层操作](output/editor-checks/M3-layer-interactions.png) · [原位编辑](output/editor-checks/M3-inline-composition.png) · [折行选框](output/editor-checks/M3-text-reflow.png) | composition 事件为自动化模拟，系统输入法候选窗 NOT_RUN |
| M4 PASS | `fonts.ts`、`FontPicker.tsx`、`InspectorPanel.tsx`、`controls.tsx`、`font_catalog.py` | 复用六格式家族索引、真实样张、字体搜索/切换/字重、FontFace、重新测量、描边/阴影/颜色/坐标/尺寸/透明度及高级排版 | [真实字体列表](output/editor-checks/M4-font-picker.png) · [属性效果](output/editor-checks/M4-font-and-properties.png) | 字体缺失/缺字阻止正式导出；本机字体移动后需重新选择 |
| M5 PASS | `document_store.py`、`react_editor.py`、`main.tsx`、`app.py`、`templates/{editor,react-build-required}.html`、`editor/{build,render}.mjs` | 防抖保存、revision 冲突、错误重试/另存副本、重开恢复、异常草稿下载/备份恢复、模板迁移、PNG/JPEG 正式下载 | [失败反馈](output/editor-checks/M5-save-failure.png) · [恢复](output/editor-checks/M5-recovered-draft.png) · [模板](output/editor-checks/M5-templates.png) · [导出成功](output/editor-checks/M5-export-success.png) | Node.js + Chromium/Edge；日常本机保存，无云端同步 |
| M6 PASS（自动化范围） | `editor/tests/*`、`tests/test_cover_document.py`、`tests/test_fabric_poc.py`、`fabric-poc/tests/browser-check.mjs`、`run_editor_checks.py`、`design-qa.md` | 72 Python、11 模型、12 浏览器组通过；旧 Fabric 12 图/6 画幅通过；正式 PNG/JPEG、FFmpeg 图片消费通过 | [Stitch 对照](output/editor-checks/design-comparison.png) · [差异图](output/editor-checks/preview-export-diff.png) | 人工视觉/真实系统输入法及完整业务视频生产链 NOT_RUN |

组件名称按职责落地为 `controller.ts` 而非新增状态库：`useSyncExternalStore` 订阅统一快照，现成 `HistoryManager` 保存历史，`snapping-engine` 继续计算参考线。没有引入画布引擎或通用状态框架。

## 数据、渲染和兼容契约

```text
EditorHeader / ResourcePanel / InspectorPanel / InteractionOverlay
                         ↓ change / begin / commit / undo / redo
                 DocumentController → CoverDocument v3
                         ↓                      ↓
            CoverArtwork（即时预览）    /api/cover-documents（原子保存）
                         ↓
       /api/cover-export → Remotion renderStill → CoverArtwork
```

- 文档数组从底层到顶层，frame 的 x/y/width/height 为逻辑像素。屏幕坐标统一由 artboard 的 `getBoundingClientRect()` 换算，不把视觉 zoom 写盘。文本宽度、字体、行高、字距改变后使用实际 DOM 字体重测量；纵向缩放保留 `textScaleY`。
- 保存 750ms 防抖，连续输入历史 500ms 合并；指针手势从 begin 到 commit 为一条命令。保存中响应仅更新 id/revision/updatedAt，保留新输入；撤销不会回退服务端 revision。
- `data/documents/*.json` 为 v3；共享 `data/designs/assets` 内容寻址图片和现有字体 ID。v2 使用 `/api/cover-migration/:id` 冻结旧素材到内容寻址目录后迁移；测试确认原 `preset.json` 字节不变。
- v2 原有独立画幅变体、自动排版模式和分组数据保存在 `sourceScene`，不伪装成 v3 可编辑分组；原设计在 `/fabric-legacy` 可继续编辑。v3 切换画幅缩放当前布局，字号按逻辑短边缩放，反复 16:9 ↔ 9:16 不累计缩小。
- 迁移时将 Fabric 的左上角旋转原点转换为 CSS 的中心原点；小标题组先恢复文字、分隔线的局部偏移及描边边界，再展开为独立图层。90° / −27° 旧矩形使用真实 Fabric 包围框与 React DOM 包围框交叉验证，逻辑像素差小于 0.1。[旋转迁移截图](output/editor-checks/M5-rotated-migration.png)。
- 原 `/api/preset`、`/api/render`、文字/账号图层接口保持原协议，`/legacy` 保留。原 Fabric 首页移动到 `/fabric-legacy`；`/fabric-poc` 仍重定向正式首页。原视频生成器文件未改动。
- Remotion 锁定 4.0.515，React 19.2.8。浏览器与 Node 导出均加载对应字体原始文件，CSS 禁止合成字重；导出前 cmap 缺字检查 + `FontFace.load()` + `document.fonts.ready` + 图片 decode。编辑辅助节点只存在于工作区，不进入 `CoverArtwork`。
- 导出文件由用户下载到目标位置，不自动改写旧视频工程的素材引用。已验证 FFmpeg 可直接消费正式 PNG；完整真实项目的视频合成及平台发布未执行。

## 最终验证证据

| 实际命令（相对 cover-studio） | 结果 |
| --- | --- |
| `.venv/Scripts/python.exe -m unittest discover -s tests -v` | PASS，72/72；日志 `../.cache/cover-studio-rebuild-baseline/python-final.log` |
| `cd editor; npm run typecheck` | PASS |
| `cd editor; npm test` | PASS，11/11 |
| `npm run build`（启动/检查脚本调用同一构建） | PASS，React bundle + Remotion bundle |
| `.venv/Scripts/python.exe run_editor_checks.py` | PASS，12/12 组；`output/editor-checks/browser-results.json` |
| `.venv/Scripts/python.exe fabric-poc/run_checks.py` | PASS，12 张/6 画幅 PNG、历史/模板/图层/吸附/样式等原回归；日志 `../.cache/cover-studio-rebuild-baseline/fabric-regression.log` |
| `git diff --check -- cover-studio` | PASS |

最终基准：1920×1080 浏览器纯画面与正式 PNG 比较逐像素一致，平均绝对 RGB 差 `[0, 0, 0]`，最大通道差 0，预定均值阈值为 0.1。前一轮有一个像素绿色通道差 1/255，仍通过阈值；最后因旋转迁移修复重跑，按最终报告记录。JPEG 实际格式与尺寸通过。详见 [image-comparison.json](output/editor-checks/image-comparison.json)。

浏览器实际覆盖：三种窗口完整 fit；25%/50%/100% 拖动与滚动；拖动中保存仍为一条历史；吸附线、角点与横向边缘缩放、锁定/隐藏/排序；中文 composition 未提前提交；字体真实样张及不同字重；描边/阴影；空名称/空文字、窄宽折行、画幅往返、异常草稿恢复；保存失败/重试/重开/副本；旧模板素材、长文字及旋转图层迁移；上传、形状/文字、快捷键、平移、净预览；实际两格式下载。运行时无非预期错误，故意注入的 HTTP 503 用于验证保存失败反馈。

## 审查和剩余边界

实现清单为 `../.cache/cover-studio-rebuild-baseline/final-review-manifest.json`，42 个交付文件逐项 SHA-256 冻结。清单 SHA-256 为 `b92678173b4c94ceba8d016916f21f2a1ccdba53748d58f6c08826aa0e4a4d42`。生成 bundle、截图、测试输出作为验证上下文保留于忽略目录。

独立核心/UI分区及集成评审均为 `CHILD_AGENT / PASSED / COMPLETE / FRESH`，最终 42/42 项哈希一致，无剩余 P0/P1/P2。UI 26 文件分区哈希为 `0940082827970bd892d8352867e556a453f4321b066b1564eded73433a014980`。评审中修复了保存中覆盖新编辑、历史/重做边界、旧长文字测量、空白名称恢复、画幅字号往返及旋转原点兼容等可复现问题。最终独立评审重新运行模型 11/11 并核验 12/12 浏览器及真实导出报告；无额外实现变更。

- 本机已实际打开最终预览 `http://127.0.0.1:18765/` 并通过页面按钮保存成功；默认 start.bat 仍使用 8765。预览进程在本次交付后保留，可关闭终端进程停止。
- 自动化通过与设计 QA 通过不等于用户的主观最终视觉验收；真实中文输入法候选窗、macOS/Linux 和全新机器安装 NOT_RUN。
- 供图沿用 Stitch 原始图片 URL 对应文件：noir 为 512×512，预设缩略图约 512×286。正式像素尺寸正确，但素材本身不会因放大增加细节；可上传高清原图替换。
- 没有提交、推送、部署，也未改变其他工程已有修改。无额外功能依赖待办。

## 后续交互完善 — shadcn 控件

按用户追加要求接入官方 shadcn/ui `new-york` Select / Tooltip，由 CLI 添加原始组件后将样式映射到既有 CSS token，保留 Phosphor 图标；没有全局 Tailwind 重置。依赖固定为 `@radix-ui/react-select 2.4.1`、`@radix-ui/react-tooltip 1.4.1`。`components.json` 与 TypeScript 别名记录源组件位置。

- `EditorHeader.tsx` 使用 Select，六种画幅均有真实宽高比矩形、横/竖/方标签和像素尺寸；键盘导航不再触发画布移动或平移。
- 保存按钮增加按压/悬停过渡，点击后显示旋转加载图标、绿色成功勾或红色失败提示，失败仍能重试。即使内容已保存，手动点击也有可见反馈。
- 共享 `IconButton`、工具栏、字体刷新、颜色提示、侧栏和对话框图标统一使用 Tooltip；原生 `title` 提示已移除。Portal 配合碰撞检测及 8px 安全间距自动翻转/平移，禁用图标也可显示解释；全屏时 Portal 随宿主切换，退出后恢复，避免被全屏层遮挡。
- 实际检查：TypeScript、构建、11 项模型测试、15 组浏览器检查通过。新增覆盖矩形比例、Select 键盘隔离、禁用控件提示、边缘/全屏 Tooltip、保存成功/失败/重试动画及悬停状态颜色；既有编辑、迁移、保存重开及正式 PNG/JPEG 回归继续通过。最终纯画面与正式 PNG 逐像素一致，最大通道差 0。
- 截图：[比例菜单](output/editor-checks/shadcn-ratio-menu.png)、[边缘提示](output/editor-checks/shadcn-tooltip-edge.png)、[全屏提示](output/editor-checks/shadcn-tooltip-fullscreen.png)、[保存中](output/editor-checks/save-icon-saving.png)、[保存成功](output/editor-checks/save-icon-success.png)、[保存失败](output/editor-checks/save-icon-error.png)。本次基线及 19 文件冻结清单位于 `../.cache/cover-studio-shadcn-controls/`。
- 独立只读审查 `CHILD_AGENT / PASSED / COMPLETE / FRESH`，19/19 文件哈希一致，无剩余 P0/P1/P2；清单 SHA-256 `7649dba2febd2c8599c808163306aa53f20f072dae3aed436e0ba7dd300c0613`。全屏提示除源码检查外，另由独立 Edge 实测顶层命中与退出恢复。


## 后续属性、素材和模板完善（2026-10-22）

本轮基线位于 `../.cache/cover-studio-properties-assets/`，保存实施前源码、测试及包配置。原有重构、其他任务的暂存/未暂存修改均保留；本轮只修改以下 29 个可执行文件和 README/本报告/设计 QA，未提交或推送。

| 修改文件（相对 cover-studio） | 架构与行为 |
| --- | --- |
| `editor/src/components/controls.tsx`、`ui/{slider,input-group,input,button,textarea}.tsx`、`editor.css`、`editor/package{,-lock}.json` | 官方 shadcn CLI 源组件；只有百分比 Slider，宽高/坐标/字号等 InputGroup 步进输入，保留精确输入、上下限与 Tooltip。固定 Slider1.6.1、Slot1.5.0、CVA0.7.1，延续项目 CSS token，不引入全局样式重置 |
| `editor/src/{controller,fonts}.ts`、`components/CanvasWorkspace.tsx` | Slider 连续手势与保存合为一次历史；资源去重、完成缓存，不因文字增删重置画布；画布缩放也是百分比 Slider，键盘事件与画布隔离 |
| `editor/src/{model.ts,CoverArtwork.tsx}`、`components/InteractionOverlay.tsx`、`InspectorPanel.tsx`、`Editor.tsx` | 圆形图片，宽高/控制点/画幅切换保持一致；矩形和椭圆图片填充、替换、移除、裁切；共用纯 React 画面。异步图片使用独立文档 epoch，切换字体不会丢弃填充结果 |
| `editor/src/components/{ResourcePanel,FontPicker}.tsx`、`Editor.tsx` | 保存为新模板、独立应用、设计/模板删除确认；新建设计及打开设计保留当前菜单；Web 字体下载入口 |
| `cover_document.py`、`document_store.py`、`react_editor.py` | 可选 imageShape 向后兼容；形状图片引用校验；templates 独立集合复用原子文档存储；删除检查 revision、保留共享图片；新增受控字体 WOFF2 服务及 CORS |
| `font_catalog.py`、`web_fonts.py` | 保留字体 ID 和原文件；WOFF2 原文件直接使用，其余格式由已有 FontTools 完整转换并缓存；禁用可选 glyf 变换，保留原轮廓并降低大字库首次转换耗时 |
| `tests/{test_cover_document,test_web_fonts}.py`、`editor/tests/{model.test,browser}.mjs`、`run_editor_checks.py` | 模板/删除/字体/API/共享素材回归，滑块历史、无闪烁、圆形往返、上传并发、真实导出；只复用字体缓存，设计仍用临时目录隔离 |

实际验收：Python **79/79 PASS**，TypeScript **PASS**，模型 **14/14 PASS**，构建 **PASS**，Edge 浏览器 **21/21 组 PASS**。浏览器无 page error，仅两次为保存失败恢复测试主动注入的503。包含1366×768、1440×900、1920×1080布局，既有中文composition和旧配置迁移继续通过。正式PNG/JPEG均为1920×1080；新基准含转换后的LXGW TTF字体、描边阴影、圆形图片、旋转矩形填图及椭圆填图，浏览器和Remotion PNG逐像素一致，均值RGB差`[0,0,0]`、最大通道差0；FFmpeg图片消费PASS。

41/41项目字体实际转换/复用成功。完整字符映射和字宽逐项一致，原文件SHA-256前后相同；源总计446267584字节，Web版本250002172字节（约节省44%）。源文件保持原位，缓存位于 `data/font-web/`，新界面与导出共用同一WOFF2服务，旧Pillow/Fabric仍可读取原文件。首次转换较大中文字库约一分钟，后续读缓存，不裁剪字集。

实际截图：[数值步进与百分比](output/editor-checks/preview-properties.png)、[滑块及属性](output/editor-checks/shadcn-properties-sliders.png)、[圆形与形状填图](output/editor-checks/image-circle-and-shape-fills.png)、[模板保存和删除](output/editor-checks/template-save-and-design-delete.png)、[正式导出](output/editor-checks/M5-export-success.png)。测试报告：`output/editor-checks/{browser-results,image-comparison,font-conversion}.json`；Python日志：`../.cache/cover-studio-properties-assets/python-tests.log`。

审查第一轮修复：圆形按两轴缩放后取最小值会在画幅往返时持续缩小（P1），改为短边比例并验证模型5次/浏览器3次往返；字体请求序号会误取消同文档上传（P2），改为独立文档epoch并延迟真实201素材响应验证。最终审查目标29文件，清单 `../.cache/cover-studio-properties-assets/review-target.json`，SHA-256 `4cea7e676db64321ca0397fd2cba1c75554034726802b45115cd7a40daa4038d`，详细上下文为同目录 `review-context.md`。

限制沿用：真实操作系统输入法候选窗、macOS/Linux、全新机器安装未执行；完整生产视频工程未执行，只验证FFmpeg消费导出图片。最终主观视觉验收仍由用户完成。本轮没有剩余功能依赖事项。

最终 Delivery review：**APPROVED**，CHILD_AGENT / PARTITIONED_PLUS_INTEGRATION，后端7文件、UI22文件及集成均PASSED；Coverage COMPLETE、Freshness FRESH，29/29哈希一致，自动修复1轮，无剩余P0/P1/P2。详细记录 `../.cache/cover-studio-properties-assets/delivery-review.json`。
