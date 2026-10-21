# 动画对照数据

`clock-360`、`showcase`、`all-cuts` 各包含一份 props 与 Python 逐帧几何结果，供 `renderer/static-comic/test-visual.mjs` 验证 TypeScript 运镜、离散帧端点和转场约束。

这些固定测试数据来自 `create_fixture.py` 与 `create_visual_fixtures.py` 的技术夹具。它们替代测试对本机 `reports` 目录的依赖；不需要复制图片、配音或视频。几何协议有意变更时，使用相同夹具生成器重新编译并审查两份 JSON 的差异。
