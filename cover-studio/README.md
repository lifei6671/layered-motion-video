# 封面工坊

本地可视化封面设计工具。正式编辑界面使用 Fabric.js，在浏览器中完成文字和图层编辑、多比例布局、实时预览及高清 PNG 导出；Python 负责字体、素材、设计存储与批量任务接口。经典 Pillow 编辑器保留独立的兼容入口。

## 启动

Windows 系统进入 `cover-studio`，双击 `start.bat`。首次启动会自动准备 Python 虚拟环境与相关依赖；如果前端脚本尚未生成或源码已更新，会使用本机 Node.js/npm 自动安装、构建 Fabric.js 资源。首次部署需要本机已安装 Node.js。

正式编辑器：http://127.0.0.1:8765/

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

默认首页使用 Fabric.js 渲染预览和 PNG；Python 管理字体、素材、设计版本与本机 API。

- 正式入口：http://127.0.0.1:8765/
- 支持当前经典模板导入、多模板创建与复制、自由图层、组合、字体样式、画幅独立布局、智能吸附和质量预检。
- 新版设计保存在 `data/designs/`，经典默认模板保存在 `data/preset.json`，可在经典编辑器中独立使用。
- 前端工程源码与命令行构建见 [fabric-poc/README.md](fabric-poc/README.md)。
- 架构与后续生产能力见 [fabric-poc/MIGRATION.md](fabric-poc/MIGRATION.md)。

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

网页「字体配置」中选择「项目目录字体」后，可先选择**字体家族**（子目录名），再从该家族下挑选**字形与字重规格**。程序从文件名和字体自身的元数据识别细体、常规、中等、粗体、极粗、等宽以及斜体等规格，并按字重排序。相同字重的 TTF、OTF、WOFF、WOFF2 也作为独立文件保留，方便选择适配效果。首次选择某家族时，优先采用非等宽常规字重；若存在同规格的 OTF 与 TTF，优先 OTF。添加、替换或删除字体文件后点击「刷新字体列表」，不必重启服务。

支持 TTF、OTF、TTC、OTC、WOFF、WOFF2。WOFF 与 WOFF2 通过 fontTools 在内存中转换成 Pillow 可读取的数据，原始文件不变。字体文件大小上限为 80 MB；压缩网页字体的渲染上限为压缩前文件 25 MB、解压后 96 MB。

字体家族与字重规格都采用**直接带字形样张的可搜索下拉框**：家族下拉选项以该家族已选（或常规）规格的真实笔画为主视觉，右侧显示家族名及规格数量；字重下拉选项直接展示每个规格的实际字体样张，旁边标识字重、文件名及中文字形覆盖情况，当前已选项目在收起状态仍显示其字形。系统字体同样采用字形可视化下拉选择。含中文的字体优先显示中文示例；只含拉丁字形的字体显示 `Aa Bb 123`。样张由 Pillow 生成并按可见范围加载。下拉框支持名称搜索、方向键浏览、回车选择与 Esc 关闭。保存模板时记录具体字体文件的稳定标识，切换字体家族会保留此前选中的规格。移动文件会产生新的标识，可在刷新后重新选择。

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
├── templates/fabric-poc.html  # 正式可视化编辑页面
├── templates/index.html   # 经典 Pillow 编辑界面
├── fabric-poc/            # Fabric.js 前端源码、构建与浏览器验证
├── editor_build.py        # 需要时自动准备前端脚本
├── static/                # 两种编辑界面使用的样式与脚本
├── tests/                 # 图片/API/字体/坐标回归测试
├── data/                  # 保存的背景、头像及个人模板配置
├── requirements.txt
└── start.bat
~~~

模块为 data/、.venv/ 和新加入的字体文件配置了忽略规则；已在版本索引中的字体仍会保留其追踪状态。

## 运行测试

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

测试覆盖字体家族分组、规格切换、两行排版、三块文字的独立定位与复位、三种画幅的图层逐像素合成、模板坐标保存、旧版账号图层接口及实际 HTTP 静态资源。

## 技术约束

- 服务仅监听 127.0.0.1，不依赖 AI 生图或云端服务。
- 前端只能选用服务端扫描产生的字体索引，无法提交任意本机路径。
- 背景和头像单个大小分别不超过 18 MB、12 MB，上传请求不超过 40 MB；图片像素上限为 4800 万。
- 三块文字图层由 Pillow 绘制为透明 PNG，网页负责各自的拖动与定位；最终下载使用同一字形图层重新合成。
- 运行环境为 Python 3.10+，Windows、macOS 和 Linux 支持常见系统字体目录扫描。
