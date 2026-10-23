---
name: static-comic-video
description: 开发和检查中文静态漫画视频合成工作流的项目级 Skill。用于原文、完整配音和静态分镜图片的校验、中文语音对齐、三渠道供图与审图、语义转场确认、Remotion 运镜、有声预览批准、正式封装与缓存恢复；已实现 SC-P0/P1/P2/P3/P3A/P4/P5/P6，SC-P7 尚未完成。
---

# 静态漫画视频合成

## Agent 执行与用户参与

用户提出制作需求后，Agent 连续完成已授权工作：检查已有输入与决定、准备必要依赖、拟定分镜与提示词、调用工具、下载或接收图片、归档命名、填写 JSON/YAML、计算摘要、执行校验、打开审核页面、记录聊天回复、渲染封装及失败修复。本 Skill 中的命令、路径、模板和字段说明都是给 Agent 的操作说明，不要复制成用户作业。

只向用户索取无法从当前文件或对话取得的原文/配音/素材、会改变内容方向的选择，以及当前图片、语义转场和成片效果的真实确认。先完成技术检查并给出可审查结果；可按整批图片或整段转场统一确认，不逐镜头重复提问，不要求逐个勾选内部字段。已明确的渠道、风格和决定直接沿用；同一回复明确覆盖多个已展示范围时，Agent 分别记录对应收据，不再问一遍。素材或决定实质变化时只重审受影响内容，不能代替用户批准。

仅用户主动选择 `manual_generate`，或缺少 Agent 无法访问的输入、账号登录/平台权限时才需用户操作；说清具体缺口，尽量只请用户提供文件或完成登录。Agent 自行完成重命名、复制、格式转换、收据与参数整理。工具不能用时先诊断已授权路径；不把报错或可自行完成的安装步骤直接转交用户，也不擅自改变用户选择的图片渠道。

先读取 [运行基线](references/runtime.md)，据实际状态执行。开发验收记录和测试数据属于本机资料，不随 Skill 源码提交，也不是使用本 Skill 的前置阅读要求。

SC-P1 已提供 `validate` / `compile --project <episode-directory>`。使用前读取 [输入编译协议](references/contracts.md)。编译器只写时间线、几何审核预览、props 与图片快照，不渲染视频。生产路径要求有效用户渠道确认及逐图批准；`--technical-fixture` 仅用于独立技术夹具，不能代替人工审核。

SC-P2 已提供 Remotion Composition、五种运镜、五类转场、Studio 和无声 H.264 技术短片。使用前读取 [视觉执行协议](references/rendering.md)。技术入口为 `renderer/static-comic/src/technical.tsx`；普通入口 `src/index.tsx` 拒绝技术夹具。淡黑最少 3 帧，正式使用仍需后续阶段审批，不把技术探针成功当成成片验收。

SC-P3 已提供 `align --project <episode-directory>`、完整 PCM 母带、原文/读法/时间映射及人工覆盖。先读 [语音与纠错协议](references/speech.md)。生产编译要求有效对齐证据；默认优先调用本机 VoiceStudio 粗识别，再使用已锁定中文模型补齐字符对齐。技术 PASS 不代表真实用户已经逐边界试听。

本 Skill 的代码、依赖与渲染器全部位于本目录。`static_comic/` 是 Python 模块；`renderer/static-comic/` 是独立 Remotion 工程；`scripts/` 是模型准备辅助脚本。单期素材与输出另放在调用项目的 `content/<episode_id>/`，不要写进 Skill 或公共素材目录。

SC-P3A 已提供 `images` 子命令：先读 [图片供应与审图协议](references/image-supply.md)。新一期先检查已有渠道选择；混合映射及分镜请求经用户确认后，Agent 调用已选择的可用工具，或在用户选择人工供图时交付提示词。导入候选、展示审图报告、记录真实用户逐图或整批批准后，运行 `images verify`。未通过不得进入 SC-P4。不可把测试收据或旧 props 当作当前批准；每次渲染先重新验证并编译。

本 Skill 的任务是制作本地视频，不执行对外发布或商业授权审核。不要询问盈利、商用、发布平台，不索要授权证明或版权承诺，不把这些内容作为制作门禁。`publication_scope`、license、license_evidence、publication_rights、attribution_ready 等是可选历史备注；缺少或否定商业/发布许可不阻塞本地导入、审图、编译和导出，也不要为放行伪填 true。有现成信息则据实保留，没有则省略；原图、工具输出和用户内容确认仍按实际记录。

SC-P4 已提供 `transitions prepare / propose / report / confirm / apply / verify`：先读 [语义转场协议](references/transitions.md)。Agent 必须查看当前已批准正式原图，再为每个非末尾边界填写具体语义、视觉证据与效果理由。候选报告可整批交用户确认，Agent 将明确批准映射到已展示边界，不逐边界索要重复回复。确认后 `apply` 只更新分镜转场并重放已有声学证据，物理窗口仍由 `compile` 计算。生产多镜头编译拒绝未确认、已驳回或已过期的语义计划；全部有依据的硬切是有效结果。

## 人工确认入口

生产来源、图片计划、逐图、语义转场、有声预览及正式画质默认在聊天中确认，详见 [确认流程](references/human-confirmation.md)。Agent 展示本次对象和确认范围；用户明确回复后，Agent 记录真实回复，运行 `human-confirm --conversation` 并应用决定。用户不必打开终端、输入摘要或转交收据。已有明确且绑定当前对象的回复直接使用，不重复索要确认。

Agent 负责记录和执行，不能替用户作决定、编造回复或把一个范围的确认扩展到其他范围；引用旧操作说明不等于批准。签名绑定范围、对象及回复记录，保证记录完整性，不认证聊天身份。仅用户主动选择时使用可选终端入口；已有有效终端收据继续有效，无签名历史记录不自动补签。

## 目前可执行

SC-A1～A2 已增加可选 [Earshot 离线音效供应与同步协议](references/earshot.md)。`earshot doctor/list/render/audition/propose-cues` 依赖固定 Git SHA 的本机代码音效库（外部源码放忽略的 reports 内），无模型生成 48kHz WAV、声学峰值和受控素材候选；不能因自动生成通过即获得用户资源批准。选定动态字卡可提出音效动作节点候选，必须在现有 `emphasis import` / 编译 / FFmpeg 混音 / 完整试听链中执行。无音效、无场景证据或未批准资源都允许跳过；Earshot AI 听音模型没有安装，不冒称已分析。

SC-M1～M2 新增可选独立动态镜头轨及非商业动效配方，先读 [混合动态镜头协议](references/motion-cards.md)。`motion propose/import/inspect` 只消费受控 JSON，`MotionCardTrack` 不增加旁白或视频时长、不侵入转场、拒绝任意 React 代码；无计划则完全沿用旧视频。SC-M3 当前仅有保守的字级数字候选，真实漫画图像语义选卡模型尚未接通。上游 video-talkcraft 改编代码为 PolyForm Noncommercial，转交/公开分发须保留版权和许可证信息，不自动复制第三方音效。动态镜头应在当前有声预览统一由用户确认。

SC-K1～K5 新增可选视觉强调与独立音效，先读 [强调与混音协议](references/emphasis.md)。缺省关闭；允许零文字、零音效，保持完整旁白。`emphasis propose/import/inspect/verify` 与 `sfx inspect/mix` 已接入原编译/预览/交付入口，支持六类常规及两类二维模板、逐帧布局、采样级混音与分离缓存。规则观察不冒充视觉模型；粒子和三级特效尚不可用。技术夹具不等于真实漫画、配音或用户验收，阶段实际状态见仓库实施清单。

SC-P5 已提供 `init / status / studio / preview / inspect / approve / render-visual / mux / verify`。先读 [有声交付流程](references/delivery.md)。初始化读取已有图片渠道，缺失才询问；生产预览依赖前述真实图片/语音/语义门禁。Agent 打开当前有声预览供用户完整试听，收到明确意见后自行记录并正式渲染。正式画质单独批准；技术示例不能成为生产批准。每次执行会重新检查输入与审批摘要，不依据旧文件存在判断成功。

SC-P6 已接入阶段缓存及失败恢复，先读 [缓存协议](references/cache.md)。同一期串行执行，检查 reports/cache 的命中原因和 reports/attempt.json 的当前尝试状态。旧成片存在不代表新尝试成功；缓存命中不替代当前来源一致性、语义与完整试听批准。Agent 处理可恢复错误并重跑，不要求用户运行恢复命令。不要并行写同一期，也不要添加分段渲染或自动代批。

SC-P7 正在制作真实样片，Windows 60/180 秒技术负载与性能测量入口见 [性能记录协议](references/performance.md)。测量与真实样片的人工审图、语义、完整试听及正式画质验收分开记录；几何夹具和 TEST_ONLY 收据不能用于生产。真实样片应明确展示已选运镜：需要渐进放大时使用 zoom_in 并检查全程主体、放大风险及细线画质；不能把静态图片理解为固定画面。转场按叙事选择，用户要求多类效果时给出具体方案，不机械轮换。改运镜可复用采集图片，但必须更新几何审核、语义与预览批准。SC-P7 的人工供图真实用例和人工活跃耗时测量仍未完成。

按用户当前约定，先检查 `http://127.0.0.1:13900` 的 VoiceStudio 服务：运行 `scripts/probe_voicestudio.py --url http://127.0.0.1:13900 --output reports/voicestudio.json`。先评估服务是否满足任务，再准备缺失的本地能力；优先复用已有模型，不重复下载。该脚本只做 HTTP 能力发现，成功不代表识别或强制对齐通过。当前接口差距见 [服务评估](references/voicestudio.md)。

在本目录按 [运行基线](references/runtime.md) 安装锁定依赖，以 `.venv/Scripts/python.exe -m static_comic doctor` 检查环境。`doctor` 不安装依赖、不下载模型、不获取图片。任何必要检查未通过，退出码为 1，报告保留各项 `PASS` / `FAIL` / `NOT_RUN` / `UNAVAILABLE`。

模型先明确准备，再用 `scripts/lock_models.py` 记录路径、revision 和全部文件 SHA256。`doctor --models-lock ... --browser ...` 会核验模型字节、离线加载并执行合成输入探针；这不是中文语音准确性验收。

## 后续实现与生产边界

本仓库权威方案为 [V2.0](../../../docs/静态漫画视频自动合成引擎.md) 和 [阶段清单](../../../docs/静态漫画视频自动合成引擎-分阶段实施清单.md)。按 SC-P0→SC-P1→SC-P2→SC-P3/SC-P3A→SC-P4→SC-P5→SC-P6→SC-P7 的依赖推进。原方案的 `renderer/static-comic/` 在本 Skill 内解析；不要在仓库根再维护一份渲染器。

- Python 负责受控数据、输入边界、唯一整数采样/帧时钟和审核；Remotion 负责整片无声视觉；FFmpeg 负责音频、封装和验证。首版 1920×1080、30 fps，无字幕。
- 每期生产先确认 `agent_generate`、`third_party_retrieve`、`manual_generate` 或 `mixed`；混合需确认逐镜头渠道。未确认保持 `SOURCE_POLICY_PENDING`。工具不可用应报告，不自动换来源。
- 所有入镜图片必须有实际来源记录、内容哈希及真实用户审图收据；不要求商业授权或发布许可证据。人工放图、生成成功、模型评价都不等于批准。测试夹具不得成为生产已审素材。
- 仅使用受控运镜和五类转场：`cut`、`fade`、`fade_black`、`wipe_from_left`、`wipe_from_right`。候选基于实际看图与旁白证据，不强制效果多样性，不执行候选中任意代码。
- 真实有声预览批准、语义审核、完整试听和正式画质分别留证。AI 不代批，不通过截断配音或 `-shortest` 掩盖帧时长差。
- SC-P8 仅在真实瓶颈出现并另获授权后实施；不加入字幕、TTS、音乐、角色动画、队列或分段缓存。
