# 本地人工确认入口与信任边界

Agent 可以准备建议、展示图片和填写待确认决定，但不能自行运行交互入口替用户批准。`actor_role=human`、时间和 evidence 字符串只是声明，生产门禁不再接受这些字段作为独立确认依据。

用户在自己的交互式终端执行以下命令，先查看对应报告或实际视频，再核对终端展示的完整决定及对象摘要，输入屏幕要求的 `CONFIRM <摘要前12位>`。其他输入取消；管道、重定向和非交互 stdin/stdout 被拒绝。没有自动同意选项。

```powershell
# 在 Skill 根执行；input 为单期目录中的建议 JSON。
.venv/Scripts/python.exe -m static_comic human-confirm --project <episode> --scope images --input review/image-proposal.json
```

入口返回 `review/human-confirmations/<hash>.json`，不会直接晋级图片或改变审批状态。Agent 可将返回路径传给原命令；原命令会重新校验当前资源，过期收据不能执行。

| scope | 建议格式 | 应用命令 |
|---|---|---|
| policy | imageDecision | images confirm-policy |
| plan | imageDecision | images confirm-plan |
| images | imageReview | images review |
| transitions | transitionDecision | transitions confirm |
| preview | deliveryDecision，stage=preview | approve |
| final | deliveryDecision，stage=final | approve |

生产消费者验证 HMAC-SHA256 签名、入口来源 `local_terminal`、scope 和完整决定负载。图片批次按签名负载中的精确 item 校验，绑定请求、候选、供应记录、几何和全部用户勾选项；批准后的图片复验还读取 record_sha256 指向的历史供应事件，校验事件摘要，并要求当前候选及其完整来源/许可记录与被签原记录相同，不能靠重算公开摘要替换来源。转场绑定完整候选与精确边界；预览/正式质量分别绑定当前媒体和执行快照。来源许可、图像主体安全及语义问题仍独立校验，签名不能覆盖这些失败。

批准可明确为 APPROVED、REJECTED 或原契约允许的 REVIEW_REQUIRED。policy/plan 契约是确认操作，用户可取消而不签发。对相同有效 policy/plan 或转场决定重复应用可保持相同结果；旧图片收据应用一次后供应记录摘要改变，重复提交按过期拒绝，已有批准不变。来源查询不签发收据、不延长有效性，也不改文件。

## 能保证什么

密钥首次交互确认后生成在当前 OS 账户的 `~/.static-comic-video/confirmation.key`，不在项目、输入 JSON 或 Git 中。普通调用者提交任意 evidence 或改签名负载无法通过检查。收据包含当前 OS 账户名称、带时区的确认时间、来源、scope、完整负载和签名。只有摘要和签名进入记录，密钥不进入日志。密钥丢失或更换后，旧签名不可验证，须重新确认。

这不是不可伪造的人类身份认证。拥有同一 OS 账户权限的恶意程序可以读取密钥、调用 Python 内部函数、控制终端或改代码。交互操作也不能证明用户确实看图或听完整视频；完整试听勾选是用户声明。此入口提供本地受控流程、决定完整性和可追溯来源，不抵御同权限攻击，不验证第三方许可的法律真实性。收据绑定内容而非目录名；复制相同对象到同一账户的其他目录不会凭路径变化使收据失效，内容或审批对象摘要改变则失效。

## 历史兼容与测试

schema 保留读取旧 human 字段的能力，但旧无签名记录不能再通过新版本的图片、来源、转场及媒体生产门禁。不自动补签，不将聊天记录转换为本地终端确认。旧 SC-P7 用户验收是旧版本的真实历史事实，原文件和收据不改写；使用新版本继续生产须通过新入口重新确认。

语音 reading/boundary 注释仍沿用 SC-P3 的历史元数据协议（`check_human_metadata`），它们不是这里的生产图片/转场/媒体批准，不能跳过完整试听。`--technical-fixture` 交付允许合成元数据，但输出始终 TEST_ONLY、production_accepted=false；生产图片和转场没有此旁路。

自动化测试只在临时目录、临时账户密钥下模拟终端输入，验证器不被替换；这些签名不能由真实账户密钥验证。共享 Python/Ajv 测试只检查字段形状，不能把 schema PASS 当作签名或人工批准有效。

过期、无签名或不可验证的旧 quality.json 会保留，但正式画质返回 REVIEW_REQUIRED、production_accepted=false；它不阻塞新媒体技术核验，也不阻塞用户重新确认。新决定应用时，旧预览/质量指针原字节归档至 review/delivery-history/<hash>.json，再通过受控发布更新。签名有效且绑定当前成片的 final 决定才能恢复质量 PASS。

同一候选的转场边界、同一 stage/binding 的媒体决定，精确重试保持幂等；不同决定必须比当前有效签名收据时间更新。较早 APPROVED 不能通过正常 API 重放覆盖较晚 REJECTED，需要用户重新确认。无效旧记录不作为时序权威；此规则仍不抵御同权限程序直接改磁盘指针或系统时钟。
