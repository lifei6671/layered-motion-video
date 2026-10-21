# SC-P2 验收记录

范围：SC-P2-01 至 SC-P2-06，仅技术视觉执行层；不进入 SC-P3 的真实配音处理。所有新增代码、测试、素材与证据位于本 Skill。独立审查结论见 [review.md](sc-p2/review.md)。

## 技术短片

| 文件 | 帧数/时长 | 覆盖 |
| --- | --- | --- |
| [showcase.mp4](sc-p2/showcase.mp4) | 481 / 16.0333 秒 | 五种运镜、cut→fade→cut→wipe、左右擦除、连续两处奇偶淡黑、三种 placement、最后单帧镜头 |
| [clock-360.mp4](sc-p2/clock-360.mp4) | 360 / 12 秒 | P1 原始 120/150/90 逻辑帧与 120/174/90 物理帧、连续两处 fade |
| [all-cuts.mp4](sc-p2/all-cuts.mp4) | 60 / 2 秒 | 三镜头全硬切，无零帧 Transition |

全部为 1920×1080、30/1 fps、H.264、yuv420p、BT.709、SAR 1:1，无音轨。静音为本阶段的刻意输出，不代表配音遗漏。

## 任务与证据

| 任务 | 实现/验证 |
| --- | --- |
| SC-P2-01 | Root / ComicVideo / StaticShot；calculateMetadata 由共享契约读取锁定 T/画幅/fps；技术入口独立 |
| SC-P2-02 | smoothstep、scale/transformOrigin、序列局部帧扣 head hold 并 clamp；Node 对照 Python 每个物理帧几何 |
| SC-P2-03 | TransitionSeries 内置 fade、from-left/from-right wipe；cut 不插入 Transition |
| SC-P2-04 | 固定黑底与自定义 FadeBlack；奇偶持续帧都取明确中点黑帧；少于 3 帧在执行边界拒绝 |
| SC-P2-05 | 原始预算片、混合展示片、全硬切片；保持、单帧、三 placement 与奇偶转场端点验证 |
| SC-P2-06 | 本地 node CLI、真实 --props/--public-dir/--muted 导出；Studio 使用同一快照加载播放；ffprobe + 完整解码 |

## 已执行测试

- PASS：37 项 Node 测试，含共享 Schema 28 项和新增视觉/几何 9 项；npm test 同时进行生成类型一致性与 tsc 编译。[日志](sc-p2/node-tests.txt)
- PASS：43 项 Python 回归。[日志](sc-p2/python-tests.txt)
- PASS：Skill quick_validate。[日志](sc-p2/skill-validation.txt)
- PASS：真实 CLI 普通入口拒绝技术 props；空 public 中缺失图片导致非零退出且无输出文件。[负例命令](sc-p2/cli-negative-tests.json)
- PASS：三段视频所有 901 帧完整解码；PTS 从 0 起严格每帧增加 1/30 秒；帧数与锁定 T 一致。各目录的 ffprobe.json 保留原始媒体参数及每帧时间戳。
- PASS：逐帧与 Python 几何/转场期望图对照。每个物理帧的运动参数亦在 Node 中独立对照 Python geometry.json。

| 技术片 | 最大平均 RGB 误差（0～255） | 黑帧 | 报告 |
| --- | --- | --- | --- |
| clock-360 | 0.8582（第 110 帧） | 无 | [verification.json](sc-p2/verification/clock-360/verification.json) |
| showcase | 1.8897（第 410 帧） | 359、414，均为预期淡黑中点 | [verification.json](sc-p2/verification/showcase/verification.json) |
| all-cuts | 1.2410（第 19 帧） | 无 | [verification.json](sc-p2/verification/all-cuts/verification.json) |

逐帧像素对照使用 320×180 缩图，阈值 5/255，用于容忍编码和重采样滤波差异。它不替代原生分辨率画质检查。左右 wipe 的中间帧另与反方向反例比较：正确方向误差约 0.94/0.98，反方向约 20.11/19.54，确认实际揭示方向。

clock-360 的转场窗口是 [108,120)、[270,282)；第 120 帧完成第一处交接，第二镜头扣 12 帧 head hold 后从局部逻辑帧 0 开始运镜。第 270 帧开始第二处交接。关键边界原始 PNG 位于各 verification 目录。

## Studio 与原生画幅检查

Studio 实际以 showcase 的同一 props/public 路径启动，在浏览器中打开 ComicVideo，观察到完整图像、镜头轨道和约 30 fps 播放；[截图](sc-p2/studio.png)记录了快照首图。没有在 Studio 内修改镜头或素材。

已按原生 1920×1080 查看 [推近末帧](sc-p2/verification/showcase/frame-0119.png)：主体轮廓与线条保持完整，细密栅格存在重采样软化，未将其称为生产高清验收。逐帧误差没有异常黑闪；动态细线闪烁与观看舒适度仍由用户查看所交付短片判断。本次只记录技术初检，不代替用户画质批准。

技术画面是确定性几何漫画；所有源图、音频、来源策略和 props 仍标记 technical_fixture。没有生成真实人工审图收据。

## 修正与运行约定

1. 初始 NodeNext 的 .js 导入无法被 Webpack 定位到 .tsx，已添加 extensionAlias；tsc 显式 rootDir/resolveJsonModule 配合 JSON 声明，防止输出路径漂移。旧的多余编译文件已按明确文件清单清理，保留正常 dist 构建产物。
2. 默认 JPEG 中间帧产生 yuvj420p；改用 PNG + BT.709 后真实输出为 yuv420p。
3. PNG 不携带像素比例，已在 Remotion 编码参数中加 -aspect 16:9，真实 SAR 为 1:1。没有用 FFmpeg 生成运镜或转场。
4. linearTiming 在窗口内为 k/L。淡黑取离散中点，保证奇数/偶数持续帧都有全黑采样；L<3 明确拒绝。普通 fade/wipe 保留内置端点行为，到窗口结束帧完成交接。
5. 可复现命令见 [视觉协议](../references/rendering.md) 和 [真实导出记录](sc-p2/render-commands.json)。没有提交、推送，也没有修改根目录原有文件。

后续仍需 SC-P3 真实配音对齐、SC-P3A 实际供图/审图、SC-P4 语义转场确认及 SC-P5 有声预览；本阶段不宣称正式生产闭环已完成。
