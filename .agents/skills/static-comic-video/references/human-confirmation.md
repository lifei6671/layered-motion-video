# 聊天确认流程与信任边界

默认由用户在聊天中确认，Agent 完成记录、签发和执行。不要要求用户打开终端、抄摘要或转交收据。`actor_role=human`、时间和无签名 evidence 字符串不能独立通过生产门禁；Agent 应使用下面的入口记录真实回复。

## 默认流程

1. Agent 准备当前决定，展示可审查对象、范围和关键选择；需要看图或试听时，同时提供报告、图片或视频。来源确认只覆盖来源，不能推导为分镜、图片计划、逐图、转场或成片批准。
2. 用户明确回复后继续执行。如果上一条待确认消息只对应一个清楚的对象和范围，回复“确认”“同意”即可；已有明确覆盖当前对象的真实回复直接使用，不再要求复述摘要。存在多个未决对象或回复含义不清时，只澄清歧义。引用旧说明、抱怨流程、沉默、技术测试通过都不是批准。
3. Agent 将用户的决定和检查项写入建议 JSON，并记录真实回复。不得编造回复、从“预览可生成”推导“已完整试听”，或把拒绝改为同意；用户拒绝时记录契约支持的 REJECTED，policy/plan 取消则不签发批准。
4. Agent 调用 `human-confirm --conversation`，再把返回的签名文件直接交给对应应用命令。整个过程不需要用户操作命令。若待确认对象已变化，重新展示变化后的对象，不能把旧回复绑定到新对象。

确认按可审查批次组织，不按命令或内部字段组织。用户明确确认整批图片或全部已展示转场时，Agent 将这一回复记录到对应 items；不用再逐张、逐边界提问。一次回复明确涵盖多个已展示范围时可分别生成对应 scope 收据，不要求重复回复。安装依赖、执行命令、计算坐标与摘要、保存记录不是新的确认点。版权、商业用途和署名不属于本地制作的必答或必勾选项目。

聊天证据 JSON 由 Agent 写入本期 `review/`，格式如下。`thread_id` 必须是真实会话 ID，`message_id` 可选，仅能使用实际可取得的消息 ID；`user_message` 保留用户原话，不改写为 Agent 总结。ID 无法取得时先查询会话元数据，不得编造。

```json
{
  "thread_id": "<实际会话 ID>",
  "message_id": "<可选：实际用户消息 ID>",
  "user_message": "确认",
  "scope": "policy",
  "decision_sha256": "<完整决定去掉 human 后的 canonical JSON SHA256>"
}
```

`decision_sha256` 使用 `static_comic.contracts.digest(human_review.payload(proposal))` 计算；它绑定整个决定，不是决定内部的 `payload_sha256` 或文件字节摘要。scope 必须与本次展示的范围和命令相同。

```powershell
# 由 Agent 在 Skill 根执行；两个输入都是单期目录内的相对路径。
.venv/Scripts/python.exe -m static_comic human-confirm --project <episode> --scope policy --input review/source-proposal.json --conversation review/source-confirmation-reply.json
```

入口返回 `review/human-confirmations/<hash>.json`，记录 `source=conversation` 及完整回复证据，本身不晋级图片或改变审批状态。Agent 随后执行下表对应命令；应用时重新校验当前资源，过期收据不能执行。

| scope | 建议格式 | 应用命令 |
|---|---|---|
| policy | imageDecision | images confirm-policy |
| plan | imageDecision | images confirm-plan |
| images | imageReview | images review |
| transitions | transitionDecision | transitions confirm |
| preview | deliveryDecision，stage=preview | approve |
| final | deliveryDecision，stage=final | approve |

生产消费者验证 HMAC-SHA256 签名、入口来源 `conversation` 或 `local_terminal`、scope 和完整决定负载。聊天来源还验证回复证据的 scope 和决定摘要。图片批次按签名负载中的精确 item 校验，绑定请求、候选、供应记录、几何和用户决定；批准后的图片复验还读取 record_sha256 指向的历史供应事件，校验摘要，并要求当前候选及完整来源记录与被签记录相同。可选许可备注如果已存在，也随原记录保持完整性，但其缺失或否定值不是拒绝本地合成的理由。转场绑定完整候选与精确边界；预览/正式质量分别绑定当前媒体和执行快照。主体安全及语义问题仍独立校验，签名不能覆盖这些失败。

批准可明确为 APPROVED、REJECTED 或原契约允许的 REVIEW_REQUIRED。policy/plan 契约是确认操作，用户可取消而不签发。对相同有效 policy/plan 或转场决定重复应用可保持相同结果；旧图片收据应用一次后供应记录摘要改变，重复提交按过期拒绝，已有批准不变。来源查询不签发收据、不延长有效性，也不改文件。

## 可选终端入口

仅当用户主动选择终端方式时，省略 `--conversation`，由用户在自己的交互式终端执行 `human-confirm`，核对展示的完整决定，再输入 `CONFIRM <摘要前12位>`。其他输入取消，重定向输入被拒绝。Agent 不模拟此终端操作；聊天确认使用独立的 conversation 来源，不能冒充 local_terminal。

## 能保证什么

密钥首次签发后由入口内部生成在当前 OS 账户的 `~/.static-comic-video/confirmation.key`，不在项目、输入 JSON 或 Git 中；Agent 无需自行读取、复制或显示密钥。记录包含带时区的签发时间、来源、scope、完整负载和签名；聊天来源另含真实回复和会话标识，终端来源记录 OS 账户名称。修改已签负载或回复会使签名校验失败。密钥丢失或更换后，旧签名不可验证，须重新确认。

CLI 不连接聊天平台，无法认证回复作者或判断原话是否表示同意；它信任 Agent 如实记录真实用户决定。签名证明记录签发后未变，不证明用户身份或 Agent 陈述属实。Agent 不能把此入口当作自动同意开关。拥有同一 OS 账户权限的程序可以调用签发入口或读取密钥，此流程不抵御同权限攻击。完整试听勾选仍是用户声明，签名不验证第三方许可的法律真实性。收据绑定内容而非目录名；复制相同对象到同一账户的其他目录不会凭路径变化使收据失效，内容或审批对象摘要改变则失效。

## 历史兼容与测试

已有有效 `local_terminal` 收据继续有效，无需改签。schema 保留读取旧 human 字段的能力，但无签名记录不能通过图片、来源、转场及媒体生产门禁，不自动补签。旧 SC-P7 用户验收保留为历史事实，原文件不改写；继续生产若缺少有效收据，展示当前对象后按聊天流程取得明确确认。

语音 reading/boundary 注释仍沿用 SC-P3 的历史元数据协议（`check_human_metadata`），它们不是这里的生产图片/转场/媒体批准，不能跳过完整试听。`--technical-fixture` 交付允许合成元数据，但输出始终 TEST_ONLY、production_accepted=false；生产图片和转场没有此旁路。

自动化测试只在临时目录、临时账户密钥下模拟聊天回复或终端输入，验证器不被替换；这些签名不能由真实账户密钥验证。共享 Python/Ajv 测试只检查字段形状，不能把 schema PASS 当作签名或人工批准有效。

过期、无签名或不可验证的旧 quality.json 会保留，但正式画质返回 REVIEW_REQUIRED、production_accepted=false；它不阻塞新媒体技术核验，也不阻塞用户重新确认。新决定应用时，旧预览/质量指针原字节归档至 review/delivery-history/<hash>.json，再通过受控发布更新。签名有效且绑定当前成片的 final 决定才能恢复质量 PASS。

同一候选的转场边界、同一 stage/binding 的媒体决定，精确重试保持幂等；不同决定必须比当前有效签名收据时间更新。较早 APPROVED 不能通过正常 API 重放覆盖较晚 REJECTED，需要用户重新确认。无效旧记录不作为时序权威；此规则仍不抵御同权限程序直接改磁盘指针或系统时钟。
