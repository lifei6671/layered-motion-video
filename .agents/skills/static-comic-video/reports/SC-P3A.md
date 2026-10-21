# SC-P3A 开发与验证记录

范围：阶段清单 SC-P3A-01～09；实现位于本 Skill。没有新增依赖、模型下载、外部图片调用、提交或推送。SC-P4 语义规划及 SC-P6 完整执行事务尚未实现。

## 实现与证据

| 任务 | 实现 | 验证 |
| --- | --- | --- |
| 01 渠道选择 | images policy / confirm-policy；待确认阻断，混合逐镜头映射 | pending、改源、混合政策测试 |
| 02 图片请求 | plan / confirm-plan；原文、画风、角色、构图、运镜、正式路径及 hash | 提示词完整性、变更失效测试 |
| 03 Agent 生图 | dispatch 返回确认请求；Agent 通过已连接授权工具执行，ingest 保存工具与原始记录 | 合成交接用例；当前本地生成器 UNAVAILABLE |
| 04 第三方获取 | 授权工具交接，URL/作者/站点/许可证据/工具记录及 hash | 合成第三方用例；未配置授权图库，真实获取 UNAVAILABLE |
| 05 人工提示词 | 每图独立中文提示词；WAITING_FOR_USER；正式路径不自动批准 | 提示词、现有文件仍需审图测试 |
| 06 候选检查 | PNG/JPEG/WebP 解码；原始留存、统一 PNG；几何、预览与逐图报告 | 解码、JPEG、主体、许可及报告测试 |
| 07 审核晋级 | 明确逐图/批次、完整检查、用户证据；只晋级已批准候选 | 失败批次不部分晋级、驳回重做、重导入失效测试 |
| 08 参考与成图 | usage_role、参考版本/hash/改编授权链；视觉批准和权利分开 | reference_only、禁止派生、未知权利阻断 |
| 09 混合来源 | 六镜头，三渠道各两张；独立记录和审批 | 合成示例、改源/驳回后相同字节使转场批准失效 |

执行流程与 JSON 字段见 [image-supply.md](../references/image-supply.md)。无新图库客户端；获取动作由 Skill 的 Agent 依据授权使用工具，模块负责交接与验证。当前未配置的真实服务没有被测试夹具冒充成功。

## 已执行验证

- Python：`.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v`，82 tests PASS，含 21 项 SC-P3A 行为测试及共用图片 schema corpus。[日志](sc-p3a/python-tests.txt)
- Node：`npm test`，contracts:check、TypeScript 编译及 50 tests PASS；包含 13 项新增图片 schema 有效/无效共享用例。[日志](sc-p3a/node-tests.txt)
- Skill：官方 quick_validate，`Skill is valid!`。
- CLI：images report / verify 成功；合成示例正式 compile 因技术 timing 明确拒绝，未生成 production public。[记录](sc-p3a/cli-smoke.json)
- 六镜头示例：生成请求、原始候选、逐图许可/工具证据、全部状态事件、驳回重做、明确批次收据及复核；没有真实生图或下载。[审图页面](sc-p3a/demo/review/images/index.html)
- 本机能力：限定端口 8188/7860/7861 没有监听，无已连接本地生图工具；未选授权图库。人工提示词与本地导入可用。[能力记录](sc-p3a/capabilities.json)

## 独立审查

采用 CHILD_AGENT / Tier 2 / Strict，只审本阶段文件。首次 checkpoint 找到一项 P1（审批版本未使旧转场失效）及一项 P2（整期缺图错误污染已批准单图报告），已在第 1 轮修复并加回归。最终完整目标和结论分别记录在 `sc-p3a/review-target.json`、`sc-p3a/independent-review.json`，不把 checkpoint 当最终批准。

## 生产边界

本次开发与测试不是生产素材验收。所有示例图片为标注 SYNTHETIC TEST ONLY 的几何图，TEST ONLY 收据仅测试本地协议；真实角色/画风效果、实际发布许可和用户审图均 NOT_RUN。真实一期需用户确认来源、工具成功取得素材并完成逐图审核后，才可进入 SC-P4。没有真实素材批准时不得根据本报告开始正式制作。

既有图片批准在当前生产编译中还必须具备 P3A 供应证据；旧审批缺供图证据会拒绝，不静默迁移为已审。图片变化、来源变更及驳回重批会使语义转场的 image_approval_hashes 过期，必须重新审语义。旧预览文件保留供查验，其存在不表示仍有效；每次渲染都需重新验证并编译。
