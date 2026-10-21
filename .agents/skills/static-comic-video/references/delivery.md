# SC-P5 有声预览与正式封装

所有命令在 Skill 根执行，路径由参数数组传递，Remotion 固定使用本地 renderer/static-comic 的 CLI、配置和浏览器；不自动下载。先读 runtime.md。生产素材必须完成 SC-P3A、SC-P3 和 SC-P4；没有真实用户批准不能复制测试收据继续制作。

## 最小命令流程

```powershell
.venv/Scripts/python.exe -m static_comic init --project <new-empty-episode>
.venv/Scripts/python.exe -m static_comic images --help
.venv/Scripts/python.exe -m static_comic align --project <episode>
.venv/Scripts/python.exe -m static_comic transitions --help
.venv/Scripts/python.exe -m static_comic compile --project <episode>
.venv/Scripts/python.exe -m static_comic status --project <episode>
.venv/Scripts/python.exe -m static_comic studio --project <episode>
.venv/Scripts/python.exe -m static_comic preview --project <episode>
.venv/Scripts/python.exe -m static_comic inspect --project <episode>
.venv/Scripts/python.exe -m static_comic approve --project <episode> --input review/preview-decision.json
.venv/Scripts/python.exe -m static_comic render-visual --project <episode>
.venv/Scripts/python.exe -m static_comic mux --project <episode>
.venv/Scripts/python.exe -m static_comic verify --project <episode>
```

init 仅创建空输入布局、默认画布、空图片清单/收据和 SOURCE_POLICY_PENDING，并返回四种供图选择，不预选渠道、不生成配音、不猜分镜。补入原文、完整配音和原文区间分镜后，按 image-supply.md 完成 policy/confirm-policy、plan/confirm-plan、dispatch、ingest、report、review、verify。Agent 生图或图库获取由已授权工具实际执行；没有工具不得声称获取完成。人工供图走同样导入与审图流程。

沿用现有 images、align、transitions、validate/compile 子命令，不另建一套时间线。status 重新检查来源、图片计划、图片批准和编译门禁；无效输入返回 REVIEW_REQUIRED 及原因。普通 CLI 失败退出 2；status 可能成功返回待审状态，调用者应检查 JSON status。

Studio 是无声逐帧检查，不代表有声预览通过。每次预览重新验证并编译。低清输出为 960×540、30 fps，正式为 1920×1080、30 fps；两者沿用同一个 1920×1080 逻辑画布、T、运动与转场窗口，只改变输出 scale 和 CRF。

## 输出与人工决定

- preview/preview_visual.mp4：Remotion 无声低清轨。
- preview/preview.mp4：FFmpeg 复制视频流并编码完整母带的有声预览。
- preview/contact_sheet.jpg、preview/index.html：镜头联系表和可播放审核页；不往视频添加字幕、编号或文字。
- review/approval.json：真实用户对当前有声预览的明确决定。
- work/remotion/visual.mp4、output/final.mp4：批准后生成的正式无声轨与封装成片。
- reports/preview.json、visual.json、render.json、validation.json：输入绑定、工具与源码版本、命令、耗时、媒体摘要和技术验证。

inspect 返回 binding_sha256；Agent 据此准备建议，用户完整观看试听后通过 [human-confirm](human-confirmation.md) 的 preview scope 确认，再把返回的签名文件传给 approve。正式画质使用 final scope 独立确认。下面是建议格式，未签名时不能用于生产批准：

```json
{
  "stage": "preview",
  "binding_sha256": "填写 inspect 返回的当前摘要",
  "human": {"actor": "真实用户", "actor_role": "human", "at": "带时区时间", "evidence": "真实明确回复的可追溯记录"},
  "decision": "APPROVED",
  "checks": {"semantics": true, "full_listening": true, "formal_quality": false},
  "reason": "真实用户对当前预览的意见"
}
```

此片段是说明，摘要和时间必须填入真实合法值。不能把生成成功、模型判断或旧回复当作当前批准。可明确 REJECTED，拒绝会使已有正式产物不能继续通过门禁。决定同时留存于 review/delivery-events 的内容寻址事件文件。

批准绑定原文、源配音和完整母带、图片渠道与逐图许可、供图请求、人工审图收据与图片字节、分镜/语义/覆盖、锁定时间线、暂存图片、渲染配置、Python/Node/FFmpeg/浏览器及渲染源码/锁文件、预览视觉轨、有声预览与联系表。变化后需重新生成预览、确认；摘要用于发现过期状态，不是身份认证。

正式封装后 verify 返回新的 binding_sha256。真实查看 1080p 后，提交 stage=final、formal_quality=true 的独立决定，再执行 verify；质量记录在 review/quality.json。技术、语义、完整试听、正式画质分别记录，只有四项均通过才返回 production_accepted=true。

## 完整音频与验证

FFmpeg 仅执行明确映射：一条已有 H.264 视频流 copy，一条完整母带 AAC 192k/48kHz；没有 shortest、裁音频、变速、FFmpeg 运镜或转场。视觉视频必须无音轨。最终只允许一条视频和一条音频，没有字幕流。

检查恒定 30 fps、T、1080p/预览尺寸、H.264、yuv420p、BT.709、方形像素、零起点和逐帧 PTS。完整解码两个视频并比较每帧 SHA256，确认封装没有改变画面。完整解码 AAC，与母带逐秒比较内容，包括首尾；检查有效播放时长与母带相符，记录首包 skip_samples、最后包及解码填充。允许 MP4 有效时长至多 1 ms 的舍入，以及不足一个 AAC 帧的解码尾部填充；测量时忽略填充不等于裁剪成片。自动内容检查不替代完整试听。

时长验证要求 0 ≤ T×1600−S < 1600。11.981 秒母带的 S=575088、T=360，尾部覆盖差 912 个采样。音频和画面均完整保留。

## 技术示例与范围

`--technical-fixture` 只接收明确技术图片/时间，使用独立 technical 子目录和渲染入口；其审核状态/验证结果不能成为生产批准。scripts/create_delivery_demo.py 复用 SC-P3 已有中文测试配音和声学证据，不重新合成语音、不下载模型、不调用 ASR；输出供开发检查的技术有声预览，保持未批准。

SC-P6 已接入[阶段缓存与失败恢复](cache.md)。单期仍串行执行；临时生成、完整验证后逐文件原子替换，可捕获的发布失败回滚。失败后的 status 返回 FAILED，并列出保留旧记录的输入摘要；RUNNING 遗留状态返回 INTERRUPTED_OR_RUNNING。不提供并发互斥或断电事务保证。旧文件存在不代表当前有效，应重新运行门禁。没有真实原画和用户收据时，不生成真实生产成片；合成测试中的生产形状数据仅验证代码路径。
