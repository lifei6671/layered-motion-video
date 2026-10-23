# Earshot 离线音效集成验收记录（SC-A1 / SC-A2）

## 目标与结构

将 **Leonxlnx/earshot** 作为音效供应及可选质检能力，而非替换已完成的 WhisperX / Remotion / FFmpeg 制作流程。

- 上游：<https://github.com/Leonxlnx/earshot>，MIT License，Copyright (c) 2026 Leon Lin。
- 固定源码提交：`591fa3e028032e6dce56620a20e932e35667e8d8`。
- Sound bank：`forge_v2r6+forge04r1+fit1+pluck1`，252 个项目，首版允许其中 237 个**纯 DSP** 音效；15 个 CC0 拟合 `fit/*` 需要独立保留逐音源证据，暂不自动导入。
- 本机上游副本放 `.agents/skills/static-comic-video/reports/earshot-runtime/source`（忽略目录），Python 已使用项目 `.venv` 现有 numpy/scipy 成功加载银行代码；没有安装额外大模型、没有使用外部音频 API。
- 可复现操作详见 `.agents/skills/static-comic-video/references/earshot.md`。

## 已改动代码

| 路径（相对 Skill 根） | 目的 |
|---|---|
| `static_comic/earshot_provider.py` | 只加载固定提交；sound bank CLI、确定性 48k 双声道 WAV、真实源许可/生成参数/哈希、HTML 试听页；候选禁止自批 |
| `static_comic/earshot_cues.py` | 动态数字卡/墨迹卡/章节卡的音效候选，不修改输入计划，保留静音决定 |
| `static_comic/emphasis_timing.py` | `motion_marker` 动作锚点，`sync_to=peak|onset|end` 精确采样点补偿，缺证据拒绝；旧音效事件默认语义不变 |
| `static_comic/project.py` | 先编译可选动态卡，再编译关联音效；保留互斥检查 |
| `static_comic/emphasis.py` | 验证 Earshot cue/sample 顺序、来源信息；只校验当前音效计划所用素材，未选择的 CANDIDATE 不阻塞旧音效，已选择仍需真人收据 |
| `static_comic/cli.py` | 新增 `earshot` 命令入口 |
| `schemas/contracts.json` / `renderer/static-comic/src/contracts.generated.ts` | 新增可选音效生成元数据、精确声学节点、动作事件及同步模式 |
| `tests/test_earshot_provider.py` | 纯 DSP、哈希/幂等、法律来源、不自批、候选隔离、时间轴同步、非法路径/参数等反例 |
| `references/earshot.md` / `SKILL.md` | 使用方式、固定版本、许可说明、真实审核门禁和边界 |

未改动 FFmpeg 主混音器：继续使用原来的 `static_comic/sfx_library.py` / `static_comic/sfx_mix.py`，保证独立的原始旁白和混音母带。

## 本机实际执行

```powershell
cd .agents/skills/static-comic-video

.venv/Scripts/python.exe -m static_comic earshot doctor
.venv/Scripts/python.exe -m static_comic earshot render --project reports/sc-m/fixture-v1 --sound ui_pop/soft --uses keyword --seed 7 --technical-fixture
.venv/Scripts/python.exe -m static_comic earshot audition --project reports/sc-m/fixture-v1
.venv/Scripts/python.exe -m static_comic earshot propose-cues --project reports/sc-m/fixture-v1 --technical-fixture
.venv/Scripts/python.exe -m static_comic emphasis import --project reports/sc-m/fixture-v1 --file work/audio/earshot/technical/proposals.json --technical-fixture
.venv/Scripts/python.exe -m static_comic compile --project reports/sc-m/fixture-v1 --technical-fixture
.venv/Scripts/python.exe -m static_comic preview --project reports/sc-m/fixture-v1 --technical-fixture
```

- 固定代码银行：`doctor PASS`、252 个银行项目、237 个允许的纯 DSP 项目，`models_used=false`。
- 实际生成音效：`earshot-c793912264091efc92b7dd.wav`，内容哈希 `d876ceacc24152f3ab01b00d19d166c975340ad7d435c77d48483a0e6f58acbd`，8,451 个采样，峰值相对位置 1,704。
- 声学同步：动态数字卡 `MC-004` 命中帧为 598；SFX `EASFX-004` 起始于采样 955,096，加上 1,704 后峰值位置正好为 `598 × 1600 = 956800`。
- 实际技术样片：`reports/sc-m/fixture-v1/preview/technical/preview.mp4`；长度 60 秒、1,800 帧，48 kHz 音频 2,880,000 采样。
- 混音报告：`reports/sc-m/fixture-v1/reports/mix.json`，`status=PASS`、5 个音效事件、`narration_sum_verified=true`、混音外静音检查通过。
- HTML 试听页：`reports/sc-m/fixture-v1/reports/earshot/audition.html`；此页面只提供试听控件，不产生生产批准。
- 现有视觉/声音审核文件绑定继续有效，预览批准：`human_acceptance=NOT_RUN`，不能解释成用户已认可声音。

## 回归结果

| 检查 | 实际结果 |
|---|---|
| 新增 Earshot 提供者单元测试 | PASS（10 项） |
| 原有 Python 音效测试 | PASS（11 项） |
| 原有 Python 动效规划 | PASS（20 项） |
| 原有 Python 动态卡片 | PASS（12 项） |
| 原有 Python 数据契约 | PASS_WITH_SKIP（18 项通过、1 项 Windows 创建软链接权限跳过） |
| 原有 Python 资源审核修复测试 | PASS（4 项） |
| 原有 Remotion/TS 测试 | PASS（96 项） |
| 原有 Python 全片集成测试 | PASS（4 项） |
| 原有 Python 增量构建测试 | PASS（6 项，89.340 秒，当前源码下退出码 0） |
| Git diff --check / 未改用户资源 | PASS（Windows CRLF 语义检查退出码 0；未暂存、提交、推送或清理原用户文件） |

## 生产边界与下一步

- 只对**真实用户明确批准**的资源放行；`CANDIDATE` 的生成音效不会因为 WAV 生成成功自动进入正式视频。技术夹具的 `TECHNICAL_ONLY` 不属于生产批准。
- 自动音效选型只针对有已选中可验证视觉事件的受控卡片；暂未接入场景物体识别、通用语义拟音、背景音乐编曲。没有证据时优先**零音效**。
- Earshot 用于智能听音的 CLAP/AST 约 1.1GB 模型**没有下载**，模型级 `rank/match/timeline/sheet/critique` 标 `NOT_RUN`。已执行的仅是 bank 内无模型的波形质量检查与现有 FFmpeg 混音 QA。
- 最终生产仍需真实漫画 + 真实旁白试听及正式画质审查；当前一切渲染是 TEST_ONLY 技术夹具。
- 工作区改动尚未提交或推送，用户原有音效文件仍保持原样。
