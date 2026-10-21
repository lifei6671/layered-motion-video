# SC-P3A 图片供应与用户审图

本 Skill 的 Agent 负责询问、调用已连接工具和展示图片；Python 负责请求、证据、候选、人工收据与生产门禁。没有内置图库账号、爬虫或生图服务客户端，不安装新服务，不自动换源。

## 每期执行顺序

1. 先问本期使用 `agent_generate`（已连接且授权的本地图片生成工具）、`third_party_retrieve`（用户指定图库/站点）、`manual_generate`（提示词交给用户生成）还是 `mixed`。明确工具/站点、发布用途、确认人及证据。`images policy` 只读查询，空项目返回 SOURCE_POLICY_PENDING，不创建文件；`init` 负责初始文件。有效确认返回 APPROVED 及当前模式、允许渠道、完整逐镜头映射，不重复询问。配置改变或确认无效返回 REVIEW_REQUIRED。已观察到的渠道失败单列 UNAVAILABLE，未探测的渠道为 NOT_PROBED，不把批准等同工具可用。
2. 根据回复填写 `input/image_source_policy.json`。混合须列全逐镜头 `shots` 映射，展示用户确认。运行 `images policy` 得到待确认的 `payload_sha256`，把真实回复整理为建议 `imageDecision`，由用户通过 [本地确认入口](human-confirmation.md) 签发，再运行 `confirm-policy`。hash 是 canonical JSON SHA256，不是 JSON 文件字节 hash。换工具/站点/模式必须重新确认，supersedes 可记录前一政策摘要。
3. 使用已确认分镜和原文填写 imageBrief，运行 `plan`，生成 `work/planning/image_requests.json` 和逐镜头完整中文 `image_prompts.md`。展示画风、角色、视觉任务、构图和渠道，请用户确认，再用 `confirm-plan` 记录 imageDecision。重新生成计划清空旧确认。采集阶段绑定原文、视觉分镜、原始运镜计划和 render 配置；取得图片后运镜可进入独立几何重审，P3 时间和 P4 转场可以独立调整。
4. 每镜头先运行 `dispatch`。策略/计划未确认时命令失败，Agent 也不得调用获取工具。人工分支进入 WAITING_FOR_USER；正式路径已有文件也不算批准。其他分支的 PLANNED 只是准备交给工具，不能当成已执行成功。
5. 获取候选并保存下述证据后 `ingest`。原始字节存 `work/images/originals/<hash>.bin`；PNG/JPEG/WebP 单帧图转换为 PNG 后存 `work/images/candidates/<hash>.png`。分别记录原始与候选 hash，不静默重绘或去水印。
6. `report` 生成 `review/images/index.html`。逐图展示口播、缩略图、运镜、来源、用途、许可、目标发布范围、分辨率/裁切/主体检查。Agent 必须实际看图检查角色、画风及叙事，不能以元数据代替视觉判断。照片或不统一画风应建议改成参考或换源，不自动入镜。
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

**Agent 生图**：发现本会话实际连接的本地工具、版本和可用性，核对确认的 channel，只调用该工具。使用 requests 完整中文 prompt，保存真实参数、原始输出记录、工具名/版本及参考图版本、SHA256、授权证据。返回文件放本期目录再 ingest。不可用则记录 UNAVAILABLE 并告知用户，切换先重新确认。远程 image_gen 可见不证明已连接本地生成器；用户若明确选远程工具，应作为新渠道确认。

**第三方**：只用已授权 API、许可检索接口或站点允许的下载方式。记录检索词、实际图像源 URL、站点、作者、带时区访问时间、工具/版本、下载方法、许可证文本/页面证据、发布范围和署名。Agent 核对原始来源及条款，不绕登录/反爬/付费，不去水印，不把搜索可见等同可发布。reference_only 可以保存但不能晋级成图；未知权利可以登记候选但不得批准。

**人工**：按镜头交付 image_prompts.md 的独立完整中文提示词，包括主题、原文、构图、画风、人物、灯光、16:9、运镜留白及排除项。建议 2304×1296，严格按提示词给出的 assets/images/shot_XXXX.png 命名。交回后登记实际工具/版本、完整 prompt、输出与权利证据，再 ingest/report/review。直接放正式路径也须走该流程。

## 契约与收据

权威字段在 schemas/contracts.json 的 imageBrief / imageDecision / imageRequests / imageSubmission / imageReview / imageSupply。Python/Ajv 读取同一 corpus。

imageBrief 包含 style_version、style、characters、objects、lighting、exclusions、publication_scope；shots 每镜头有 shot_id、visual_task、picture_type、composition。使用 templates/image-brief.example.json 起草，必须覆盖本期全部镜头。

imageDecision 为 `{payload_sha256, human}`；生产 human 必须带本地交互入口签发的 confirmation，验证签名、scope 和完整决定负载，详见 [人工确认信任边界](human-confirmation.md)。自填身份和 evidence 字符串不能批准；TEST ONLY 收据不能用于真实项目。

下面命令中的决定文件均指 human-confirm 返回的签名文件，不是 Agent 起草的建议 JSON。policy 的待确认摘要针对 status=APPROVED 且去掉 confirmation 的负载计算；查询不改写当前状态。

imageSubmission 字段：

- shot_id、request_sha256（完整已确认 requests 对象摘要）、source_mode、channel、file（单期相对路径）、usage_role（final_artwork 或 reference_only）。
- tool、tool_version、prompt、query、author、source_uri、site、accessed_at、download_method。生图/人工 prompt 必须与确认提示词逐字一致；图库必须有 HTTP(S) 来源、站点、作者、检索词。工具未报告版本可如实填写 unreported 并在输出证据说明，不猜测版本。
- license 包含 id、evidence、usage_scope、attribution、publication_allowed。视觉接受与发布权利独立，不能默认商业可用。
- license_evidence、request_record、output_record 都是 `{path, sha256}`，指本期保存的真实证据文件；导入、批准、生产验证重读 hash。
- references 每项包含 source_uri、sha256、version、license_evidence、derivation_allowed。派生图必须记录原图到成图的链、允许改编的证据；渠道改变先确认，再重新审成图。不可只改 reference_only 标签充当授权。

imageReview 为 `{request_sha256, human, items}`。每 item 含 shot_id、candidate_sha256、record_sha256、geometry_sha256、decision、reason、checks。checks 的 comic_style、character_identity、narrative、composition、motion_safe、resolution_accepted、publication_rights、attribution_ready 均须用户明确接受。分辨率不足报告 upscale_risk，须明确接受，插值不算高清；无主体框或主体裁切禁止批准。

取得图片后可以在 storyboard 补标或修改实测 subject_bbox，或按用户意见调整 motion。采集校验继续使用 requests 中冻结的原计划框及原 motion，原始 prompt、请求摘要与确认保持不变；不声称旧图片按新参数生成。当前实测框与当前 motion 用于几何检查。报告的 geometry_sha256 绑定当前实测框、完整 motion 及原请求，提交审图和生产复验均核对它。改框或运镜后必须重新展示并审图，即使新旧构图都安全；原采集确认不能代替新版运镜批准。cover_anchor、叙事和来源改变仍需重新规划。为读取历史审图记录，schema 允许缺少此字段，但此类旧决定不能提交或作为当前生产批准。

批准绑定当前 supply 记录摘要。替图、同字节重新导入、来源/许可变化、驳回/重做使旧批准失效。SC-P4 的非空转场还须填写相邻当前图片收据的 image_approval_hashes，与 image_hashes 同时匹配才可编译。重新批准后实际重审语义，再更新字段；导入器不自动替转场盖章。

## 开发证据边界

create_image_supply_demo.py 只在空目录创建六镜头合成示例，三渠道各两张。所有图是几何测试图，所有收据 synthetic，第三方 URL 为 example.invalid，不访问网络。保留技术 timing，禁止正式编译。示例只说明状态及审核协议，不能宣称真实图库下载、生图效果或用户审图通过。

## 图片批次发布

review 先检查全部候选、几何、许可、决定字段和输出路径，再经 cache.publish 将正式图片、内容寻址审核事件、供应状态、清单及审批最后发布。临时文件校验后逐文件原子替换；可捕获异常回滚本批，其他镜头的合法批准保持不变。若回滚本身失败，保留 .bak 并报告恢复路径；先恢复原字节再重新 report/review。强杀或断电不是跨文件原子事务，混合代次由图像/清单/供应/审批 hash 复验阻断。旧供图及审核事件保留，可重新导入候选并再审，不自动沿用被拒绝或旧候选批准。
