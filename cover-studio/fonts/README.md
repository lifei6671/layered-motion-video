# 封面工坊字体库

每个一级子目录是一套字体家族，目录下每个字体文件是一种具体规格（字重、字形或格式）。例如：

```text
fonts/
├── README.md
├── LXGWWenKai/
│   ├── LXGWWenKai-Light.ttf
│   ├── LXGWWenKai-Regular.ttf
│   ├── LXGWWenKai-Medium.ttf
│   └── LXGWWenKaiMono-Regular.ttf
└── SourceHanSans/
    ├── Source_Han_Sans_SC_Regular.otf
    ├── Source_Han_Sans_SC_Bold.otf
    └── LICENSE.txt
```

网页中先选择「项目目录字体」，再选「字体家族」和「字形与字重规格」。支持 TTF、OTF、TTC、OTC、WOFF、WOFF2。不同格式的同规格字体均保留为可选项。支持更深层目录：其一级目录仍归为同一字体家族。

字体名称与字重优先参考文件名，必要时读取字体内部元数据；等宽、斜体等也会单独区分。字体预览使用该文件的实际字形。缺少中文字形的压缩网页字体会在生成时报告缺字内容。

新增、删除、替换字体后点击「刷新字体列表」，无需安装或上传字体。字体文件和许可证保留在本机；实际使用前请核对授权范围。
