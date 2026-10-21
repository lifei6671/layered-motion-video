# SC-P1 验收记录

范围：仅 SC-P1-01 至 SC-P1-10，代码全部保留在本 Skill。仓库根原有脏文件及 SC-P0 实现未重构。独立审查结果单独记录于 [review.md](sc-p1/review.md)。

| 任务 | 实现 | 直接验证 |
| --- | --- | --- |
| 01 共享契约 | schemas/contracts.json、Python jsonschema、Ajv、生成 TS 类型 | 9 类有效输入、13 个非法变体、3 个合成批准记录，两端同源测试 |
| 02 原文 | 原字节摘要、BOM/CRLF 保留策略、码点/字节索引 | 重复句、𠮷、emoji、BOM、CRLF，JS 码点切片 |
| 03 路径 | paths.py、输出预检和 public 白名单 | 盘符/UNC/穿越/ADS/保留名、真实 Windows 联接点和输出祖先文件 |
| 04 时钟 | timeline.py 整数绝对采样与帧边界 | half-up、非整数秒、长序列无累计舍入 |
| 05 转场预算 | 三种 placement、保持帧与窗口 | 奇偶帧、首尾越界、容量冲突、单帧镜头、360 帧例 |
| 06 图片 | EXIF、ICC/sRGB、alpha、cover、bbox、逐帧几何 | 八种方向、透明像素、无效 ICC/APNG、非 16:9、裁切帧定位 |
| 07 快照 | 正式批准检查、独立哈希 PNG 副本及复核 | 原图替换不影响快照、无硬链接、public 不暴露非图片 |
| 08 来源 | policy Schema、确认摘要、混合逐镜头映射 | 未确认阻断、来源改变使确认失效、不完整混合映射失败 |
| 09 清单 | 来源/许可/用途/状态/审核人、三重收据摘要 | 缺失授权、来源 URL/检索、资产信息变更、过期证据失败 |
| 10 路径晋级 | 候选/正式文件规则与人工收据 | 候选、参考、技术素材不能晋级，人工放图无收据失败 |

## 已执行

- PASS：`.venv/Scripts/python.exe -m unittest discover -s tests -v`，43 项通过（含原有 SC-P0 的 10 项），日志 [python-tests.txt](sc-p1/python-tests.txt)。
- PASS：`npm test`，生成契约一致性检查、tsc 编译及 28 项 Node 测试，日志 [typescript-tests.txt](sc-p1/typescript-tests.txt)。
- PASS：`npm run typecheck`，无 TypeScript 错误。
- PASS：`uv lock --check`，直接依赖 jsonschema/Pillow/PyYAML 已固定版本，旧模型依赖不变。
- PASS：skill-creator 的 `quick_validate.py`，Skill 元数据与结构有效。
- PASS：真实 CLI 技术编译产生 timeline.lock / props / staging-manifest / 图片快照。
- 图像预览：已打开 portrait 夹具的 cover 预览检查中央形状没有被拉伸；这只是几何夹具检查，不是用户审美批准。

测试记录采集曾因 Windows 控制台 GBK 无法打印 Node 的勾号退出；测试子进程本身退出 0、原始日志完整保存。受影响的 typecheck 随后单独执行并通过。

独立审查第 1 轮发现输入错误响应不完整：YAML 语法错误、日期/集合值、PNG 解码像素上限会抛出未转换异常。已在对应输入边界转换为明确错误，补充 CLI 退出码 2、JSON stderr、无输出副作用的回归测试；错误 JSON 使用 ASCII 转义以兼容 Windows 旧代码页中的非 BMP 路径。

## 可复核结果

[技术项目](sc-p1/fixture-project/input/storyboard.json) 使用 575088 个 48 kHz 采样帧（11.981 秒），三个逻辑镜头为 120/150/90 帧，物理长度 120/174/90，转场窗口 [108,120) 和 [270,282)，总长 360。重复编译的时间线与全部输出字节一致。

- [timeline.lock.json](sc-p1/fixture-project/work/timeline/technical/timeline.lock.json)
- [props.json](sc-p1/fixture-project/work/remotion/technical/props.json)
- [staging-manifest.json](sc-p1/fixture-project/work/remotion/technical/staging-manifest.json)
- [逐帧几何](sc-p1/fixture-project/work/timeline/technical/geometry.json)
- [4:3 裁切预览](sc-p1/fixture-project/work/timeline/technical/cover/SHOT-001.png)
- [3:4 裁切预览](sc-p1/fixture-project/work/timeline/technical/cover/SHOT-002.png)

这些图片由确定性几何绘制脚本生成，音频是静音，全部明确标记 technical_fixture，渠道仍为 SOURCE_POLICY_PENDING。测试中的合成人工收据不是用户批准，没有生成真实生产视频。

## 阶段边界

SC-P1 已建立可执行输入协议；非空 overrides 的应用属于 SC-P3，当前明确拒绝。母带真实采样计数、真实模型对齐、图片工具接入、语义转场审核、视频视觉探针、整批原子发布和正式画质验收属于后续阶段，均未宣称通过。本阶段主体框缺失报告 UNVERIFIED，源分辨率不足报告 upscale_risk；这些报告不能代替人工看图。
