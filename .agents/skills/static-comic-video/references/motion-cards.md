# 混合动态镜头（SC-M1 / SC-M2 / SC-M3 初版）

在单张、不可拆分的静态漫画上，允许**零个或少量全屏动态信息卡**。动态镜头不是追加视频时长，而是以 Remotion `Sequence` 覆盖被选中的原漫画稳定帧区间；旁白声学对齐、镜头时长、转场重叠、FFmpeg 混音都保持原有时间轴。

## 上游来源与非商业许可

本地 `renderer/static-comic/src/talkcraft-recipes.tsx` 改编了 **video-talkcraft** 的 `number-slab-pop` 和 `ink-underline`，`MotionCardTrack.tsx` 还实现了基于其章节字卡时序的独立实现。

- 上游仓库：https://github.com/Vincentwei1021/video-talkcraft
- 原始路径：`template/cards/number-slab-pop.tsx`、`template/cards/ink-underline.tsx`、`template/cards/chapter-title-card.tsx`
- **Required Notice: Copyright (c) 2026 Vincent Wei (https://github.com/Vincentwei1021/video-talkcraft)**
- **PolyForm Noncommercial License 1.0.0**：https://github.com/Vincentwei1021/video-talkcraft/blob/main/LICENSE
- 目前仅基于用户明确说明的非商业个人使用场景。若分享或分发含改编代码的项目，必须保留上游 Required Notice 和许可证说明。将来转向商业用途，需要另行取得合适的授权。
- 不复制上游真实/演示人像、音乐、音效、品牌或配图。静态漫画仍沿用本项目独立图片审核。

## 作用域与执行链

```
input/script.txt + input/storyboard.json + verified WhisperX alignment
     ↓ 规则候选 / Agent 人工观察后导入
work/motion/proposals.json（非生产）
     ↓ 用户/Agent 选择并显式执行 motion import
input/motion_cards.json（唯一选定计划）
     ↓ Python compile_cards 事实+时间+冲突+密度复核
work/timeline[/technical]/motion_cards.lock.json
     ↓ 可选 props.motion_cards（schema_version 2.0 不变）
ComicVideo: TransitionSeries → MotionCardTrack → VisualEmphasisOverlay
     ↓ Remotion 视频；原 48kHz 完整配音交由 FFmpeg 混音
preview/motion_cards_sheet.jpg + motion_cards.json → 试听批准
```

### 当前配方白名单

| recipe | 动作 | 最短/最长 | 漫画适用语义 |
|---|---|---|---|
| `talkcraft-number-slab` | 色块落下 → 数字弹出 → 说明标签 | 42～150 帧 | 金额、涨幅、占比 |
| `talkcraft-ink-underline` | 墨迹沿贝塞尔脊线变宽、逐渐写出 | 32～150 帧 | 概念定义、短句强调 |
| `talkcraft-chapter-card` | 章节引子、标题揭示、强调线停留 | 48～180 帧 | 章节边界、话题切换 |

全部使用固定源代码和逐帧纯计算，不允许运行 JSON 内任意 CSS、HTML 或脚本。当前动画全屏覆盖原漫画，不依赖拆分图层；每个镜头最多一个独立字卡，每个滑动 60 秒窗口最多两个。全部事件还必须落在相应镜头的转场之外；与已有关键词视觉强调时间重合则编译失败。**建议保留大部分镜头原状**，无需为了炫技塞满模板。

### 选定计划协议

输入可选 `input/motion_cards.json`；不存在等价于旧版本，无 `motion_cards` props 字段。例子中的哈希须替换为本期 `input/script.txt` 的真实 SHA256、区间须是真实中文 Unicode 码点半开区间：

```json
{
  "schema_version": "1.0",
  "script_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "events": [
    {
      "id": "MC-001",
      "shot_id": "SHOT-001",
      "recipe": "talkcraft-number-slab",
      "script_range": [7, 11],
      "text": "166元",
      "style": "paper",
      "source": "manual",
      "start_frame": 44,
      "end_frame": 106
    }
  ]
}
```

说明：`text` 必须逐 Unicode 码点与原文片段完全相等；数字卡仅可展示原文数值。为保证 1080p 可读，数字卡文案最多 12 个 Unicode 字符，墨迹及章节卡最多 14 个，可选 `label` 最多 20 个且必须能在该镜头文案里找到，否则拒绝。风格只能是 `paper`、`ink`、`bright`。事件持续时间是原时间轴的绝对 `[start_frame,end_frame)`，不得越过转场；不允许选定计划自动扩展视频总帧数。

### Agent 及规则候选操作

```powershell
.venv/Scripts/python.exe -m static_comic motion propose --project <episode> --provider rules
.venv/Scripts/python.exe -m static_comic motion import --project <episode> --file work/motion/proposals.json
.venv/Scripts/python.exe -m static_comic motion inspect --project <episode>
.venv/Scripts/python.exe -m static_comic compile --project <episode>
.venv/Scripts/python.exe -m static_comic preview --project <episode>
```

旧计划存在且候选改变时，`import` 必须显式添加 `--replace`；不会在 `propose` 阶段替换。规则模式目前依据**已有、可验证的逐字对齐**，对原文数字、明确的章节提示词（如「第一章」「接下来」）及「所谓 X」「这就是 X」等定义语义提出对应的数字、章节或墨迹字卡候选。没有足够声学证据明确返回 `UNAVAILABLE`，不会推测发音时间；规则并不具备真正的画面语义识别能力。外部 `agent` 模式没有配置可证明的视觉模型时返回 `UNAVAILABLE`，Agent 可通过本期可信观察制作规范 JSON 后由 `import` 进入相同编译门禁。编译 PASS 不等于人类已确认成片。

### 试听与 QA

选定计划参与 `timeline.input_hashes`、Remotion props、构建缓存键和当前试听快照。动态字卡有实际视频抽出的入场、重点、停留及退场帧；`motion_cards_sheet.jpg` 和帧摘要进入批准绑定。删除全部卡片时，旧视频的零事件轨保持原行为。声音依旧走现有 `emphasis` 四类 SFX 事件与 FFmpeg，不单独引入另一个声轨时钟。

**当前限制**：真实图像语义推断尚未自动接入；普通系统中文字体的跨机器一致性仍需真实设备视觉审核；视频卡作为整镜覆盖而不是任意前/后景互动；纯展示型音效必须另行建立授权、人工批准并试听。技术夹具不替代真实漫画审图或完整视听验收。

## 技术夹具

```powershell
.venv/Scripts/python.exe scripts/create_motion_fixture.py --output reports/sc-m/fixture-v1
.venv/Scripts/python.exe -m static_comic preview --project reports/sc-m/fixture-v1 --technical-fixture
```

60 秒 TEST_ONLY 图形素材含合成测试音轨，无实际人声模型或真人审批；它用于检查在原来的 1800 帧上插入两个动态字卡后画面、音频时长与原有缓存/转场仍正确。脚本要求新目录为空，避免覆盖用户已有工作。
