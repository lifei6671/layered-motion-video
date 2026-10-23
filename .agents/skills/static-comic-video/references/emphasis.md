# 智能视觉强调与独立音效（SC-K1～K5）

扩展缺省关闭，旧项目无需字体和音效目录。`input/emphasis_policy.json` 选择视觉和音效两个独立开关；`input/emphasis_plan.json` 为选定计划。Schema 是唯一字段权威，最小策略见 `templates/emphasis/`。不要复制示例占位哈希或将 CANDIDATE 改成已获用户批准。

## 计划、观察与编译

```powershell
.venv/Scripts/python.exe -m static_comic emphasis propose --project <episode> --provider rules
.venv/Scripts/python.exe -m static_comic emphasis import --project <episode> --file work/emphasis/proposals.json
.venv/Scripts/python.exe -m static_comic emphasis inspect --project <episode>
.venv/Scripts/python.exe -m static_comic emphasis verify --project <episode>
.venv/Scripts/python.exe -m static_comic sfx inspect --project <episode>
.venv/Scripts/python.exe -m static_comic sfx mix --project <episode>
```

命令由 Agent 操作。`propose` 只写候选，不覆盖计划；`import` 保留原计划的固定事件和 skip/silence 决定，最终编译仍检查碰撞、声学证据和边界。直接人工编辑选定计划可解除明确排除。`excluded` 以事件 ID 排除候选，固定项与排除冲突进入 REVIEW_REQUIRED。命令返回 PASS 是技术状态，不签发任何用户批准。

规则提供者只按真实像素的边缘/明暗、已标注主体以及原文数值/少量叙事词产生克制候选；不声称识别画中所有物体或已有文字。没有适合候选即零事件。`--provider agent` 在未配置视觉提供者时返回 UNAVAILABLE，不伪造模型调用。Agent 可以在实际查看当前抽帧后导入受控候选和观察；不接受 HTML、React、CSS、滤镜或任意脚本。

`work/emphasis/observations.json` 保存当前规范化图片开始、四分位、结尾和候选时刻的实际 PNG 路径、摘要、全局帧及证据摘要。规则观察标为 HEURISTIC。人工/Agent 观察写 `input/emphasis_observations.json`，严格协议见 `emphasis_vision.OBSERVATION_SCHEMA`：每个镜头绑定 `evidence_sha256`、全部 `viewed_frames`、主体/嵌入文字/不可用区框、情绪与原因。框坐标是**规范化图片坐标** `[x0,y0,x1,y1]`，不是某个裁切后屏幕坐标；布局器逐帧投影。Agent 必须实际看图，文件中的 DECLARED_VIEWED 仅记录声明，不能认证模型调用。图片、运镜、几何或采样帧改变会拒绝旧观察。

计划原文范围为去 BOM 后 Unicode 码点半开区间，保留 CRLF 和非 BMP 字符。编译在现有 `apply_alignment` 重放通过后，消费该范围对应的**全部**读法字符；300% 不可截取半个读法 token。缺失、低分、插值和粗/人工窗口不冒充精确词时间，返回 TIMING_UNCERTAIN。人工边界/窗口仍使用原 overrides 流程重新对齐；没有可靠字符时可以跳过该事件。

## 视觉与资源

`visual.lock.json` 和 `sfx.lock.json` 分开保存事件与输入摘要；`diagnostics.json` 保存接受、跳过、固定冲突及观察绑定。技术夹具放入 `work/emphasis/technical`。视觉锁进入可选 `props.visual_emphasis`；无事件不增加覆盖层。文字在 TransitionSeries 外以全局 Sequence 渲染，不修改 StaticShot。

六个一级模板：soft_rise、comic_pop、comic_burst、number_tick、underline_reveal、stagger_group。两个二级模板：ink_reveal、light_sweep。fragment_disperse、particle_assemble 的受控枚举入口明确 UNAVAILABLE；三级预渲染不可启用。number_tick 仅接受可准确解析的阿拉伯数及白名单单位，单行文字不接受换行/制表符；未支持的输入明确拒绝或跳过。

布局检查所有运镜物理帧、主体和已提供的文字/不可用区，使用模板 1.18 倍缩放、12px 平移、缩放后的描边和三倍阴影包络。中文字体使用 hhea/OS2 最大行度量，浏览器加载实际字体后再次用 SVG getBBox 验证；字体缺字、载入失败或占位失配阻止渲染，不替换字体。number_tick 中间数值按最宽数字预算；stagger 关闭连字/kerning。字体解析复用锁文件已有 fontTools/Pillow；WOFF2 所需解码器缺失会失败，不隐式安装。

字体、音效必须具有本地来源/作者、许可描述、许可附件、资源 SHA256 和适用范围；这与既有图片的本地使用规则相互独立，源于本扩展需求，不反向增加图片审批条件。验证只能证明记录完整性，不能认证第三方权利真实性。正式资源要求 APPROVED；TECHNICAL_ONLY 仅用于明确技术入口。字体进入受控 public/fonts；音效不进入 public。候选资源不能因转换成功自动批准。

## 混音、缓存和审核

关键词、场景、转场、叙事音效独立规划；支持 visual_marker、speech_start、shot_start、transition_frame 锚点。视觉节点为实际锁定的 enter_start/impact/settle/exit_start。48kHz / 30fps 每帧1600样本；所有新增声音用绝对整数样本。silence 不影响旁白，但任何新增音效尾巴不得侵入该镜头逻辑窗口；自动候选跳过，固定冲突待审。

FFmpeg 把已验证原始音效转为独立48k双声道PCM，以源/工具/代码摘要缓存。每个事件受控裁剪、增益、淡化与 `adelay=…S`，`amix normalize=0` 保留原旁白增益。`master_48k.wav` 原字节不变；输出 `sfx_stem_48k.wav` 与恰好S采样的 `mix_48k.wav`。无效果直接回到原母带，即使磁盘残留旧mix也不引用它。混音超峰值拒绝，不引入有延迟的limiter或自动裁旁白。

`reports/mix.json` 记录实际音频图、输入摘要、事件非零窗口、原/标准化样本数、峰值、RMS与旁白逐样本求和核验。RMS不是LUFS/true-peak；当前没有sidechain。标准化资产采用内容寻址，可复制已获得的原素材跨期复用；构建缓存仍按单期保存，没有共享全局缓存。

纯音效变化保留视觉 props/public 与视觉缓存；混音及AAC封装重建。文本改变不调用 ASR/WhisperX；若视觉节点变化，关联音效重编译。快照同时绑定原母带、当前混合母带、音效计划、字体与观察；旧试听/正式画质批准不可复用。`preview/emphasis_sheet.jpg`、事件表、实际关键帧及mix报告进入试听绑定，`inspect` 审核页面提供入口。最终AAC与当前音频参考核验，原母带仍独立验证。


## 资源审核与智能体候选入口

正式字体和音效除了来源、权利附件与字节摘要，还必须有当前资源的独立人工签署记录。设置清单中的 `review_status=APPROVED` 不能替代真人批准。签名绑定 `asset_sha256` 与包含许可/来源/用途的 `asset_manifest_sha256`，变更任意元信息都会使收据过期。技术夹具的 `TECHNICAL_ONLY` 仍与生产路径隔离。

```powershell
.venv/Scripts/python.exe -m static_comic emphasis prepare-resource --project <episode> --asset-kind font --asset-id <id>
.venv/Scripts/python.exe -m static_comic human-confirm --project <episode> --scope resources --input review/resource-proposals/font-<id>.json
.venv/Scripts/python.exe -m static_comic emphasis approve-resource --project <episode> --file review/human-confirmations/<signed-hash>.json
```

音效将 `--asset-kind` 改成 `sfx`；人类应先实际查看资源、许可和用途，再通过既有终端或真实聊天确认流程签署。签署结果保存在 `review/emphasis_resource_approvals.json`。Agent 只能准备建议，不代签。

规则规划入口只对可靠且有资产标签支持的信息提出候选：原文数值对应关键词、明确转折对应叙事、画面观察与文案同时指明的动作对应场景、已确认高能量转场对应转场音效。没有匹配授权音效时保持零事件。外部视觉智能体必须真正阅读 `work/emphasis/frames/` 下的当前画面，依据镜头证据写入当前 `input/emphasis_observations.json` 和受控计划，再执行：

```powershell
.venv/Scripts/python.exe -m static_comic emphasis propose --provider agent --file <episode-relative-agent-plan.json> --project <episode>
.venv/Scripts/python.exe -m static_comic emphasis import --project <episode> --file work/emphasis/proposals.json
```

命令只验证实际提交的 Agent 数据和当前观察摘要，不内置视觉模型，也不把 `DECLARED_VIEWED` 当成模型调用凭证。没有提交文件或可靠图像观察时仍明确报告 `UNAVAILABLE` 或拒绝。每镜头可以零文字、零音效，仍需有声预览审核。

当前单镜头视觉并发仅支持 1；`selection=manual` 仅接受人工固定并声明 `layout.x/y` 的事件，不自动挪到其他候选位置。`allow_tail_trim=true` 允许将音效尾部裁至母带末端/静音镜头起点，并自动增加尾部短渐隐；其余情况按冲突跳过或要求人工修订。音效解码以采样量和字节预算限制单个素材（上限约 120 秒），压缩体积不代表可用的 PCM 时长。预览关键词关键帧合并去重后按每批最多 128 帧统一提取。

## 技术验收与开源复用

```powershell
.venv/Scripts/python.exe scripts/create_emphasis_fixture.py --output <new-empty-technical-directory>
.venv/Scripts/python.exe -m static_comic preview --project <technical-directory> --technical-fixture
.venv/Scripts/python.exe scripts/verify_emphasis_probe.py --project <technical-directory> --output <new-probe-directory> --performance
```

夹具明确使用合成音轨和 TEST_ONLY 字符证据，不调用模型，不作为真实旁白对齐质量证据。已有本地 LXGW WenKai 字体只读复制到技术目录，保留字体内嵌OFL声明；不下载素材。探针执行真实Remotion/FFmpeg、完整解码及缓存/性能测量，不能签发生产批准。生产素材和人工审图/试听/正式画质必须另行满足现有门禁。

GitHub检索后采用已有依赖的公开实现：

- [Remotion](https://github.com/remotion-dev/remotion)：复用锁定4.0.515的Sequence、字体加载等待和确定性帧驱动；遵守现有Remotion许可上下文。
- [FFmpeg adelay](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/af_adelay.c) 与 [amix](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/af_amix.c)：复用本机FFmpeg二进制，未复制/改写上游源码。
- [LXGW WenKai](https://github.com/lxgw/LxgwWenKai)：已有本地字体，内嵌SIL OFL 1.1声明与作者记录。
- 检索到的 `mcostanzo1/remotion-animated-text` 未声明许可，未复制。没有引入额外动画框架或音效库下载。
