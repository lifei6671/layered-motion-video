# 可选强调输入示例

`policy.disabled.json` 可直接复制到单期 `input/emphasis_policy.json`。没有策略文件也保持关闭。

两个 manifest 是结构示例，所有 REPLACE 字段、零摘要和持续样本数必须来自实际资源，不能直接用于生产；CANDIDATE 状态也不能进入渲染或混音。原始文件与非空许可附件均放在对应的 assets/fonts 或 assets/sfx 子树。字体真实格式及中文字形由布局/渲染验证，音频格式由音效规范化验证。

只有 visual.enabled 才要求字体；只有 audio.enabled 且计划包含音效才要求音效资源。source_kind 不代表人工批准。技术夹具使用 TECHNICAL_ONLY，不能进入正式生产。
