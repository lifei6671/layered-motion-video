# 智能视觉强调与音效系统——Codex 分阶段实施清单

> 任务版本：2.0 ｜ 2026-10-21  
> 适用仓库：`layered-motion-video` ｜ 实施目录：`.agents/skills/static-comic-video/`  
> 权威需求：[智能视觉强调与音效系统-技术方案.md](./智能视觉强调与音效系统-技术方案.md)  
> 目标：根据画面自主决定是否添加文字，按旁白/镜头选择一级至高级文字特效，并为整片视频智能选择可选音效，在 FFmpeg 中形成完整可审核的混合音轨。

## 实施记录（2026-10-22）

已按 SC-K1 → SC-K5 实现核心链路，以下复选框只表示对应代码/验证已完成；不代表生产素材或人工审批通过。当前阶段详细结果见 [阶段验收记录](./智能视觉强调与音效系统-阶段验收记录.md)。

- 初始 Git 工作区干净，基线 `c5594877a46fa55b97599b26d69ab13ec4406d53`；改动仅限本 Skill 与相关文档，未提交、推送或下载模型/素材。
- SC-K1～K4：契约、受控候选/多帧布局、6+2 种文字效果、4 类音效和采样级混音已有代码、正反例及真实技术样片。
- SC-K5：60 秒 540p/1080p 有声技术片、45张转场帧、56组双尺寸同帧对照、Python/Node全量回归与增量矩阵已通过；零文字像素对照也已通过；四组真实冷/热性能已通过；纯音效增益修改也已实测：视觉/build HIT、混音/封装 REBUILT，旧试听绑定改变。20项探针断言全部通过。
- `fragment_disperse`、`particle_assemble` 为受控但未实现的枚举入口，状态 **UNAVAILABLE**；三级预渲染关闭。视觉模型提供者 **UNAVAILABLE**，规则观察标为 **HEURISTIC**，可导入实际看图后的受控观察。
- 真实漫画/真实旁白全流程、人工审图/完整试听/正式画质确认 **NOT_RUN**。合成技术夹具不作为真实声学模型质量或主观效果验收依据。

## 0. Codex 开始执行前的硬性要求

### 0.1 识别真实实现与当前修改

- [x] 读取当前 Git 状态（包括暂存、未暂存和未跟踪），记录工作区已有改动；**禁止**重置、清理、暂存、提交或推送未经用户授权的文件。
- [x] 确认正式代码在 `.agents/skills/static-comic-video/`；不要以仓库根早期设计稿为可执行代码基线。
- [x] 读取 `SKILL.md`、`references/runtime.md`、`references/contracts.md`、`references/speech.md`、`references/rendering.md`、`references/delivery.md`、`references/cache.md`、`references/image-supply.md`、`references/human-confirmation.md`。
- [x] 阅读 `static_comic/{cli,project,timeline,speech,speech_text,delivery,media,cache,paths,images}.py` 及 `schemas/contracts.json`。
- [x] 阅读 `renderer/static-comic/src/{ComicVideo,StaticShot,Root,contracts,motion,transitions}.tsx|.ts`、`package.json`、现有 TypeScript/Python 测试和版本锁定信息。
- [x] 记录当前实际 Remotion 4.0.515、WhisperX 3.8.6、FFmpeg、Python/Node 及字体和音效资源的可用性；必要功能不可用时标记 `UNAVAILABLE`，不能宣称已支持。
- [x] 采用与现有项目一致的技术夹具与正式生产区分，不能签发图片、转场、有声预览、画质、音效版权等任何真实用户批准。

**当前任务范围**只允许修改当前 Skill、新增相关测试及其设计文档。仓库中 `cover-studio`、其他项目文件、已有用户改动都不属于本次范围。优先复用当前虚拟环境与 Node 依赖；未经授权，不自动下载声学模型、字体、音效库、图片或修改 VoiceStudio。

### 0.2 强制架构规则

1. 视觉覆盖层只能存在于 `ComicVideo` 的全片根帧域，并且作为 `TransitionSeries` 外面的独立上层。禁止往 `StaticShot` 塞歌词式文字逻辑或将文字直接写入图片。
2. 采用现有 48 kHz 整数采样、30 帧/秒时钟；视觉与音效拥有不同类型的锁定事件，不得并行维护第二套浮点时钟。
3. 完整保留 `work/audio/master_48k.wav`。音效使用独立 stem，再产生 `mix_48k.wav`；最终视频只有一条混合 AAC 音轨。
4. 决策必须支持零文字、零音效及两者均零；`skip/silence` 是合法且可解释的输出。
5. Agent/模型只产生受控 JSON 候选；Python 负责校验、时间规划、来源授权和最终事件锁定。禁止将 Agent 输出当任意可执行代码或 FFmpeg 命令。
6. 用户人工指定的跳过、固定词条和固定音效优先于自动计划；冲突需明确 `REVIEW_REQUIRED`，不能私自删改。
7. 视觉/音效只要改变当前有声预览内容，必须使旧预览和正式画质的批准绑定过期。
8. 仅修改音效时，应命中视觉缓存；不应再次运行完整 Remotion 视觉渲染。

### 0.3 测试与阶段交付格式

本 Skill 根目录（Windows）：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m static_comic doctor
```

Remotion 根目录：

```powershell
npm run contracts:check
npm run typecheck
npm test
```

以上是已存在的测试入口，Codex 应先验证它们在当前环境中的实际行为。新增 `emphasis`/`sfx` 命令在对应阶段完成后才允许测试，不能把待实现接口当成当前可运行命令。

每阶段至少交付：改动文件清单、输入/输出 Schema、实际运行命令及退出码、有效测试/反例测试、生成物相对路径、缓存事件日志、失败说明、人工审核状态，以及 `PASS / FAIL / NOT_RUN / UNAVAILABLE` 状态报告。提供实际 JSON/PNG/WAV/MP4 产物时，应能在项目目录找到真实文件。

---

## SC-K1：可选契约、资源与旧项目兼容

**目标**：让新能力能够安全启停，并建立独立字体与音效授权资源。即使没有新输入文件，旧项目也必须继续工作。

### 功能任务

- [x] `schemas/contracts.json` 新增 `emphasisPolicy`、`emphasisPlan`、`shotEmphasisDecision`、`visualEmphasisEvent`、`sfxEvent`、`fontManifest`、`sfxManifest` 等 `$defs`。
- [x] 保持现有 `props.schema_version=2.0`；新增可选 `props.visual_emphasis`。旧 props 不因新字段缺失报错。
- [x] 通过既有 `npm run contracts:generate` 重新生成 TypeScript 类型，检查生成结果的契约新鲜度，不能手工修改 `contracts.generated.ts`。
- [x] 在 `static_comic/emphasis.py` 建立策略、计划读取及校验；文件缺失默认为 `disabled`，`visual.enabled` 和 `audio.enabled` 可独立选择。
- [x] `shot_decisions` 全镜头唯一覆盖，支持 `text_decision=auto/show/skip` 和 `sfx_decision=auto/allow/silence`；非法镜头 ID、缺少原因或未知状态拒绝。
- [x] 建立 `assets/fonts/manifest.json` 和 `assets/sfx/manifest.json` 的合法性、路径边界、来源、授权证据和哈希校验。
- [x] 只有视觉层启用时才要求字体；只有音效使用时才要求音效资产；旧项目无需创建空资源目录。
- [x] 扩展受控 Remotion public 暂存白名单，仅放行声明的 `images/`、`fonts/`、`effects/` 资源；音效**不**进入 public。
- [x] 禁止重复 JSON 键、未知字段、路径越界/软链接跳转、非有限数值、非法时间/模板、资源哈希不一致。

### 主要文件

`schemas/contracts.json`、`static_comic/emphasis.py`、`static_comic/project.py`、`static_comic/paths.py`（仅确有需要时）、`renderer/static-comic/src/contracts.generated.ts`、`renderer/static-comic/src/contracts.ts`，相关测试和文档。

### 自动化验收

- [x] 现有 Python/Node 回归已执行且无失败（Python 241 项：240 PASS、1 SKIP；Node 89 PASS；SKIP 为本机无法创建普通软链接，不计 PASS）。
- [x] 未配置扩展时，旧技术夹具仍按既有时间线和图片清单编译、渲染；零视觉事件不改变旧帧内容。
- [x] 视觉单开、音效单开、双开、双关全部通过 Schema 和资源按需校验。
- [x] 不合法字体授权、音效许可缺失、目录注入、哈希篡改等反例均失败且定位具体资产。
- [x] 同一输入计划两次规范化输出字节一致。

**阶段验收结果**：契约类型、资源清单示例、正反例测试、旧项目兼容报告。本阶段不得以静态模拟效果声称视频动效完成。

---

## SC-K2：图像自适应、可跳过策略与时序编译

**目标**：让系统对每个镜头判断“要不要文字/要不要音效”，再决定位置、样式及可计算的全片事件锚点。

### 视觉观察与决策

- [x] 建立 `static_comic/emphasis_vision.py`，只读取当前真实已批准的规范化漫画快照和相应运镜/几何信息。
- [x] 对开始、1/4、1/2、3/4、结束和候选事件时刻采样，生成带图片/运镜哈希的证据索引。
- [x] 定义受控视觉观察协议：主体框、已有文字框、留白、复杂度、色彩对比、画面情绪、不可用区域及原因。Agent 未实际看图时，不允许标成模型观察通过。
- [x] 支持 Agent 候选导入、本地启发规则、人工直接写入计划三种方式，模型不可用时报告 `UNAVAILABLE` 而不是伪造分析。
- [x] 支持镜头 `skip/silence` 以及 `reason_code`；人工覆盖优先，零事件不报错。
- [x] 使用 `static_comic/emphasis_layout.py` 在**多帧运镜后画面**检查安全区、主体/嵌入文字框、字号、描边、阴影和放大超调极值。
- [x] 尝试有限的 `upper_left/upper_right/left_center/right_center/lower_side` 等位置；无安全区则自动 `SKIPPED` 或用户固定时 `REVIEW_REQUIRED`。

### 声学/镜头锚点

- [x] 与 `speech.apply_alignment()` 的证据重放方式一致，使用 `reading_map.source_ranges` 和 `characters` 定位关键词的真实发音采样。
- [x] 原文以去 BOM 后 Unicode **码点半开区间**索引；重复词、数字读法、百分比、标点、表情符号、CRLF 要完整测试。
- [x] 仅可靠 `acoustic_aligned` 字符可自动标注声学精确起止；无法确认时不得平均摊派时间。允许沿用已有人工边界/窗口覆盖流程，并保留其不同证据等级。
- [x] 使用 `frame_at()`、`compile_timing()` 计算事件全局帧和镜头稳定窗口。事件默认不跨切镜/转场，不得把 Sequence 局部帧当全局帧。
- [x] 对可独立触发的音效生成声学、镜头起点或转场帧锚点，编译为 48kHz 的全片整数样本；引用视觉节点的音效必须与实际选中视觉事件关联。
- [x] 统一输出 `work/emphasis/{proposals,observations,visual.lock,sfx.lock,diagnostics}.json`，保留稳定跳过原因和源证据摘要。
- [x] 对超出密度、事件互斥、固定项冲突、负样本、音效尾部越界进行明确判定。

### 主要文件

`static_comic/emphasis_vision.py`、`emphasis_layout.py`、`emphasis_timing.py`、`emphasis.py`、`static_comic/project.py`、`static_comic/timeline.py`（尽可能不更改其时钟规则）、相关 Schema/测试。

### 自动化验收

- [x] 漫画人物居中且四周复杂：自动零文字，有明确 `VISUAL_BUSY/NO_SAFE_REGION` 等证据。
- [x] 情绪沉静镜头：能够同时选择零文字、零音效。
- [x] 有留白的镜头：候选文字位置在多帧峰值包围盒检查中合法。
- [x] 已审核截图/运镜变化后，旧观察报告必定被判过期。
- [x] 重复中文片段和 `300%` 一原文字符对应多个读法字符仍能准确映射或返回待审。
- [x] 镜头转场边缘、文字与音效同步锚点均可从全局采样/帧数反推，无浮点累积漂移。
- [x] 人工固定与自动候选冲突时保留固定项、拒绝非法执行计划。

**阶段验收结果**：真实镜头抽帧、视觉观测证据、逐镜头决策清单、两个锁定事件文件和跳过/冲突诊断。

---

## SC-K3：全片文字轨和分级高级特效

**目标**：完成正式 Remotion 画面执行，并让一级文字动画与少量可控二级特效可以由同一轨道渲染。

### Remotion 组件

- [x] 在 `ComicVideo.tsx` 中于 `TransitionSeries` 后方添加 `VisualEmphasisOverlay`，不修改现有 `StaticShot` 运镜和转场预算。
- [x] 每个视觉事件用全片 `Sequence from=start_frame durationInFrames=end_frame-start_frame`，动画函数只由锁定数据和整数帧驱动。
- [x] 创建 `renderer/static-comic/src/emphasis-presets.tsx`，提供 `soft_rise`、`comic_pop`、`comic_burst`、`number_tick`、`underline_reveal`、`stagger_group` 六类一级模板。
- [x] 所有模板统一暴露 `enter_start`、`impact`、`settle`、`exit_start` 等可绑定音效的关键节点，确保节点由实际视觉时序计算而非模型猜测。
- [x] `number_tick` 必须与原文的真实数值和单位一致；遇无法解析的金额/百分比不能生成伪造数值。
- [x] 固定字体文件、字号、字形覆盖率、规范化布局坐标、阴影与描边，使用 `delayRender()` 或当前版本支持的字体加载等待机制消除加载闪帧。
- [x] 实现不少于两个二级模板，建议 `ink_reveal` 和 `light_sweep`，使用确定性 SVG/遮罩/缓存数据，检测动态外接框和性能边界。
- [ ] 给 `fragment_disperse`、`particle_assemble` 提供受控扩展接口，要求事件种子固定、粒子数/时长预算有限；未实现功能不得标 PASS。
- [x] 三级透明预渲染特效默认关闭；若实施需验证当前 Remotion 4.0.515 的实际透明帧读取能力，记录帧数、透明通道、资源哈希、可复现缓存与可降级路径。
- [x] 添加 `preview/emphasis_sheet.jpg`：对事件入场、冲击峰值、稳定和退场抽帧。
- [x] 测试旧项目的视觉回归，以及 960×540 预览、1920×1080 正式输出相同逻辑帧语义。

### 主要文件

`renderer/static-comic/src/ComicVideo.tsx`、`VisualEmphasisOverlay.tsx`、`emphasis-presets.tsx`、`emphasis-advanced.tsx`、`Root.tsx`、`contracts.ts`，`static_comic/project.py`、`delivery.py` 及测试/报告。

### 自动化验收

- [x] 六类一级模板至少各有一次**真实渲染输出**，并截图验证入场前、峰值、停留、退出帧。
- [x] 两类二级模板可在锁定环境真实渲染、资源和粒子不越预算。
- [x] 不存在动画重复、字形缺字、转场时跳回、镜头切换后残留、弹性极值裁切。
- [x] 预览与正式帧位语义一致；全片视觉继续无声渲染，音轨只在 FFmpeg 阶段添加。
- [x] 无文字镜头保留静态漫画运镜，且不会产生透明覆盖导致的莫名颜色变化。

**阶段验收结果**：真实 MP4/抽帧、模板测试和性能初值；没有音效也能独立看见文字效果。

---

## SC-K4：整片智能音效库、采样级混音与双母带验证

**目标**：可以为文字、场景、转场、叙事分别配音效，并在保留完整原始旁白的前提下输出混合母带与有声视频。

### 资源与事件

- [x] 实现 `static_comic/sfx_library.py`；素材授权证据、来源/作者、哈希、格式、原始/标准化样本数、音效类别及重复使用范围均可查询。
- [x] 通过 FFmpeg 将音效标准化为 48kHz、立体声 PCM。原始资产不覆盖；内容寻址的音效可跨期复用。
- [x] 支持 `keyword/scene/transition/narrative` 四种类型，每个镜头允许 `silence`，与文字 `skip` 互不影响；须拒绝从上一镜头延伸到 `silence` 镜头逻辑窗口内的音效尾部，或在充分留出淡出时间后调整。
- [x] `visual_marker`、`speech_start`、`shot_start`、`transition_frame` 四种锚点有严格 Schema，音效事件锁定 `start_sample`、长度、增益、淡化、权限和来源。
- [x] 用户固定时间/音效发生冲突时需人工调整，自动候选可稳定跳过，输出 `SKIPPED` 与原因。

### FFmpeg 混音

- [x] 实现 `static_comic/sfx_mix.py`；按 argv 调用 FFmpeg，滤镜图由可信代码生成。不能直接执行 Agent 提供的滤镜命令或脚本。
- [x] `adelay=...S` 进行样本级延迟；输入音效先完成受控剪裁、增益和淡化。超时/越界、负值及过大音效长度拒绝。
- [x] 生成 `work/audio/sfx_stem_48k.wav` 与 `work/audio/mix_48k.wav`；当音效为空时，应走现有完整旁白封装分支，保证旧项目兼容。
- [x] 确保 `work/audio/master_48k.wav` 原字节与摘要保持不变；混合母带 PCM 长度必须等于真实 `S` 个采样，不使用 `-shortest`。
- [x] 保持人声为主导，对效果 stem 设置最大响度/峰值、事件并发预算和可选旁白驱动压低策略。`alimiter` 若引入延迟必须补偿并测试，不得造成声画错位。
- [x] 修改 `static_comic/media.py`、`delivery.py` 的音频参考，使最终音频与**当前混合母带**核验，同时原始旁白通过完整母带及独立人声 stem 做来源/持续性核验。
- [x] 生成 `reports/mix.json`：音频图、输入哈希、事件清单、过滤参数、开始采样、预期/实际样本数、峰值/响度、削波/编码验证。
- [x] 改造 `mux_product` 和 `visual_product` 的依赖键，让只改音效不重新渲染 Remotion，但当前有声预览和正式封装必须重建。
- [x] 有声预览提供音效表及文字峰值帧审核，新增产物纳入 `review_binding`；用户须完整试听才能批准。

### 主要文件

`static_comic/sfx_library.py`、`static_comic/sfx_mix.py`、`static_comic/media.py`、`static_comic/delivery.py`、`static_comic/cache.py`（仅确有依赖拆分需要时）、`static_comic/emphasis_timing.py`、`static_comic/cli.py`、相关测试。

### 自动化验收

- [x] 四类音效分别完成技术样例，能在未出现文字的镜头播放场景/转场/叙事声音；还能在有文字镜头完全静音。
- [x] 精确样本触发：48kHz/30fps 每帧 1600 样本，合成脉冲检查冲击点一致；编码 AAC 后记录实际容差而非假定 PCM 字节一致。
- [x] 44.1kHz/单声道输入可按契约标准化；不受支持的损坏音效、路径越界、未授权素材必须失败。
- [x] 只有效果音改动：原始旁白、静态漫画、无声视觉缓存有效；混音和有声预览失效。
- [ ] 校验完整母带 `S`、混合母带 `S`、封装单 AAC 音轨、音频可解码、旁白清晰且末尾无截断。
- [x] `sfx_decision=silence` 以及全片音效事件为空时，输出旁白音频满足原有测试行为。

**阶段验收结果**：原始音效、标准化音效、SFX stem、混合母带、真实有声 MP4、音频报告、正反例及缓存命中日志。

---

## SC-K5：真实有声预览、审批、性能与全量回归

**目标**：证明文字/音效自适应系统可端到端生产，技术验收与用户主观审核边界清楚。

### 端到端样片

- [x] 使用**实际运行的技术夹具**生成至少 60 秒的完整有声视频，包括不低于 3 种布局、全部一级动效、至少两种二级动效、零文字镜头、零音效镜头及四类音效样例。
- [x] 至少覆盖两种已实现转场，且转场音效不强制随每次切换出现。
- [x] 保存所有视觉事件开始/峰值/保持/结束及转场边界的原始分辨率帧图，记录对应全局帧索引与音效起始采样。
- [x] 完整检查 FFprobe 媒体时长、帧率、像素格式、色彩、音频数量、时钟起点，执行完整解码并保留检测日志。
- [x] 检查所有 `text_decision=skip` 的镜头确实未渲染文字，所有 `sfx_decision=silence` 的镜头逻辑窗口内没有任何新增音效（包括跨镜头尾部）；相邻镜头允许尾部延续的情况也必须有明确的时间区间和审核记录。
- [ ] 在真实来源已批准的漫画和真实配音上走完整生产审批流程；素材缺失时标记 `NOT_RUN`，不可自动伪造批准。

### 性能、缓存和回归

- [x] 同设备、同编码参数比较基线漫画、一级文字、二级文字、含 SFX 混音的视频耗时与峰值内存，记录冷/热缓存差异。不得预填“开销小”或捏造数据。
- [x] 单独修改文字、字体、运镜、旁白、一个声音素材、声音增益、转场，观察重编译范围和旧审批的拒绝行为。
- [x] 特别证明：**只改音效时无声视觉缓存命中；只改文字时旁白模型对齐不重跑**；如果动画节点改变导致关联音效时间变化，必须只重编译相关效果轨与混音。
- [x] 检查源材料哈希、用户审核来源和时区时间；旧用户批准不允许直接升级到新视频。
- [x] Python/Remotion 回归已执行且无失败，新增用例覆盖关键回归；质量审查没有过期测试夹具混入生产。实际为全量 Python 240 PASS / 1 SKIP，补充契约 18 PASS / 1 SKIP、新增增量 6 PASS，Node 89 PASS；未执行项不计 PASS。
- [x] 更新 `SKILL.md`、`references/emphasis.md`、CLI 帮助、测试文档、阶段验收记录。

**完成标准**：实际技术短片、真实媒体检测、合约正反例、缓存证明、真实生产审图/试听流程（条件具备时），以及用户最后的正式画质确认。主观审美、旁白可懂度和音效恰当性不能被静态 JSON 断言取代。

---

## 附录 A：必测负向用例清单

| 编号 | 输入/操作 | 期望状态 |
| --- | --- | --- |
| N01 | 老项目无任何 `emphasis_*` 输入 | 保持旧链路成功，不要求字体/SFX 清单 |
| N02 | 镜头 `text_decision=skip`，但 Agent 仍提交词条 | 编译拒绝该词条或产生可追踪 `SKIPPED` |
| N03 | 镜头 `sfx_decision=silence`，但存在关联音效候选 | 无新增该镜头音效，保留原因 |
| N04 | 用户固定文字占据主体，动态缩放后越界 | `REVIEW_REQUIRED`，不能自动挪动或删除 |
| N05 | `script_range` 指向重复词的错误位置 | 精确校验失败，不能首次匹配猜测 |
| N06 | `300%` 的原文与多个中文读法字符时间映射 | 所有读法字符一起校验；来源不足待审 |
| N07 | 字符低分数/缺失，仅有粗识别时间 | 不能编译声学精确词条 |
| N08 | 文本刚好靠近镜头 wipe/fade_black 重叠 | 稳定展示窗口验证通过或跳过 |
| N09 | 字体文件哈希、授权或字形覆盖不合法 | 拒绝正式产出 |
| N10 | 三级透明特效不可解码或缓存损坏 | 明确回退/失败，并重新预览 |
| N11 | 音效素材版权不明、路径越界、未知编解码格式 | 拒绝生产，输出资产 ID |
| N12 | 音效计划负延迟、尾部溢出、非有限增益 | 拒绝/待审，不裁母带 |
| N13 | 混音滤镜引入额外延迟 | 脉冲同步回归能发现并要求修复 |
| N14 | `amix` 默认缩小旁白而未显式配置 | 音频能量/增益验证发现，不能视为通过 |
| N15 | SFX 变更但视觉 `render` 重新执行 | 缓存测试 FAIL，需要拆分构建键 |
| N16 | 字体/声音更新后旧预览收据仍有效 | 审核绑定测试 FAIL，必须失效 |
| N17 | 预览加音效后出现第二条音频流或源旁白截断 | 媒体验收 FAIL |
| N18 | 本地视觉模型/音效提供者不可用 | 明确 UNAVAILABLE，可经人工/规则路径继续，不能伪造已分析 |

## 附录 B：CLI（已实现；技术夹具需显式添加 `--technical-fixture`）

```powershell
# 所有命令均从 .agents/skills/static-comic-video/ 目录执行
.venv/Scripts/python.exe -m static_comic emphasis propose --project <episode> --provider rules
.venv/Scripts/python.exe -m static_comic emphasis import --project <episode> --file <proposal.json>
.venv/Scripts/python.exe -m static_comic emphasis inspect --project <episode>
.venv/Scripts/python.exe -m static_comic emphasis verify --project <episode>
.venv/Scripts/python.exe -m static_comic sfx inspect --project <episode>
.venv/Scripts/python.exe -m static_comic sfx mix --project <episode>

# 继续沿用的现有主要管线
.venv/Scripts/python.exe -m static_comic align --project <episode>
.venv/Scripts/python.exe -m static_comic compile --project <episode>
.venv/Scripts/python.exe -m static_comic preview --project <episode>
.venv/Scripts/python.exe -m static_comic inspect --project <episode>
.venv/Scripts/python.exe -m static_comic render-visual --project <episode>
.venv/Scripts/python.exe -m static_comic mux --project <episode>
.venv/Scripts/python.exe -m static_comic verify --project <episode>
```

新命令应复用现有路径安全、原子输出、缓存报告和 `human-confirm` 审批机制，而不建设另一套独立发布流程。

## 附录 C：阶段报告模板

```json
{
  "milestone": "SC-K1",
  "status": "NOT_RUN",
  "scope": ["schemas/contracts.json"],
  "actual_changes": [],
  "commands": [],
  "tests": [],
  "artifacts": [],
  "cache_evidence": [],
  "human_review": "NOT_RUN",
  "blocking_issues": [],
  "notes": ""
}
```

状态与测试结果只依据实际执行。产物无法创建或本地功能不可用时，明确说明受阻路径及已完成范围。

## 附录 D：可直接交给 Codex 的执行提示词

> 阅读 `docs/智能视觉强调与音效系统-技术方案.md` 与 `docs/智能视觉强调与音效系统-Codex分阶段实施清单.md`。在本仓库 `.agents/skills/static-comic-video/` 内按 SC-K1→SC-K5 逐阶段实现。首要目标是**逐镜头自适应判断是否出现文字、按实际画面和运镜选位置、提供分级可控文字特效、为整片视频独立规划可选音效，并在 FFmpeg 中与完整旁白混音**。先检查工作区 Git 状态、当前契约、音频和视觉处理链以及旧测试，保留所有已有用户修改。
>
> 每阶段先确认变更点/数据协议/验证命令，再编写源码和真实正反例测试；必须保证 48kHz 整数采样时钟、TransitionSeries 外部全片文字轨、原始旁白母带完整、混音 PCM 固定样本数、只改音效复用视觉缓存，以及每次预览/正式交付的人类确认门禁。任何 Agent 模型只输出受控 JSON，不得写可执行动画/滤镜代码或生成用户审批。
>
> 使用本地锁定的依赖和合法素材，禁止擅自下载模型/声音、覆盖已审文件、修改无关目录、清理暂存、提交或推送。每阶段报告实际完成文件、运行命令和结果、缓存命中证据、技术样片、不可用项及人工待审项。技术夹具与真实生产分别汇报，不能将未运行的事项标为 PASS。
