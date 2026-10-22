# SC-P2 Remotion 视觉探针

本阶段已实现静态图片运镜、受控转场、Studio 与无声 H.264 输出。素材来源确认、真实语音对齐、语义批准及有声预览仍由后续阶段完成；技术片不是生产素材审批。

## 运行

Agent 在本 Skill 的 `renderer/static-comic/` 执行命令，负责启动、打开和停止本次 Studio 会话，不要求用户操作终端。依赖继续固定 Remotion 4.0.515。Windows 使用本地 node 入口，缺依赖按 runtime.md 准备，不通过 npx 隐式安装。

以下命令使用已交付的技术展示夹具：

```powershell
node node_modules/@remotion/cli/remotion-cli.js studio src/technical.tsx --props=../../reports/sc-p2/fixtures/showcase/work/remotion/technical/props.json --public-dir=../../reports/sc-p2/fixtures/showcase/work/remotion/technical/public --port=3032 --no-open

node node_modules/@remotion/cli/remotion-cli.js render src/technical.tsx ComicVideo ../../reports/sc-p2/showcase.mp4 --props=../../reports/sc-p2/fixtures/showcase/work/remotion/technical/props.json --public-dir=../../reports/sc-p2/fixtures/showcase/work/remotion/technical/public --muted --codec=h264 --pixel-format=yuv420p --color-space=bt709 --image-format=png --crf=18 --concurrency=2 --browser-executable=node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe
```

Studio 地址为 [localhost:3032/ComicVideo](http://localhost:3032/ComicVideo)。同一 props 和 public 路径用于 Studio/导出。Agent 通过本次启动的会话句柄停止服务，不结束用户已有进程。当前 CLI 的 `studio --help` 也会启动 Studio，不用它查询参数。

`src/index.tsx` 是普通入口，拒绝 technical_fixture；`src/technical.tsx` 是显式技术测试入口。没有默认生产素材，也没有把技术文件自动转为 production 的流程。输入 props 必须来自 SC-P1 编译器；手工修改 props 不等于通过审核。SC-P6 之前不承诺完整事务、并发隔离与跨进程快照防篡改。

如需重建技术夹具，在 Skill 根运行（目标目录必须尚不存在或为空）：

```powershell
.venv/Scripts/python.exe scripts/create_visual_fixtures.py --output <new-empty-directory>
```

脚本依赖本机 Windows Arial 字体，生成确定性几何漫画与静音 WAV；所有用途仍标记 technical_fixture，无真实用户批准。已交付源 PNG 可直接复用。

## 执行约定

- `RemotionRoot` 使用共享 Schema、执行预算校验和 calculateMetadata，从锁定 props 读取 T、1920×1080、30 fps。
- `StaticShot` 仅使用规范化快照，固定同画幅宽高，按 `scale(z)` 和裁切锚点设置 transformOrigin。无 objectFit、CSS transition、随机数或墙上时间。
- 序列局部帧先扣 head_hold，再 clamp 到 [0,logical_frames-1]。单帧取起始状态，头尾保持不推进运动。
- `ComicVideo` 以 TransitionSeries.Sequence 的 physical_frames 组合。硬切直接连接，不插入 0 帧转场。fade 和左右 wipe 使用 Remotion 内置 presentation。
- `wipe_from_left` 从画面左侧揭示新图，`wipe_from_right` 从右侧揭示。通过解码帧与反方向反例的像素误差分别验证。
- 全片固定黑底；fade_black 是自定义 presentation，不是 fade 别名。

### 离散淡黑端点

linearTiming 的窗口内进度为 k/L（k=0..L-1），窗口后为 1。普通 fade/wipe 保留原生语义，到窗口结束帧完全交接。

淡黑取 `m=floor((L-1)/2)`，旧图在 k=0..m 从 1 变 0，新图在 k=m..L-1 从 0 变 1；k=m 为精确黑色帧。因此奇数和偶数 L 都经过黑场、末窗口采样已全新图。L<3 无法表达旧图/黑场/新图三种状态，Composition 明确拒绝，不自动增帧或缩短其他镜头。该限制在 P2 执行边界检查；P1 Schema 保持通用正整数定义。

### 编码参数

`remotion.config.ts` 默认 PNG 中间帧、BT.709、yuv420p、H.264；编码阶段加 `-aspect 16:9` 明确 SAR=1:1。此参数只声明显示比例，不进行运镜/转场处理。所有视觉运动仍由 Remotion 生成。配置同时让 Webpack 将 NodeNext 的 .js 导入解析到对应 TypeScript 源，Node 编译测试仍使用 dist。

## 验证

在渲染目录运行 `npm test`，执行生成契约新鲜度、tsc 和 Node 测试。逐物理帧对照 Python 几何结果，包括所有五种运动、保持和单帧。

在 Skill 根运行：

```powershell
.venv/Scripts/python.exe scripts/verify_visual_probe.py --video reports/sc-p2/showcase.mp4 --project reports/sc-p2/fixtures/showcase --output reports/sc-p2/verification/showcase
```

验证器只用于当前技术夹具：核验源快照哈希、H.264/1080p/yuv420p/BT.709/SAR/30 fps/无音轨；检查每帧 PTS；完整解码每一帧；用独立 Python 几何和转场合成期望画面做像素比较。保存原始 1080p 关键帧，像素误差比较使用 320×180 缩图以容忍 H.264 色度采样和重采样滤波差异，阈值为平均每通道 5/255。它不是全分辨率画质认证；原生大小细线查看和用户观看单独记录。

验证器输出 verification.json、ffprobe.json、完整解码日志和边界 PNG。真实运行命令及编码结果记录在 reports/sc-p2/render-commands.json。
