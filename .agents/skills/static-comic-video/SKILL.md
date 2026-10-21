---
name: static-comic-video
description: 开发和检查中文静态漫画视频合成工作流的项目级 Skill。用于原文、完整配音和静态分镜图片的校验、中文语音对齐、三渠道供图与审图、语义转场确认、Remotion 运镜、有声预览批准、正式封装与缓存恢复；已实现 SC-P0/P1/P2/P3/P3A/P4/P5/P6，SC-P7 尚未完成。
---

# 静态漫画视频合成

先读取 [运行基线](references/runtime.md) 与 [阶段记录](reports/SC-P0.md)，据实际状态执行，未实现的命令不得当作已可运行。

SC-P1 已提供 `validate` / `compile --project <episode-directory>`。使用前读取 [输入编译协议](references/contracts.md) 和 [SC-P1 验收记录](reports/SC-P1.md)。编译器只写时间线、几何审核预览、props 与图片快照，不渲染视频。生产路径要求有效用户渠道确认及逐图批准；`--technical-fixture` 仅用于独立技术夹具，不能代替人工审核。

SC-P2 已提供 Remotion Composition、五种运镜、五类转场、Studio 和无声 H.264 技术短片。使用前读取 [视觉执行协议](references/rendering.md) 与 [SC-P2 验收记录](reports/SC-P2.md)。技术入口为 `renderer/static-comic/src/technical.tsx`；普通入口 `src/index.tsx` 拒绝技术夹具。淡黑最少 3 帧，正式使用仍需后续阶段审批，不把技术探针成功当成成片验收。

SC-P3 已提供 `align --project <episode-directory>`、完整 PCM 母带、原文/读法/时间映射及人工覆盖。先读 [语音与纠错协议](references/speech.md) 和 [SC-P3 验证记录](reports/SC-P3.md)。生产编译要求有效对齐证据；默认优先调用本机 VoiceStudio 粗识别，再使用已锁定中文模型补齐字符对齐。技术 PASS 不代表真实用户已经逐边界试听。

本 Skill 的代码、依赖与渲染器全部位于本目录。`static_comic/` 是 Python 模块；`renderer/static-comic/` 是独立 Remotion 工程；`scripts/` 是模型准备辅助脚本。单期素材与输出另放在调用项目的 `content/<episode_id>/`，不要写进 Skill 或公共素材目录。

SC-P3A 已提供 `images` 子命令：先读 [图片供应与审图协议](references/image-supply.md) 和 [SC-P3A 验证记录](reports/SC-P3A.md)。新一期必须先运行渠道选择流程；混合映射及分镜请求经用户确认后，才调用已连接且授权的工具或交付人工提示词。导入候选、展示审图报告、记录真实用户逐图批准后，运行 `images verify`。未通过不得进入 SC-P4。不可把测试收据或旧 props 当作当前批准；每次渲染先重新验证并编译。

SC-P4 已提供 `transitions prepare / propose / report / confirm / apply / verify`：先读 [语义转场协议](references/transitions.md) 和 [SC-P4 验证记录](reports/SC-P4.md)。Agent 必须查看当前已批准正式原图，再为每个非末尾边界填写具体语义、视觉证据与效果理由。候选报告交用户逐边界确认，不能代填真实用户批准。确认后 `apply` 只更新分镜转场并重放已有声学证据，物理窗口仍由 `compile` 计算。生产多镜头编译拒绝未确认、已驳回或已过期的语义计划；全部有依据的硬切是有效结果。

## 人工确认入口

生产来源、图片计划、逐图、语义转场、有声预览及正式画质决定必须通过 [本地确认入口](references/human-confirmation.md)。Agent 只准备建议和展示对象，不能自行操作终端签发用户批准。自填 human/evidence 字符串不再有效；本地签名提供流程来源及完整性，不是抵御同权限恶意程序的真人认证。旧批准保留为历史，不自动补签。

## 目前可执行

SC-P5 已提供 `init / status / studio / preview / inspect / approve / render-visual / mux / verify`。先读 [有声交付流程](references/delivery.md) 和 [SC-P5 验证记录](reports/SC-P5.md)。初始化先问图片渠道；生产预览依赖前述真实图片/语音/语义门禁。把当前有声预览交给用户完整试听，收到明确意见才记录批准并正式渲染。正式画质单独批准；技术示例不能成为生产批准。每次执行会重新检查输入与审批摘要，不依据旧文件存在判断成功。

SC-P6 已接入阶段缓存及失败恢复，先读 [缓存协议](references/cache.md) 和 [SC-P6 验证记录](reports/SC-P6.md)。同一期串行执行，检查 reports/cache 的命中原因和 reports/attempt.json 的当前尝试状态。旧成片存在不代表新尝试成功；缓存命中不替代当前来源、许可、语义与完整试听批准。不要并行写同一期，也不要添加分段渲染或自动代批。

SC-P7 正在制作真实样片，Windows 60/180 秒技术负载与性能测量入口见 [性能记录协议](references/performance.md)。测量与真实样片的人工审图、语义、完整试听及正式画质验收分开记录；几何夹具和 TEST_ONLY 收据不能用于生产。真实样片应明确展示已选运镜：需要渐进放大时使用 zoom_in 并检查全程主体、放大风险及细线画质；不能把静态图片理解为固定画面。转场按叙事选择，用户要求多类效果时给出具体方案，不机械轮换。改运镜可复用采集图片，但必须更新几何审核、语义与预览批准。当前进度见 [SC-P7](reports/SC-P7.md)，未完成项不得标为通过。

按用户当前约定，先检查 `http://127.0.0.1:13900` 的 VoiceStudio 服务：运行 `scripts/probe_voicestudio.py --url http://127.0.0.1:13900 --output reports/voicestudio.json`。先评估服务是否满足任务，再准备缺失的本地能力；优先复用已有模型，不重复下载。该脚本只做 HTTP 能力发现，成功不代表识别或强制对齐通过。当前接口差距见 [服务评估](references/voicestudio.md)。

在本目录按 [运行基线](references/runtime.md) 安装锁定依赖，以 `.venv/Scripts/python.exe -m static_comic doctor` 检查环境。`doctor` 不安装依赖、不下载模型、不获取图片。任何必要检查未通过，退出码为 1，报告保留各项 `PASS` / `FAIL` / `NOT_RUN` / `UNAVAILABLE`。

模型先明确准备，再用 `scripts/lock_models.py` 记录路径、revision 和全部文件 SHA256。`doctor --models-lock ... --browser ...` 会核验模型字节、离线加载并执行合成输入探针；这不是中文语音准确性验收。

## 后续实现与生产边界

本仓库权威方案为 [V2.0](../../../docs/静态漫画视频自动合成引擎.md) 和 [阶段清单](../../../docs/静态漫画视频自动合成引擎-分阶段实施清单.md)。按 SC-P0→SC-P1→SC-P2→SC-P3/SC-P3A→SC-P4→SC-P5→SC-P6→SC-P7 的依赖推进。原方案的 `renderer/static-comic/` 在本 Skill 内解析；不要在仓库根再维护一份渲染器。

- Python 负责受控数据、输入边界、唯一整数采样/帧时钟和审核；Remotion 负责整片无声视觉；FFmpeg 负责音频、封装和验证。首版 1920×1080、30 fps，无字幕。
- 每期生产先确认 `agent_generate`、`third_party_retrieve`、`manual_generate` 或 `mixed`；混合需确认逐镜头渠道。未确认保持 `SOURCE_POLICY_PENDING`。工具不可用应报告，不自动换来源。
- 所有入镜图片必须有来源、权利证据、内容哈希及真实用户审图收据。人工放图、生成成功、模型评价都不等于批准。测试夹具不得成为生产已审素材。
- 仅使用受控运镜和五类转场：`cut`、`fade`、`fade_black`、`wipe_from_left`、`wipe_from_right`。候选基于实际看图与旁白证据，不强制效果多样性，不执行候选中任意代码。
- 真实有声预览批准、语义审核、完整试听和正式画质分别留证。AI 不代批，不通过截断配音或 `-shortest` 掩盖帧时长差。
- SC-P8 仅在真实瓶颈出现并另获授权后实施；不加入字幕、TTS、音乐、角色动画、队列或分段缓存。
