# Earshot 离线声音供应与动态镜头声音同步（SC-A1 / SC-A2）

## 设计边界

Earshot 是**音效生成、试听和可选的听音质检工具**，不是替代本项目的音频混音器、WhisperX 对齐器或完整旁白母带。已有 `static_comic/sfx_library.py` 继续执行资源核验与 48kHz 双声道标准化；`static_comic/sfx_mix.py` 继续负责独立 SFX 轨、FFmpeg 精准混音、逐采样审计与峰值限制。

上游：<https://github.com/Leonxlnx/earshot>，作者 Leon Lin，**MIT License**。此处使用固定上游提交 `591fa3e028032e6dce56620a20e932e35667e8d8`；Bank 版本 `forge_v2r6+forge04r1+fit1+pluck1`。项目源码在 `static_comic/earshot_provider.py`、`static_comic/earshot_cues.py`、共享 Schema 的 `sfxManifest`、`sfxEvent` 等。

用户明确说明这是非商业项目。MIT 仍需保留许可声明；在技术和生产项目中具体导出的 WAV 内嵌清单也保留了来源、作者、许可和摘要。上游 15 个由 CC0 声源拟合而成的声音未进入第一批白名单；日后使用 `earshot fit` 需要核对原录音许可。

## 可复现本地部署（本次已完成）

安装源代码于本 Skill 已被 Git 忽略的 `reports/` 子目录，不污染已有 `uv.lock`、不下载听音模型，也不将外部仓库嵌入当前 Git 提交。

```powershell
cd .agents/skills/static-comic-video
git clone https://github.com/Leonxlnx/earshot.git reports/earshot-runtime/source
git -C reports/earshot-runtime/source checkout 591fa3e028032e6dce56620a20e932e35667e8d8
.venv/Scripts/python.exe -m static_comic earshot doctor
```

运行时拒绝未知/脏 Git 提交；`doctor` 检查上游 252 个银行音效，首版开放其中 **237 个纯 DSP 合成音效**，15 个 `fit/*`（从 CC0 录音拟合）暂不直接作为 MIT 音效导入，需要单独保留原录音的 CC0 来源证据。使用项目已有 numpy/scipy，不加载 CLAP、AST 或大型 torch 听音模型。若源代码未安装，提示 `EARSHOT_UNAVAILABLE`，不会静默联网安装；运行时文件保持在 `reports/earshot-runtime/source/`，不覆盖用户文件。

## 音效资产生命周期

```powershell
# 验证声音库 / 查询受支持声音
.venv/Scripts/python.exe -m static_comic earshot doctor
.venv/Scripts/python.exe -m static_comic earshot list

# 按需生成数字卡配音效果，输出至当前单期音效资源库
.venv/Scripts/python.exe -m static_comic earshot render --project <episode> --sound ui_pop/soft --uses keyword --seed 7

# 其他例子：转场的轻撞击声
.venv/Scripts/python.exe -m static_comic earshot render --project <episode> --sound cut_hit/punch --uses transition --seed 8

# 本机静态试听页；仅显示已生成音效，不执行脚本、不代替真人批准
.venv/Scripts/python.exe -m static_comic earshot audition --project <episode>
```

输出包括：`assets/sfx/earshot-<options-hash>.wav`、`assets/sfx/licenses/earshot-MIT.txt`、`assets/sfx/manifest.json` 中的生成配方记录、`reports/earshot/<asset-id>.json` 的哈希/动作节点摘要和 `reports/earshot/audition.html`。生成时默认 `review_status=CANDIDATE`，不会写 `APPROVED` 或捏造签名收据；未选中的候选不会阻塞原有已批准音效，只有被本次计划引用的资源才会被送入 `verify_asset` 做正式授权和字节校验；`--technical-fixture` **仅用于独立技术夹具**，设置 `TECHNICAL_ONLY`，不能进入正式制作。

正式使用仍需用户听过音效后，按既有 `emphasis prepare-resource` / `human-confirm` / `approve-resource` 流程留下与当前素材、来源、许可摘要绑定的有效批准收据。修改声音种子、参数、许可、用途或源文件摘要后必须重新审核。不能因为耳声 `sfx check` 返回 PASS 就视为符合用户审美或拥有版权。

## 动态镜头声音事件（SC-A2）

`static_comic earshot propose-cues --project <episode>` 读取**已选定且通过编译**的动态镜头配方，只针对语义明确且已有批准音效的动作点提出候选：

| 视觉配方 | 音效优选 | 事件类型 / 锚点 |
|---|---|---|
| `talkcraft-number-slab` | `ui_pop/*` | keyword · motion_marker impact（卡开始 +24 帧） |
| `talkcraft-ink-underline` | `swish/*` | keyword · motion_marker impact（卡开始 +28 帧） |
| `talkcraft-chapter-card` | `cut_hit/*` | transition · motion_marker impact（卡开始 +28 帧） |

候选音效默认使用 `sync_to=peak`：系统先读取 Earshot 原 WAV 的 `cue_points.peak_samples`，再根据图形动作的**绝对帧 ×1600**算出 WAV 的开始播放采样点。以 598 帧 / 1704 采样偏移为例，混音从 955096 开始，峰值正好对齐 956800（598 × 1600）。`sync_to=onset|peak|end` 为可选精确对齐能力；原来的音效事件不带此字段时严格保持原始“裁剪后的音频起点”语义。

```powershell
# 只产出 work/audio/earshot/proposals.json；不更改 input/emphasis_plan.json
.venv/Scripts/python.exe -m static_comic earshot propose-cues --project <episode>
# Agent 在预览/候选审查后显式导入
.venv/Scripts/python.exe -m static_comic emphasis import --project <episode> --file work/audio/earshot/proposals.json
.venv/Scripts/python.exe -m static_comic compile --project <episode>
.venv/Scripts/python.exe -m static_comic preview --project <episode>
```

没有启用音效、未选定动态镜头、缺少审核过的音效、设置为 `silence` 的镜头或出现密度冲突时，直接给出零音效/跳过诊断。不能强迫每个镜头发声。对于静态图片中仅由视觉模型识别的脚步、关门、流水等现场音，仍需未来实际的画面与语义证据，当前不会胡乱推测。

## 高级听音质检（SC-A3，未安装/未执行）

Earshot 的 `rank / match / find / timeline / sheet / critique` 需要额外 CLAP / AST 模型（约 1.1GB），本期**没有下载**。模型启用前，先确认本机磁盘与 CPU 开销并通过独立的模型锁文件，所有音频留在本机。若使用可选外部 LLM，请单独征得上传授权；未授权不上传。

当前只执行 Earshot 纯 DSP sound bank 自带的无模型声学质量审计（波形头尾、削波、振铃、截断、异常音高等），并由既有 FFmpeg 进行可验证的整片混音。**机器评分不能替代真人完整试听。**

## 实施验收及路径

- 新增 `tests/test_earshot_provider.py`：固定上游来源、生成确定性、字节摘要、不能自签、非法 ID、动作锚点峰值、镜头移动后同步重计算。
- 60 秒 TEST_ONLY 项目 `reports/sc-m/fixture-v1/`，其中音效候选/输出、技术 WAV 与实际有声预览仅用于技术校验，不代表真实漫画/人声项目验收。
- 保留全部原有未提交的 `AGENTS.md`、`sound/*.mp3`、视觉注册与缓存产物，禁止清理/提交用户文件。
