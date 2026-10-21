# SC-P4 原画语义转场规划

本阶段由 Agent 实际看图提出离散候选，Python 校验来源和时钟，用户确认语义。没有图片识别服务客户端、自动特效轮换或任意 React/Shell 执行。默认优先考虑有理由的硬切；不设置效果多样性配额。

## 生产入口与流程

先完成 SC-P3A 的全部图片批准和 SC-P3 的语音对齐/纠错。只读取与当前来源、许可、图片哈希及用户收据一致的正式原画。未批准候选、reference_only 或技术 timing 不能进入规划器。旧分镜在语音对齐前可保留有效占位硬切；没有 P4 确认仍无法正式编译。

在 Skill 根目录执行，--project 是本期目录，--input 是本期相对 JSON 路径：

```powershell
.venv/Scripts/python.exe -m static_comic transitions prepare --project <episode>
.venv/Scripts/python.exe -m static_comic transitions propose --project <episode> --input work/planning/proposal.json
.venv/Scripts/python.exe -m static_comic transitions report --project <episode>
.venv/Scripts/python.exe -m static_comic transitions confirm --project <episode> --input review/semantic-decision.json
.venv/Scripts/python.exe -m static_comic transitions apply --project <episode>
.venv/Scripts/python.exe -m static_comic compile --project <episode>
```

prepare 输出 transition_input.json 和 transition_proposal.template.json；propose 输出 transition_candidates.json，均在 work/planning 下。候选不会修改分镜。confirm 只写逐边界人工收据，允许分批批准或驳回；全部非末边界批准后 apply 才更新 storyboard。编译器仍独自计算整数帧、保持帧和实际窗口，不接受 Agent 填写 pre_frames / physical_frames 等预算字段。

候选状态 READY_FOR_REVIEW 仅表示结构和证据校验可供审核，不是批准。REVIEW_REQUIRED 会按边界记录缺失/冲突。输入错误退出 2；命令处理成功退出 0，但必须读取返回状态。只有一个镜头时没有非末边界，编译无需转场确认。

## Agent 必须完成的看图工作

prepare 已返回相邻正式图片路径、完整来源条目和用户批准收据。用实际图片查看工具打开两张原画，核对主体、人物身份、布局、视线/运动方向、前后景及叙事连续性；必要时放大查看。不得只看文件名、提示词或缩略图就声称已看原画。

在 proposal 的 author 中记录真实观察者、agent/human、带时区时间、实际工具调用或用户描述来源。viewed_images 按前图/后图记录当前 SHA256；observations 的 before / after / continuity 具体写出看到的物体、动作、构图与连续性。字段检查只能发现缺失及明显空泛记录，不能证明 Agent 真的看过图，更不能替代用户语义判断。

每个非末边界（包括 cut）都提供：

- relation：continuous_narration、reversal、direct_reveal、metaphor、time_or_place_change、chapter_end 或 spatial_progression。
- evidence：相邻原文一侧的准确码点区间和逐字 quote。重复句靠区间定位，禁止猜句子位置。
- visual_evidence、intent：具体解释为什么这样换图、何时让后图完整出现。
- type：cut / fade / fade_black / wipe_from_left / wipe_from_right；duration_frames 为整数，cut=0，非硬切为正数，fade_black≥3。
- placement：start_at_anchor / end_at_anchor / center_on_anchor；anchor_id 只能选 prepare 提供的已核验边界或字符锚点，不直接写模型猜测的秒数。
- wipe 须填写匹配的 direction（from_left 或 from_right）及具体 direction_evidence；含义是新图从该侧开始覆盖，不是旧图退出方向。fade_black 须写 black_interval_reason，解释时间跨越或章节间隔。
- image_text_conflict 如实记录图文冲突。冲突时先修订图或文并重新审批，不能靠转场掩盖。

缺少看图、错误引用、方向不明、语音证据不足、黑场意图不明或预算容量不足都会成为该边界待审事项。共享容量冲突可能同时标记相邻两处；代码不缩短效果、不挪动逻辑边界、不修改配音。规划器可以接受整片有理由的硬切。

## 用户审核

report 生成 review/transitions/index.html，展示前后图、相邻旁白、运镜、停顿、语义意图、候选类型与 SC-P1 计算的窗口。semantic_anchor_frame 是旁白锚点；transition_start_frame / transition_end_frame 是实际半开窗口，内置 fade 的 linearTiming 以 k/L 推进，最后一个窗口帧 end-1 尚未完成，完整后图在 end；自定义 fade_black 使用离散端点，完整后图在 end-1。cut 在锚点直接完整呈现。实际首次可见与完全呈现必须结合具体效果及解码帧核验。逻辑边界与语义锚点不同必须检查原因，不能把两个时机混为一谈。

image/character/方向/反转揭示/淡黑含义都需真实用户判断。明显但无依据的效果应驳回；不是出现五种效果才算通过。以 transitionDecision 提交候选摘要、真实 human 和明确 items，每项包含 from_shot_id、to_shot_id、APPROVED/REJECTED、reason 和 checks（semantics、visual、timing、direction、style_continuity）。仅明确接受全部检查且没有待审事项的边界能批准。不能填写 TEST ONLY 或冒充用户。

confirm 不等于 apply；apply 不等于已编译或有声预览批准。批准记录绑定完整候选及源上下文，逐边界/批次事件保存于 review/transitions/events。后续驳回、修改候选、改变图片/来源/许可/原文/音频/运镜/语音纠错会使生产门禁失败，必须重新 prepare、看图、提案和确认。不得通过编辑派生候选或 input JSON 伪造通过，系统会重算检查。

## 语音证据重放与审计

SC-P3 对齐和人工 overrides 原本绑定完整 storyboard 的字节摘要。P4 apply 仅允许改 transition_out；先验证原有证据，再使用同一音频、coarse_ref、plan、原始 windows 重算，更新分镜绑定，不运行 ASR 或加载新模型。字符、读法、语音区间和人工边界证据必须完全不变。

旧分镜、aligned 和 overrides 保留于 work/planning/history；旧 raw 永久保留，新的 raw 用 replay_of 引用旧 raw。若存在 overrides，仅更新外层 storyboard_sha256，用户 entries 保持原样；这是本次语义确认引发的显式重绑定，不把用户原确认日期改成当前日期。任何语音计划变化会失败，需显式修复/align。

apply 先完成全部验证及输出路径预检，再写分镜和重放证据；整批事务/多进程互斥仍属于 SC-P6。若异常中断导致文件不一致，后续门禁会拒绝，不能继续用旧 public/预览。每次渲染前必须重新验证、编译。

## 开发与真实制作的区别

scripts/create_transition_demo.py 在新空目录创建六张几何测试图、合成静音/字符时间与 TEST ONLY 收据，覆盖五种效果及三个 placement。它测试生产形状的数据路径、生成候选/确认分镜/锁定时间线，不是实际人物漫画的语义验收。不得把示例的审批、工具能力或许可复制到真实项目。

当前没有本期真实已审批原画，因此真实图片语义候选和人工语义验收为 NOT_RUN。实际一期必须沿用上述完整流程，通过后进入 SC-P5 有声预览，不扩展自动生图、物体变形或自定义 presentation。

## 本地确认来源

候选报告展示后，Agent 仅准备 transitionDecision 建议。用户通过 [human-confirm](human-confirmation.md) 的 transitions scope 签发；confirm 和每次生产 approved 验证完整负载与逐边界 item。普通 human/evidence 字符串、变更的候选或旧边界记录不能放行。apply 的多文件写入复用 cache.publish，可捕获失败回滚；断电混合状态仍须重新检查并恢复。
