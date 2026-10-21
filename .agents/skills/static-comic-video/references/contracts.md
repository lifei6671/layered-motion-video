# SC-P1 输入编译协议

P1 编译层不执行 ASR、图像获取或视频渲染。SC-P3 已补充独立 `align` 命令：当前生产编译必须先有有效语音对齐证据，参见 [语音协议](speech.md)；纯 P1/P2 技术夹具仍可用已知时间。语义确认和正式预览审核仍属后续阶段。

## 命令

在 Skill 根目录执行（项目路径指向单期目录，不是 Skill）：

```powershell
.venv/Scripts/python.exe -m static_comic validate --project <episode-directory>
.venv/Scripts/python.exe -m static_comic compile --project <episode-directory>
```

`validate` 运行相同的输入、图片、预算及输出位置检查，不写文件。`compile` 写入经过全部检查的结果。失败退出 2 并在 stderr 输出 JSON；成功退出 0。`doctor` 保留原有行为。

技术探针：

```powershell
.venv/Scripts/python.exe scripts/create_fixture.py --output <new-empty-directory>
.venv/Scripts/python.exe -m static_comic compile --project <new-empty-directory> --technical-fixture
```

技术输出标记 `artifact_kind=technical_fixture`，时间线在 `work/timeline/technical/`，props/public 在 `work/remotion/technical/`。只能接收同时标为技术用途的图片和时间，不能用该参数绕过生产审核。TypeScript 的 `validateProps` 默认拒绝技术夹具，测试必须显式放行。

## 输入与唯一契约

权威来源是 [contracts.json](../schemas/contracts.json) 的 `$defs`；Python 使用 jsonschema，TypeScript 使用 Ajv2020。运行 `npm run contracts:generate` 从该文件生成类型；`npm test` 检查类型未过期。两端对同一组 [有效/无效夹具](../fixtures/contracts-cases.json) 校验。夹具中的 TEST ONLY 收据是测试数据，不能复制到真实项目。

| 文件 | 定义 | 含义 |
| --- | --- | --- |
| input/script.txt | UTF-8 字节输入 | SHA256 含 BOM，码点索引去除一次开头 BOM，CR/LF 原样保留 |
| input/voice.wav 或 voice.mp3 | storyboard.audio | 原始音频哈希、48 kHz 采样时钟、已知有效采样帧数 |
| input/storyboard.json | storyboard | 逐镜头原文区间、逻辑起点、语音区间、运镜、转场与图像证据 |
| input/render.yaml | render | 1920×1080、30/1 fps、透明像素合成底色 |
| input/image_source_policy.json | policy | 单一/混合渠道、允许渠道和用户确认 |
| assets/images/manifest.json | manifest | 来源、提示词/检索、作者、许可、用途、哈希、状态和审核人 |
| review/image_approvals.json | approvals | 每镜头当前有效人工收据 |
| input/overrides.json | overrides | 可选；非空读法/窗口/边界覆盖由 SC-P3 校验并应用，编译器重放原始证据 |

所有字段封闭，未知字段和枚举失败。JSON 重复键及非有限数字失败。整数受 JavaScript 安全整数范围约束。原文区间为去 BOM 后 Unicode 码点的半开区间；顺序覆盖整篇原文，不用句子检索定位重复句。JS 使用 `Array.from`，不能按 UTF-16 下标切片。输出 `source-index.json` 保存每个码点到原始 UTF-8 字节的映射（含末尾哨兵）。

纯 P1/P2 技术夹具的音频时长仍是调用方提供并绑定源哈希的**已知输入**。当前生产路径由 SC-P3 母带的真实 PCM 采样数替代输入中的占位时长，并核验音频与报告哈希；不能把夹具静音音频的成功当作真实配音验收。

## 时间与几何

唯一时钟为 48000 Hz。总帧数 `ceil(S*30/48000)`；每个绝对边界按 `floor(s*30/48000+1/2)` 舍入，镜头长度取相邻绝对帧差。模型十进制秒数用 `seconds_to_samples` 一次 half-up 转成整数采样，窗口偏移仅加一次。

转场 L 的 pre/post：start=(0,L)，end=(L,0)，center=(floor(L/2),L-pre)。镜头 head 为前一转场 pre，tail 为当前转场 post，物理长度为 head+logical+tail。检查所有窗口在 [0,T) 中，incoming_post+outgoing_pre < logical。逻辑起点与语义锚点可不同，但必须提供 boundary_reason。

图片只接受单帧 PNG。依次执行 EXIF 方向、ICC→sRGB（无配置按 sRGB 报告）、alpha 合成、按 cover_anchor 显式裁切成 16:9。规范化尺寸按最大缩放预留像素，源图不足会报告 upscale_risk；不把插值放大当成高清验收。预处理限制 4000 万像素。

subject_bbox 使用**原始存储像素方向**下的归一化 [x0,y0,x1,y1]，先随 EXIF 变换，再映射到 cover 后图像坐标。逐个物理帧记录实际 crop 和主体包含性，缺少主体框标记 UNVERIFIED，生产主体被裁切会阻断并列出帧号。没有主体框不自动证明安全，留待后续审图。头尾保持通过 clamp 冻结运镜；运镜使用 smoothstep，不用墙钟或随机数。

## 来源与审核

SC-P3A 已实现 [渠道供应与审图流程](image-supply.md)。生产编译还必须核验已确认 image_requests、当前 supply 记录、原始/候选/正式图片及来源证据。manifest 在候选阶段可为空，但生产仍必须逐镜头完整。批准收据增加 supply_sha256；非空生产转场同时绑定 image_approval_hashes，重新批准后需重新审语义。无主体框现在也不能通过图片晋级。

候选只放在 `work/images/candidates/<name>.png`。正式目标严格为顺序 `assets/images/shot_0001.png` 等；文件存在仍不是批准。

渠道为 agent_generate、third_party_retrieve、manual_generate，混合模式逐镜头完整映射。确认记录包含用户、带时区时间、可追溯交互证据，以及除 confirmation 外策略内容的 canonical SHA256。改变策略内容需重新确认，`supersedes` 可链接前一策略摘要。

收据同时绑定图片原始字节 SHA256、完整资产条目摘要、完整来源策略摘要。资产中的 reviewer 必须与收据相同。修改图片、许可、作者、来源或渠道都会使旧批准失效。第三方入镜必须有源 URL、检索条件、许可证据和适用范围。reference_only、候选、未审、驳回、技术用途不能进入生产 public。Agent 不得生成真实用户批准；这些本地摘要用于发现过期记录，不是身份认证或数字签名。

转场还需绑定相邻两张原始图片的哈希和当前图片批准摘要。SC-P4 已加入 [语义转场流程](transitions.md)：生产多镜头编译必须核验当前候选、逐边界人工收据和 apply 记录。候选与分镜严格分离；更改原文、图片、来源、审批或声学证据会使计划过期。完整性验证不能代替 Agent 实际看图及用户语义审核。只有一个镜头时没有转场边界，无需转场收据。

## 输出与目录归属

生产输出：
- `work/timeline/timeline.lock.json`：源输入哈希、契约哈希、编译器版本、原始镜头和执行预算。
- `work/timeline/source-index.json`、`geometry.json`、`cover/SHOT-XXX.png`。
- `work/remotion/props.json`、`staging-manifest.json`。
- `work/remotion/public/images/<processed-sha256>.png`：独立复制并复核的规范化图片。

路径必须是以 / 分隔的相对路径。拒绝盘符、UNC、反斜线、..、空段、ADS、Windows 保留名、尾部点/空格，以及解析后越出项目的符号链接/联接点。输出路径还拒绝所有重定向链接和非目录祖先。public 只接受可校验的哈希 PNG；出现其他文件时停止并保留现场。原图后续变化不会修改已有快照，重新编译会首先拒绝旧批准。成功重新编译会清理此前生成且已校验的闲置快照。

单期串行执行。SC-P6 已接入内容/版本缓存、临时验证后逐文件原子替换、可捕获发布失败的回滚及执行快照检查，详见[缓存协议](cache.md)；不承诺多进程互斥或跨文件断电事务。渲染器必须使用经校验的 props 和该 public，不直接读原始素材。

SC-P5 已通过 [交付流程](delivery.md) 连接上述编译结果与本地 Remotion。preview / render-visual 重新验证输入及暂存；approve 的 deliveryDecision 绑定当前有声预览，正式画质另用 stage=final。生产批准和 technical 测试收据使用不同目录，完整 PCM 母带只在 FFmpeg 封装阶段加入。

## 验证

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/create_contract_fixtures.py --output fixtures/contracts-cases.json
cd renderer/static-comic
npm run typecheck
npm test
```

测试 corpus 的重建是显式写操作；普通 npm test 不重写源契约和类型。通过测试只证明 SC-P1 的契约、时钟、几何和拒绝路径，不等于 SC-P2 的真实逐帧视频验收。
