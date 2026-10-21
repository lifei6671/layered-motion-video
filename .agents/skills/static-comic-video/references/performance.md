# SC-P7 Windows 性能记录

这是测试负载与测量工具，不是新的生产入口。真实样片仍按 images → align → transitions → preview → 人工试听 → render-visual/mux → 正式画质审核执行，不得用技术收据代批。

`scripts/benchmark_fixture.py` 复用现有 3 镜头几何夹具，扩展到精确 60/180 秒，音频为静音，只有技术入口接受。它测量 540p 预览、1080p 整片渲染、完整音轨封装和媒体校验的组合开销，不覆盖真实图像细节、ASR、中文对齐或人工工作量。生产样片不得引用这些几何图或 TEST_ONLY 收据作为已审素材。

在 Skill 根执行，输出位置使用独立的 `content/sc-p7-benchmark-60`、`content/sc-p7-benchmark-180`。冷运行目标必须为空；热运行要求同一期已成功冷运行。一次冷/热结果不覆盖，复测应另建测试目录。`cold` 指该项目缓存为空，不表示清空操作系统文件缓存或重启机器。

测量器需要 Windows / PowerShell 7，不增加 Python 依赖。命令文件为 UTF-8 JSON：

```json
{
  "argv": ["<Skill绝对路径>/.venv/Scripts/python.exe", "scripts/benchmark_fixture.py", "--project", "<独立测试项目绝对路径>", "--seconds", "60", "--mode", "cold"],
  "cwd": "<Skill绝对路径>",
  "label": "60s-cold-synthetic",
  "cache_expectation": "cold"
}
```

```powershell
pwsh -NoProfile -File scripts/measure_performance.ps1 -CommandFile <命令文件> -OutputDirectory <新的测量目录> -TimeoutSeconds 1800
```

随后同一项目以 `--mode warm` 执行一次，再对 180 秒新项目重复。不要并行写同一期，也不要在运行之间改动输入、源码或依赖。测量器保留 argv/cwd、命令文件摘要、原始 stdout/stderr 字节、每次进程采样、GPU CSV、主机名与报告。日志编码沿用被测进程。子命令退出码透传，超时为 124，原始报告不会被新运行覆盖。

指标解释：

- `wall_seconds` 包含采样开销和输出排空；是此组合命令的墙钟耗时。
- `sampled_peak_tree_working_set_bytes` 是同次采样中已观察进程工作集之和的最大值，可能重复计算共享页；不是机器物理内存增量，也不保证捕获采样间峰值。
- `sampled_peak_cpu_core_percent` 的 100% 为一个逻辑核；不与整机归一化百分比混淆。
- 浏览器进程计数限被测树的 Chrome/Chromium/Edge；热运行 0 是有效结果。
- `nvidia-smi` 每秒采样整机 GPU，包含 VoiceStudio 和其他任务，不能据此宣称 GPU 消耗全部来自渲染器。不可用时明确 `UNAVAILABLE`。
- 进程树不包含已有 VoiceStudio 服务；很短的进程可能漏采。超时清理根进程及已观察后代；父进程在采样前消失可能使后代失去可追溯链。因此此工具不是后台任务管理或完整进程隔离器。
- 测量器的冷/热标签只是声明，`cache_verified=false`。必须同时读取测试项目的 `benchmark-cold.json` / `benchmark-warm.json`：它们核验预览/正式视觉与封装四阶段 `REBUILT` / `HIT`，并保存真实缓存记录。

代码验证：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_sc_p7_*.py' -v
```

真实样片的语义锚点、逐图审批、完整试听和 1080p 细线/裁切画质另行记录。性能结果没有预设 SLA，未测量的项目不得从短夹具推算为通过。
