# 封面工坊

本地可视化封面设计工具。正式编辑界面使用 React + TypeScript，在浏览器中即时编辑文字、图片和图层；Remotion 使用同一个 `CoverArtwork` 输出原尺寸 PNG / JPEG。Python 负责字体、素材与本机存储。原 Fabric 和经典 Pillow 编辑器保留独立入口。

## 启动

Windows 系统进入 `cover-studio`，双击 `start.bat`。首次启动会自动准备 Python 虚拟环境与相关依赖；前端缺失或源码更新时，会使用本机 Node.js/npm 安装、构建 React / Remotion 及兼容 Fabric 资源。首次准备需要 Node.js 和网络；日常编辑与导出使用本机资源。正式导出优先使用已安装的 Microsoft Edge，也可通过 `COVER_STUDIO_BROWSER` 指定 Chromium 可执行文件；其他环境首次导出可能下载 Remotion Headless Shell。

正式编辑器：http://127.0.0.1:8765/

原 Fabric 编辑器：http://127.0.0.1:8765/fabric-legacy

经典 Pillow 编辑器：http://127.0.0.1:8765/legacy

也可以用 PowerShell 手动启动：

~~~powershell
cd cover-studio
.\.venv\Scripts\python.exe app.py
~~~

Python 环境首次安装命令：

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

## 可视化封面编辑器

默认首页采用 Stitch 浅色工作台，白色面板、点阵画布、蓝色选中态。画面与交互覆盖层分离，编辑过程中不会请求后端重新渲染。

- 正式入口：http://127.0.0.1:8765/
- 单击选层，双击文字原位编辑，Ctrl+Enter 完成、Esc 取消；支持拖动、八个缩放控制点、智能吸附、图层隐藏/锁定/排序及撤销重做。
- 右侧编辑文字、真实字体文件/字重、颜色、描边、阴影、行高、字距、位置、尺寸及透明度。空格拖动画布、Ctrl+0 适应窗口；底部可改变显示缩放。
- 修改后 750ms 防抖自动保存，顶部显示保存状态；失败可重试或另存副本。本地草稿可在重开后恢复；异常草稿支持原始下载及保留备份后打开已保存版本。
- 新文档 `schemaVersion: 3` 保存到 `data/documents/`，使用逻辑像素坐标，素材沿用 `data/designs/assets/`；原 v2 设计仍在 `data/designs/`，经典模板仍在 `data/preset.json`。
- 「模板」面板可打开或复制完整文档，也可迁移原模板。迁移当前画幅并存档完整 `sourceScene`，原文件保持原样。旧分组扁平为等效可见/锁定/顺序；其他画幅的原有独立布局请在原 Fabric 编辑器继续编辑。新文档切换画幅按比例缩放当前布局。
- 正式 PNG / JPEG 等待字体和图片加载并检查缺字。导出仅包含画面内容，16:9 为真实 1920×1080 像素；下载文件可直接供既有 FFmpeg/视频流水线引用。
- 文件级架构、阶段验收、截图和限制见 [EDITOR_REBUILD.md](EDITOR_REBUILD.md)；设计对照见 [design-qa.md](design-qa.md)。原 Fabric 工程说明保留在 [fabric-poc/README.md](fabric-poc/README.md)。
- 顶部画幅使用官方 shadcn/ui Select，每项以真实宽高比矩形展示横版、竖版或方形。图标提示统一使用可自动避让窗口边缘的 Tooltip，保存按钮包含加载、成功和失败动画。组件由 shadcn CLI 添加到 `editor/src/components/ui/`，沿用 Phosphor 图标和现有 CSS token，无需全局 Tailwind 样式重置。

## 项目字体库

`fonts/` 采用**一个一级目录对应一个字体家族、目录内每个字体文件对应一种可选择的字形规格**的组织方式。例如：

~~~text
cover-studio/
└── fonts/
    ├── LXGWWenKai/
    │   ├── LXGWWenKai-Light.ttf
    │   ├── LXGWWenKai-Regular.ttf
    │   ├── LXGWWenKai-Medium.ttf
    │   └── LXGWWenKaiMono-Regular.ttf
    ├── SourceHanSans/
    │   ├── Source_Han_Sans_SC_Regular.otf
    │   ├── Source_Han_Sans_SC_Medium_Medium.otf
    │   └── Source_Han_Sans_SC_Bold.otf
    └── MaokenAssortedSans/
        ├── MaokenAssortedSans-Lite.otf
        ├── MaokenAssortedSans-Lite.ttf
        ├── MaokenAssortedSans.otf
        └── MaokenAssortedSans.ttf
~~~

右侧「字体排版」先搜索并选择**字体家族**（子目录名），再选择**字重 / 字形**。程序从文件名和字体元数据识别细体、常规、中等、粗体、极粗、等宽及斜体，按字重排序。相同字重的不同格式文件保留独立 ID。添加、替换或删除字体后点击字体列表中的刷新按钮，无需重启。

支持 TTF、OTF、TTC、OTC、WOFF、WOFF2。WOFF 与 WOFF2 通过 fontTools 在内存中转换成 Pillow 可读取的数据，原始文件不变。字体文件大小上限为 80 MB；压缩网页字体的渲染上限为压缩前文件 25 MB、解压后 96 MB。

家族列表使用对应字体文件生成的真实字形样张，可搜索名称；无中文覆盖的字体展示拉丁样张。字重选择具体文件后，画布自动通过 `FontFace` 加载对应 WOFF2 文件并重新测量文本，不合成伪粗体。Remotion 使用同一 ID 和文件；加载失败或缺字会显示错误并阻止正式导出。保存记录具体文件的稳定标识；移动字体文件后需刷新并重新选择。经典入口保留原有家族和字重样张下拉框。

字体无需安装到系统。模块的 Git 忽略规则适用于尚未纳入版本索引的字体文件；已经暂存或追踪的字体继续遵循仓库当前版本管理状态。请确认所用字体的许可证允许封面、短视频、传播和商业使用等实际用途。

## 经典编辑器操作

在 `/legacy` 打开经典编辑器时，可使用以下固定模板排版流程：

1. 输入大标题、小标题和账号名称，大标题优先保持书法大字效果，必要时自动换成两行；小标题支持两行。
2. 选择目标画幅：9:16（1080×1920）、3:4（1080×1440）、4:5（1080×1350）、1:1（1080×1080）、4:3（1440×1080）、16:9（1920×1080）。
3. 选择背景与头像（PNG/JPEG/WebP），调整背景压暗和裁切重心。
4. 为大标题与小标题分别选择字体；项目字体可按家族、字重和字形样张选择。
5. 在右侧封面画布上，直接按住**大标题、小标题或账号名称**分别拖动。小标题下方的分隔线与小标题作为一个整体移动。长标题的自动换行和字号测量保持一致。
6. 文字都可以通过左侧横向、纵向百分比坐标输入框精确定位；点击对应文字图层后按方向键微调 1 个原图像素，Shift 加方向键移动 10 个像素。文字完全处于画布可见范围之内。
7. 大标题的「自动居中」和小标题的「自动排版」将位置恢复为自动模式：修改标题文字或切换字体后，仍按原有规则计算位置。只有手动拖动或填写坐标才固定位置，两个坐标轴也可以分别设为自动模式。账号「复位」则恢复默认位置。
8. 点击「下载 PNG 封面」输出完整版高清 PNG；预览底图、标题、小标题和账号使用同一批由 Pillow 生成的字形和原生像素位置，保持逐像素一致。
9. 点击「保存为默认模板」后，背景、头像、字体与三块文字的位置（包括自动定位状态）会写入本机 `data/preset.json`。下次打开后继续使用。

每个文字层的位置以画布左上角为原点，使用宽高百分比记录；切换画幅时根据新的实际像素尺寸重新换算。当文字变长、字体变化或改为窄画幅时，超出边界的部分会在画布内自动约束，避免裁切。独立手动拖动时可以自行决定三块文字的相对关系。

## 目录结构

~~~text
cover-studio/
├── app.py                 # Flask 本机接口与模板配置持久化
├── renderer.py            # 文字排版、透明图层及最终高分辨率绘制
├── font_catalog.py        # 系统字体及家族目录索引
├── font_variants.py       # 字重、字形、格式识别与排序
├── font_preview.py        # 字形覆盖分析与字体预览生成
├── fonts/                 # 本地开源字体文件和许可证
├── templates/editor.html  # React 编辑器页面
├── editor/                # React / TypeScript、共享画面、Remotion 导出及浏览器测试
├── cover_document.py      # v3 文档边界校验
├── document_store.py      # v3 文档原子保存及 revision 冲突检查
├── react_editor.py        # v3 存储、迁移、正式导出接口及构建
├── templates/fabric-poc.html  # 原 Fabric 编辑页面
├── templates/index.html   # 经典 Pillow 编辑界面
├── fabric-poc/            # Fabric.js 前端源码、构建与浏览器验证
├── editor_build.py        # 需要时自动准备前端脚本
├── static/                # 编辑器资源与构建产物
├── tests/                 # 图片/API/字体/坐标回归测试
├── data/                  # 保存的背景、头像及个人模板配置
├── requirements.txt
└── start.bat
~~~

模块为 data/、.venv/ 和新加入的字体文件配置了忽略规则；已在版本索引中的字体仍会保留其追踪状态。

## 运行测试

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd editor
npm ci
npm run typecheck
npm test
npm run build
cd ..
.\.venv\Scripts\python.exe run_editor_checks.py
.\.venv\Scripts\python.exe fabric-poc/run_checks.py
~~~

`run_editor_checks.py` 使用临时数据目录和 Microsoft Edge headless，不改个人模板。覆盖三种桌面尺寸、多缩放拖动、中文 composition 事件、图层/字体/属性、自动保存失败恢复、旧数据迁移、真实 PNG/JPEG 下载及浏览器/Remotion 像素对比。结果在忽略的 `output/editor-checks/`。真实系统输入法候选窗仍需人工验证。

## 技术约束

- 服务仅监听 127.0.0.1，不依赖 AI 生图或云端服务。
- 前端只能选用服务端扫描产生的字体索引，无法提交任意本机路径。
- 背景和头像单个大小分别不超过 18 MB、12 MB，上传请求不超过 40 MB；图片像素上限为 4800 万。
- 新编辑器画面为纯 React DOM，交互覆盖层独立；原 Pillow / Fabric 接口保持兼容。新导出是独立图片文件，不自动覆盖视频工程素材路径。
- 运行环境为 Python 3.10+，Windows、macOS 和 Linux 支持常见系统字体目录扫描。

## 属性、图片填充和模板管理

- 只有百分比属性使用 shadcn Slider（透明度、压暗、裁切重心、画布缩放）；宽高、坐标、字号、圆角等使用 shadcn InputGroup 组合的「− / 数值 / ＋」步进输入框，可直接精确输入并遵守上下限。
- 图片属性中可选择「圆形」，直径在数值编辑、控制点缩放和切换画幅时保持一致。矩形、椭圆可上传图片填充，支持替换、移除和裁切设置。
- 模板页可「保存为新模板」，模板完整存储背景、图片、字体和各图层样式；点击模板创建独立设计。设计和模板的删除均有确认及版本冲突保护，删除保留共享图片素材。新建设计和打开设计会留在模板页。
- `fonts/` 原文件保持不变；原有 WOFF2 直接使用，其他格式使用已有 FontTools 转换，缓存到 `data/font-web/`。首次转换较大的中文字库可能需约一分钟，后续复用缓存。保留完整字库，不做字符子集裁剪。选择字体后会自动加载对应 WOFF2，使用时无需手动下载或安装。
- 自建模板位于 `data/templates/`，设计仍在 `data/documents/`，旧 v2 模板继续通过原迁移入口导入。
