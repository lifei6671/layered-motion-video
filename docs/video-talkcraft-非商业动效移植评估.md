# video-talkcraft / video-shotcraft 非商业动效移植：第一批

## 来源与许可

- video-talkcraft: https://github.com/Vincentwei1021/video-talkcraft
- video-talkcraft PolyForm Noncommercial 1.0.0: https://github.com/Vincentwei1021/video-talkcraft/blob/main/LICENSE
- Required Notice: Copyright (c) 2026 Vincent Wei (https://github.com/Vincentwei1021/video-talkcraft)
- video-shotcraft: https://github.com/Vincentwei1021/video-shotcraft
- video-shotcraft 代码 Apache-2.0: https://github.com/Vincentwei1021/video-shotcraft/blob/main/LICENSE
- **用途限制**：目前只按用户明确声明的非商业个人项目使用；源码若公开分发，务必附上 PolyForm Noncommercial 许可证 URL 与 Required Notice，不得默认再授权商用。第三方音效、图片和字体分别核对许可证，不因主项目许可证而获得其授权。

## 源文件与本地适配状态

| 上游文件 | 当前本地文件 | 状态 |
|---|---|---|
| video-talkcraft/template/cards/number-slab-pop.tsx | renderer/static-comic/src/talkcraft-recipes.tsx::TalkcraftNumberSlab | 首批源码适配，使用传入内容，不含真人视频和演示文字 |
| video-talkcraft/template/cards/ink-underline.tsx | renderer/static-comic/src/talkcraft-recipes.tsx::TalkcraftInkUnderline | 首批曲线/变宽缎带算法适配，不含主持人或演示素材 |
| video-talkcraft/template/cards/chapter-title-card.tsx | renderer/static-comic/src/MotionCardTrack.tsx | 章节卡时序独立适配，已实际浏览器抽帧验证 |
| video-talkcraft/references/taxonomy.md | 本文设计参考 | 已评估语义卡片分类，SC-M3 仅启用保守规则候选 |
| video-talkcraft/references/layout.md | 本文设计参考 | 已评估，未来映射到已有 emphasis_layout.py |
| video-shotcraft/assets/lib/DigitRoll.tsx、FlashCut.tsx | 暂未移植 | 待统一动画配方协议 |

**当前状态：三类受控配方已接入** `motion-card-registry.ts` / `MotionCardTrack.tsx`，由可选 `input/motion_cards.json` 编译为 `props.motion_cards`。无选定计划时旧 Props 和渲染行为不变；SC-M2 已完成 60 秒、1800 帧 TEST_ONLY 有声合成与实际抽帧。没有重写 WhisperX 或 FFmpeg，没有引入上游音频文件、视觉模型或主持人占位素材。静态漫画渲染器 Remotion 已从 `4.0.515` 精确升级到 `4.0.537`。**真正的 Agent 画面语义选卡、真实漫画效果与用户审片仍未完成**。

## 已完成及待继续的 SC-M1 / SC-M2 / SC-M3 验收

1. **SC-M1 已完成基础注册**：三类已支持配方固定在 `motion-card-registry.ts`；可选事件契约来自 Python JSON Schema 和生成的 TypeScript 类型，不允许注入任意 React/CSS。更精细的逐资源 font hash 绑定仍属后续增强。
2. **SC-M2 已完成基础接线**：`MotionCardTrack` 依据全局 `start_frame/end_frame` 覆盖漫画稳定窗口，保留总时长；不能侵入转场或现有关键词事件。编译计划、技术夹具、真实关键帧报告与有声预览摘要已经接入。
3. **SC-M3 已有保守规则候选**：原文字级可靠对齐的数字、明确章节词与概念定义可以提出受控候选，需由 `motion import` 显式选中。下一步仍需接入真实视觉 Agent、构图适配、多图关系与完整语义分类，允许任何阶段零事件。
4. 无真实可验证数据不得生成折线/比较图；真人素材缺失时不伪造人物，移植时清除上游演示数据。
5. 音效只产生对应 `sfxEvent` 候选，继续走素材授权与签署、48 kHz 采样级定位、FFmpeg 单独混音及完整有声预览。
6. 验收真实漫画与轻/重动画各一镜；视觉双帧/进退关键帧对比、中文字体校验、渲染缓存命中、关闭扩展兼容、超过图文预算 fail-closed、人工听音。

## 第一批选卡说明

- 优先：`number-slab-pop`（结果数字、单点强调），`ink-underline`（漫画纸墨关键词标注）。
- 已完成：`chapter-title-card` 章节字卡基础适配。下一批重点为 `line-chart-story-draw`、`split-compare-slider`、`whip-pan-transition`。图表必须有数据证据，甩镜必须验证原画裁切与转场占用。
- 不优先：数字主持人、假聊天界面、终端操作演示、真人出镜互动。漫画仍是不可拆分静态图片。
