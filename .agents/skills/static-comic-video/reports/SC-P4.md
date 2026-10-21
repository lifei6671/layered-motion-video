# SC-P4 开发与验证记录

范围：阶段清单 SC-P4-01～05 的代码与协议实现，仍位于本 Skill。没有新增依赖、下载模型或调用外部生成服务，没有提交或推送。真实一期原画及用户语义验收未执行，不把合成测试当作阶段制作验收。

## 实现与验收对应

| 任务 | 实现 | 验证 |
| --- | --- | --- |
| 01 输入输出契约 | plannerInput 包含当前正式原画、来源、图片批准、相邻原文、运镜、停顿与可信语音锚点 | 拒绝未审图片、过期上下文和修改后的锚点/原文 |
| 02 离散候选 | 关系、准确引用、看图记录、视觉证据、意图、五类效果、整数帧、三种 placement、观察者记录 | Python/Ajv 共用 13 项有效/无效用例；未知 React/Shell、浮点帧和物理预算字段拒绝 |
| 03 候选与执行分离 | prepare / propose / report / confirm / apply / verify；确认后仅更新 transition_out，SC-P1 编译执行窗口 | 未确认、部分批准、拒绝及应用后撤回阻断生产；全部硬切可通过 |
| 04 逐边界待审 | 缺看图、图文冲突、引用不匹配、方向不明、时间证据不足、黑场理由缺失或容量不足 | 输出边界 issues；不自动缩短效果、挪动边界或改配音 |
| 05 人工语义确认 | 当前候选摘要、明确边界/批次、真实用户证据、五项检查及不可变事件记录 | 更改图片、来源、审批、原文、音频、运镜或语音纠错使旧计划失效 |

操作流程与字段说明见 [语义转场协议](../references/transitions.md)。生产多镜头编译现在必须通过 P4 门禁；单镜头无转场边界，无需语义收据。

## 与语音对齐的衔接

SC-P3 原本绑定完整分镜字节。P4 apply 在验证旧对齐后，只重放同一声学证据并更新转场绑定，不运行 ASR、不加载新模型。字符、读法、语音区间和边界必须保持一致；人工 overrides 的 entries 不变，只更新外层 storyboard_sha256。旧分镜、aligned、overrides 和 raw 留存，新的 raw 通过 replay_of 指向旧记录。非空人工边界纠错的保留有单独回归。

候选只接受受验证的边界或字符锚点；最终 start/end、pre/post 和保持帧全部由原编译器计算。语义锚点与效果完成时机分别展示。尚未实现 SC-P6 的整批事务与互斥，中断后的不一致会被后续校验拒绝。

## 验证证据

- Python：`.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v`，99 tests PASS，包括 16 项新增 P4 行为测试和共享契约用例。[日志](sc-p4/python-tests.txt)
- Node：`npm test`，contracts:check、TypeScript 编译及 63 tests PASS。[日志](sc-p4/node-tests.txt)
- Skill：官方 quick_validate，`Skill is valid!`。[记录](sc-p4/skill-validation.txt)
- CLI：`transitions verify --project reports/sc-p4/demo` PASS。[记录](sc-p4/cli-verify.json)
- 六镜头合成示例：三种图片渠道、五类效果、三个 placement，候选→测试收据→apply→compile 贯通，总长 360 帧。[逐边界页面](sc-p4/demo/review/transitions/index.html)、[结果](sc-p4/demo/review/demo-result.json)
- 全片有理由的硬切另有测试，不把效果多样性当验收条件。

## 独立审查

采用 CHILD_AGENT / Tier 2 / Strict / READ_ONLY。核心 checkpoint 覆盖 7 个冻结文件，独立执行 16 项 P4 测试全部通过，未发现 P0/P1/P2；[记录](sc-p4/checkpoint-review.json)。完整交付目标及最终结论另见 `sc-p4/review-target.json` 与 `sc-p4/independent-review.json`，checkpoint 不等于最终批准。

## 真实制作边界

示例是 SYNTHETIC TEST ONLY 几何图、合成声学窗口和测试收据，仅验证数据协议与生产形状的编译路径。没有声称实际观察过人物漫画，也没有代替用户批准。当前真实原画语义候选、擦除方向/反转揭示/黑场含义、混合来源角色与画风连续性，以及真实用户逐边界确认均为 NOT_RUN。

实际制作必须先取得 SC-P3A 当前有效原画批准，Agent 查看原图并结合配音提出候选，再由用户明确确认。完成这些人工门槛后才进入 SC-P5 的有声预览；本阶段未实现 SC-P5，也未生成或验收真实生产短片。
