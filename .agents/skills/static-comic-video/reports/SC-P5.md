# SC-P5 开发与验证记录

范围：SC-P5-01～05，代码和文档均在本 Skill。新增 delivery.py、media.py、明确的预览/质量决定契约及 CLI；沿用 P1～P4，不下载模型、不新建 TTS/图库客户端、不提交或推送。缓存与恢复仍留给 SC-P6。

## 实现对应

| 任务 | 实现 | 验证 |
| --- | --- | --- |
| 01 最小 CLI | init/status/studio/preview/inspect/approve/render-visual/mux/verify，复用 images/align/transitions/compile | init 不预选渠道；缺批准及旧摘要拒绝；实际 Studio 启动、构建与 HTTP 200 |
| 02 有声预览 | 本地 Remotion 960×540、30 fps、相同 T；视频流复制并编码完整母带；联系表和播放页 | 既有中文语音技术预览，553 帧、18.433 秒；逐帧视频一致和首尾音频内容通过 |
| 03 状态与收据 | 来源/计划/图片门禁，预览文件、输入、许可、审图/语义收据、时间线、源码与运行版本绑定 | 缺少试听确认、驳回、许可/母带/预览字节/转场意图/渲染版本变化均阻断 |
| 04 正式输出 | 批准后同一 props/时间线的 1080p 无声视觉，FFmpeg copy 视频 + AAC 192k/48kHz | 真实 Remotion 生产入口在合成审批项目中完成全流程；隔离 technical 目录留存回归成片 |
| 05 媒体验证 | 精确流布局、帧数、PTS、完整解码画面 hash、AAC 有效时长/填充及逐秒母带对照 | 11.981 秒/575088 采样 → 360 帧，尾差 912 采样；截短音频、改画面、错误流布局拒绝 |

流程、文件位置和真实用户决定格式见 [delivery.md](../references/delivery.md)。正式画质采用 stage=final 单独记录，不把预览批准当正式画质批准。只有技术、语义、完整试听、正式画质四项均 PASS 才返回 production_accepted=true。

## 已执行证据

- Python：`.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v`，119 tests PASS。[日志](sc-p5/python-tests.txt)。新增行为验证包含实际低清/1080p Remotion 渲染和 FFmpeg 封装，没有用 mock 渲染冒充集成成功。
- Node：`npm test`，contracts:check、TypeScript 编译和 69 tests PASS，含六项共享批准契约用例。[日志](sc-p5/node-tests.txt)
- Skill：官方 quick_validate PASS。[记录](sc-p5/skill-validation.txt)
- 媒体 checkpoint：五项实际 FFmpeg 回归 PASS；独立审查无 P0/P1/P2。[记录](sc-p5/checkpoint-review.json)
- 中文有声预览：复用 SC-P3 已存完整音频和对齐结果，不调用 VoiceStudio、不重新推理、不新增语音生成。[命令和来源](sc-p5/speech-demo/demo-result.json)、[有声预览](sc-p5/speech-demo/preview/technical/preview.mp4)、[联系表](sc-p5/speech-demo/preview/technical/contact_sheet.jpg)、[技术报告](sc-p5/speech-demo/reports/technical/preview.json)
- 11.981 秒完整技术流程：两路测试音、360 帧、隔离测试批准，正式尺寸输出仍不代表用户验收。[CLI 记录](sc-p5/clock-demo/cli-commands.json)、[render.json](sc-p5/clock-demo/reports/technical/render.json)、[validation.json](sc-p5/clock-demo/reports/technical/validation.json)
- Studio：本地服务完成构建、HTTP 200；测试后已关闭本次启动的进程树。[记录](sc-p5/studio-smoke.json)
- 未批准中文预览执行 render-visual：预期退出 2，明确缺少 review/technical/approval.json，未生成正式视频。[失败信息](sc-p5/unapproved-render.txt)

首次共享批准用例出现可变 human 对象复用导致有效用例被反例污染，已改为独立拷贝；没有降低 Schema 的 human 限制。

## 独立交付审查

CHILD_AGENT / Tier 2 / Strict / READ_ONLY。媒体分区 checkpoint 已通过；完整最终目标及审查结论分别记录在 sc-p5/review-target.json 和 sc-p5/independent-review.json，最终新鲜度见 sc-p5/final-freshness.json。只有最终完整覆盖才是本次交付审查通过，不用 checkpoint 替代。

## 人工验收与限制

提供的是中文技术有声预览，画面为已有几何测试图；源测试图本身含技术标签，引擎没有叠加字幕、编号或其他文字。中文配音为前期已生成并实测的测试语音。本次没有真实一期已批准漫画，因此真实原画语义、用户完整试听、正式画质均 NOT_RUN；中文预览保持未批准，没有为用户生成批准收据。

完整输出回归中的收据明确为 SYNTHETIC TEST ONLY，technical 目录和状态不能作为生产批准。真实一期必须先完成图片和转场审核，再对具体有声预览明确批准。尚未实现 SC-P6 的多进程互斥、缓存和整批原子替换；执行失败后不得凭文件存在认定成功。旧期语义计划绑定契约摘要，契约变化后须重新规划确认，不静默迁移为已审。
