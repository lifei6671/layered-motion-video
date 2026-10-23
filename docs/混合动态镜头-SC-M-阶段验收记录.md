# 混合动态镜头 SC-M1～M3 基础能力：阶段验收记录

## 完成范围

- **Remotion 4.0.537**：只升级 `.agents/skills/static-comic-video/renderer/static-comic` 中的 `remotion`、`@remotion/bundler`、`@remotion/cli`、`@remotion/renderer`、`@remotion/transitions`，全部精确版本号一致；未调整 cover-studio 的独立运行时，也未更换原配音、FFmpeg 管线。
- **SC-M1 配方注册**：`renderer/static-comic/src/motion-card-registry.ts` + `talkcraft-recipes.tsx`（先前移植）+ `MotionCardTrack.tsx`。允许 `talkcraft-number-slab` / `talkcraft-ink-underline` / `talkcraft-chapter-card`，不执行计划里的任意 JSX、JavaScript 或 CSS。
- **SC-M2 全局动态镜头轨**：`ComicVideo.tsx` 支持可选 `motion_cards`，继续复用 `TransitionSeries` 和 `VisualEmphasisOverlay`。Python `motion_cards.py` 将 `input/motion_cards.json` 编译为原 30fps 绝对帧事件，限制每镜至多一张、滑动 60 秒最多两张，检查转场稳定窗口、内容来源和字号可读宽度，拒绝与关键词动画重叠。扩展缺省关闭。
- **SC-M3 规则候选初版**：`motion propose/import/inspect`；可靠声学字级证据 + 原文中数字/章节提示/概念定义才提出候选，`propose` 不替换选定计划；`import` 需明确选择，已有不同选定计划必须 `--replace`。未配置的真实视觉 Agent 返回 `UNAVAILABLE`，不得冒称具备跨画面物体识别能力。
- **审核、缓存和许可**：`motion_card_preview.py` 抽取实际渲染后的动态镜头入场/定格/退场关键帧并绑定试听批准；当前 `motion_cards.lock.json` 在 snapshot 阶段核对。保留现有图像、声学证据、资源批准、音效混音机制。
- **上游**：源自 video-talkcraft，PolyForm Noncommercial 1.0.0；Required Notice: Copyright (c) 2026 Vincent Wei (https://github.com/Vincentwei1021/video-talkcraft)。详细源码溯源及本地使用限制见 `references/motion-cards.md`。未加入第三方音效和商用限制不明的素材。

## 验收对象与命令

根目录以下相对路径均以 `.agents/skills/static-comic-video/` 为基准：

```powershell
# TypeScript 合约生成后，确认没有陈旧类型；测试包含既有回归和 SC-M2 新用例。
cd renderer/static-comic
npm test
npm run versions

# Python 固定原文/Unicode/转场边界/密度/无事件等 12 个新增测试。
cd ../..
.venv/Scripts/python.exe -m unittest discover -s tests -p test_motion_cards.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_emphasis_contracts.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_emphasis_integration.py -v
.venv/Scripts/python.exe -m unittest discover -s tests -p test_emphasis_incremental.py -v

# 新目录必须为空；TEST_ONLY 图形+合成音轨，不含真人审核。
.venv/Scripts/python.exe scripts/create_motion_fixture.py --output reports/sc-m/fixture-v1
.venv/Scripts/python.exe -m static_comic motion inspect --project reports/sc-m/fixture-v1 --technical-fixture
.venv/Scripts/python.exe -m static_comic preview --project reports/sc-m/fixture-v1 --technical-fixture
```

## 实际验证记录

| 检查 | 结果 | 说明 |
|---|---|---|
| Remotion 统一版本 | **PASS** | `npm run versions` 报 4.0.537；未出现版本不匹配 |
| TypeScript/Node 测试 | **PASS** | 96 项通过；包含 7 项 SC-M2 新增校验 |
| Python SC-M 新增测试 | **PASS** | 12 项通过；Unicode、事实数值、概念/章节建议、过期计划、事件冲突、安全白名单及可读宽度 |
| 原有 Python 合约回归 | **PASS_WITH_SKIP** | 18 项通过，1 项 Windows 链接权限跳过 |
| 原有 Python 集成回归 | **PASS** | 4 项通过 |
| 原有 Python 增量缓存回归 | **PASS** | 6 项通过，稳定源码下验证，耗时约 88 秒 |
| 60 秒技术夹具 | **PASS** | 1800 帧，2 段混合字卡；已完成实际浏览器视频与 48 kHz FFmpeg 试听封装，需查看 `reports/sc-m/fixture-v1/preview/technical/` |
| 混合镜头审核绑定 | **PASS** | 2 张卡、10 张事件帧、1 次批量解码；真实试听报告绑定动态镜头联系表；音频 2,880,000 采样 |
| 章节字卡浏览器定妆帧 | **PASS** | `reports/sc-m/chapter-render-smoke.png`，使用技术锁定画面、测试文字 |
| Git whitespace 检查 | **PASS** | `git -c core.whitespace=cr-at-eol diff --check` |
| 真实漫画+真实口播应用 | **NOT_RUN** | 尚未对用户正式一期素材进行审片 |
| 真人完整试听 / 资源生产批准 | **NOT_RUN** | 技术夹具不签发，也不伪造 |
| 真实 Agent 视觉模型选卡 | **UNAVAILABLE** | 尚未接入能确证已看图的视觉模型 |
| 连续长片跨题材风格验收 | **NOT_RUN** | 后续扩展配方前需实际样片 |

技术夹具与诊断数据放入已有忽略的 `reports/sc-m/`，不是正式成片。

## 后续优化方向

1. 增加可验证的视觉模型接入，依据漫画构图、人物主体、已嵌入文字与情绪判断是否允许动态镜头，允许零事件。
2. 将 video-shotcraft 的 `riso-print-hits`、`comic-panel-split`、`flash-cut` 和 video-talkcraft 的 `line-chart-story-draw` 接成新的受控配方；图表必须提供可审查数据。
3. 动态镜头的动作标记与现有 FFmpeg SFX 事件做显式映射，仍需资源批准与有声预览，不直接导入第三方音频。
4. 后续若需要可编辑工作台，应建立严格与生产锁一致的时间线协议，而不是整套替换现有工程。

**本次没有提交、推送、重置或清理工作区；用户已有的 `AGENTS.md`、音效文件及其他未提交改动全部保留。**
