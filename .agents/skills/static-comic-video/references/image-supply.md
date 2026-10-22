# SC-P3A 图片供应与用户审图

Agent 负责调用工具、整理输入、保存文件、生成报告和执行命令；用户只做必要的内容选择和效果确认。以下 JSON、路径、摘要与命令都由 Agent 处理。Python 检查素材与审图记录的一致性，不审核商业授权。没有内置图库账号、爬虫或生图服务客户端，不自动换源。

## 每期执行顺序

1. 确定本期使用 `agent_generate`（用户已选且当前可用的本地或远程图片生成工具）、`third_party_retrieve`（用户指定图库/站点）、`manual_generate`（提示词交给用户生成）还是 `mixed`；已有明确选择直接采用，只询问尚缺的渠道信息。明确工具/站点，确认人及回复证据由 Agent 记录。不要询问是否盈利、营利、变现或商用，不要求用户声明发布平台或商业计划。未主动说明发布用途时继续制作，`publication_scope` 填“未指定；当前仅制作本地视频”。`images policy` 只读查询，空项目返回 SOURCE_POLICY_PENDING，不创建文件；`init` 负责初始文件。有效确认返回 APPROVED 及当前模式、允许渠道、完整逐镜头映射，不重复询问。配置改变或确认无效返回 REVIEW_REQUIRED。已观察到的渠道失败单列 UNAVAILABLE，未探测的渠道为 NOT_PROBED，不把批准等同工具可用。
2. 根据回复填写 `input/image_source_policy.json`。混合须列全逐镜头 `shots` 映射，运行 `images policy` 得到待确认的 `payload_sha256`，展示本次来源和覆盖镜头。用户在聊天中明确确认后，Agent 按 [确认流程](human-confirmation.md) 记录真实回复、签发 `imageDecision` 并运行 `confirm-policy`；已有明确覆盖当前对象的回复不重复询问。hash 是 canonical JSON SHA256，不是 JSON 文件字节 hash。换工具/站点/模式必须重新确认，supersedes 可记录前一政策摘要。
3. 使用已确认分镜和原文填写 imageBrief，运行 `plan`，生成 `work/planning/image_requests.json` 和逐镜头完整中文 `image_prompts.md`。展示画风、角色、视觉任务、构图和渠道，请用户确认，再用 `confirm-plan` 记录 imageDecision。重新生成计划清空旧确认。采集阶段绑定原文、视觉分镜、原始运镜计划和 render 配置；取得图片后运镜可进入独立几何重审，P3 时间和 P4 转场可以独立调整。
4. 每镜头先运行 `dispatch`。策略/计划未确认时命令失败，Agent 也不得调用获取工具。人工分支进入 WAITING_FOR_USER；正式路径已有文件也不算批准。其他分支的 PLANNED 只是准备交给工具，不能当成已执行成功。
5. 获取候选并保存下述证据后 `ingest`。原始字节存 `work/images/originals/<hash>.bin`；PNG/JPEG/WebP 单帧图转换为 PNG 后存 `work/images/candidates/<hash>.png`。分别记录原始与候选 hash，不静默重绘或去水印。
6. `report` 生成 `review/images/index.html`，Agent 主动打开给用户查看。逐图展示口播、图片、运镜、来源和分辨率/裁切/主体检查；已有许可仅作备注，不要求用户完成版权问卷。Agent 先实际看图检查角色、画风及叙事，不能以元数据代替视觉判断。照片或不统一画风应建议改成参考或换源，不自动入镜。
7. 收到明确逐图或明确批次用户意见后，提交 imageReview 的 APPROVED / REJECTED / REVIEW_REQUIRED（要求重做）。每项绑定当前 candidate_sha256、record_sha256 和报告中的 geometry_sha256；不能隐式扩大批准范围。`review` 整批预检，只晋级批准图片到正式路径，更新 manifest / approvals，并保留事件。驳回保留文件但撤销活动批准。
8. `images verify` 通过才可进入 SC-P4。正式 validate/compile 也强制执行该门禁。每次渲染先重新验证、编译；旧 props/public/预览存在不代表当前批准，不直接继续使用旧产物。完整执行快照和事务属于 SC-P6。

在 Skill 根目录执行，--project 指单期目录，--input 是单期目录内相对路径：

```powershell
.venv/Scripts/python.exe -m static_comic images policy --project <episode>
.venv/Scripts/python.exe -m static_comic images confirm-policy --project <episode> --input review/source-decision.json
.venv/Scripts/python.exe -m static_comic images plan --project <episode> --input input/image-brief.json
.venv/Scripts/python.exe -m static_comic images confirm-plan --project <episode> --input review/plan-decision.json
.venv/Scripts/python.exe -m static_comic images dispatch --project <episode> --shot SHOT-001
.venv/Scripts/python.exe -m static_comic images ingest --project <episode> --input work/images/submission-001.json
.venv/Scripts/python.exe -m static_comic images report --project <episode>
.venv/Scripts/python.exe -m static_comic images review --project <episode> --input review/decision-001.json
.venv/Scripts/python.exe -m static_comic images verify --project <episode>
```

命令成功退出 0，但 JSON 状态可能仍是 WAITING_FOR_USER / REVIEW_REQUIRED / UNAVAILABLE，不等于批准。输入/门禁失败退出 2，stderr JSON 给出原因。`unavailable --shot ... --reason ...` 记录实际失败原因，不调用备用服务。单期串行执行，沿用 P1 受控路径和输出预检。

## 三个获取分支

**Agent 生图**：发现本会话实际连接的本地或远程工具、版本和可用性，核对用户已选的 channel，只调用该工具。使用 requests 完整中文 prompt，保存真实参数、原始输出、工具名/版本及参考图版本、SHA256。Agent 保存返回图片、命名并 ingest，不让用户下载再上传。工具未报告版本时记录 unreported。不可用则先诊断，确实无法执行才记录 UNAVAILABLE 并说明缺口；切换渠道再确认。用户已选远程 image_gen 时直接沿用，不额外要求本地生成器。

**第三方**：Agent 用已可用的工具/API/浏览器检索和取得图片，记录实际源 URL、站点、检索词、时间、工具及下载方法；作者未提供时如实记录 unreported，不要求用户补查。已有许可信息可附存，缺少商业/发布授权不阻塞本地制作，不索要授权证明。`reference_only` 表示未选为成图，不能直接晋级；不以此标签充当授权检查。登录、付费等实际工具访问限制由平台处理，不绕过；仅在 Agent 无法完成必要访问时请用户协助。

**人工**：仅在用户主动选择此渠道时，Agent 交付逐镜头完整提示词，用户提供生成图片即可；不要要求用户创建目录、按特定名字保存、算哈希、填表或执行导入。Agent 根据镜头对应关系自行复制、命名、转换 PNG、登记可取得的生成记录并 ingest/report/review；对应不明确时只询问镜头映射。缺少工具版本或许可资料如实记录未知或省略，不要求用户另找证明。不要覆盖用户原图。直接放正式路径也由 Agent 完成登记审图。

## 契约与收据

权威字段在 schemas/contracts.json 的 imageBrief / imageDecision / imageRequests / imageSubmission / imageReview / imageSupply。Python/Ajv 读取同一 corpus。

imageBrief 包含 style_version、style、characters、objects、lighting、exclusions、publication_scope；shots 每镜头有 shot_id、visual_task、picture_type、composition。使用 templates/image-brief.example.json 起草，必须覆盖本期全部镜头。`publication_scope` 是记录字段，不是对用户的必答问题；未指定时保留模板默认值。仅记录用户主动提供的用途，不为填写字段追问盈利或商用，也不把“未指定”推定为商业授权。

imageDecision 为 `{payload_sha256, human}`；生产 human 必须带确认入口签发的 confirmation，默认来源为 `conversation`，用户主动选择终端时为 `local_terminal`。验证签名、scope 和完整决定负载，详见 [人工确认信任边界](human-confirmation.md)。只有真实用户明确回复才能由 Agent 记录；自填身份和无签名 evidence 字符串不能批准，TEST ONLY 收据不能用于真实项目。

下面命令由 Agent 执行，决定文件均指 human-confirm 返回的签名文件，不是 Agent 起草的建议 JSON；用户只需在聊天中确认相应对象。policy 的待确认摘要针对 status=APPROVED 且去掉 confirmation 的负载计算；查询不改写当前状态。

imageSubmission 字段：

- shot_id、request_sha256（完整已确认 requests 对象摘要）、source_mode、channel、file（单期相对路径）、usage_role（final_artwork 或 reference_only）。
- tool、tool_version、prompt、query、author、source_uri、site、accessed_at、download_method。生图/人工 prompt 必须与确认提示词逐字一致；图库必须有 HTTP(S) 来源、站点、作者、检索词。工具未报告版本可如实填写 unreported 并在输出证据说明，不猜测版本。
- license 是可选备注，字段 id、evidence、usage_scope、attribution、publication_allowed 也均可省略；已有内容据实保留，不检查 commercial/publication 是否允许，不伪填 true。
- request_record、output_record 是 `{path, sha256}`，由 Agent 保存实际请求和输出记录；license_evidence 是可选的同格式附件。存在附件才校验文件和 hash，未提供许可附件不阻塞导入、批准和导出。
- references 每项记录 source_uri、sha256、version，保留实际原图到成图的来源链；license_evidence、derivation_allowed 可选，已有否定值原样保留，不作为本地合成门禁。来源或所选成图改变仍按内容重新审查。

imageReview 为 `{request_sha256, human, items}`。每 item 含 shot_id、candidate_sha256、record_sha256、geometry_sha256、decision、reason、checks。本地放行只检查 comic_style、character_identity、narrative、composition、motion_safe、resolution_accepted；publication_rights、attribution_ready 可省略，旧 false 值不阻塞。Agent 先做技术与视觉检查，再展示具体结果与已知缺陷，用户可以一次确认已展示的整批效果，Agent 据此填写字段，不逐项提问。分辨率不足应展示实际效果并说明，不要求用户理解 upscale_risk 等内部字段；无主体框由 Agent 标注，裁切由 Agent 调整方案后再展示，不能要求用户算坐标。

取得图片后可以在 storyboard 补标或修改实测 subject_bbox，或按用户意见调整 motion。采集校验继续使用 requests 中冻结的原计划框及原 motion，原始 prompt、请求摘要与确认保持不变；不声称旧图片按新参数生成。当前实测框与当前 motion 用于几何检查。报告的 geometry_sha256 绑定当前实测框、完整 motion 及原请求，提交审图和生产复验均核对它。改框或运镜后必须重新展示并审图，即使新旧构图都安全；原采集确认不能代替新版运镜批准。cover_anchor、叙事和来源改变仍需重新规划。为读取历史审图记录，schema 允许缺少此字段，但此类旧决定不能提交或作为当前生产批准。

批准绑定当前 supply 记录摘要。替图、同字节重新导入、来源/许可变化、驳回/重做使旧批准失效。SC-P4 的非空转场还须填写相邻当前图片收据的 image_approval_hashes，与 image_hashes 同时匹配才可编译。重新批准后实际重审语义，再更新字段；导入器不自动替转场盖章。

## 开发证据边界

create_image_supply_demo.py 只在空目录创建六镜头合成示例，三渠道各两张。所有图是几何测试图，所有收据 synthetic，第三方 URL 为 example.invalid，不访问网络。保留技术 timing，禁止正式编译。示例只说明状态及审核协议，不能宣称真实图库下载、生图效果或用户审图通过。

## 图片批次发布

review 先检查全部候选、几何、来源记录一致性、决定字段和输出路径，再经 cache.publish 将正式图片、内容寻址审核事件、供应状态、清单及审批写入本期目录；这里的发布是本地文件写入，不是对外发布。临时文件校验后逐文件原子替换；可捕获异常回滚本批，其他镜头的合法批准保持不变。若回滚失败，Agent 保留 .bak 并按已验证的原字节恢复，再重新 report/review；无法确定恢复目标时说明具体冲突，不让用户盲跑命令。强杀或断电后的混合代次由 hash 复验阻断。旧供图及审核事件保留，不自动沿用被拒绝或旧候选批准。
