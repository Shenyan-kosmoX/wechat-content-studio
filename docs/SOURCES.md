# 发布内容与许可

本项目公开 Core、CLI、三个 skill、运行界面与基础排版，原创代码与文档采用 [MIT License](../LICENSE)。

首个公开源码版本从作者维护的项目整理而来，以独立 Git 历史发布。参考账号的样式包、文章样本、个人工作区、旧 HTML 快照和历史构建包未纳入。公开版的基础组件为此次发布重新编写。

## 运行依赖

| 依赖 | 用途 | 上游许可 |
| --- | --- | --- |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 结构检查 | MIT |
| [platformdirs](https://github.com/tox-dev/platformdirs) | 个人文件路径 | MIT |
| [PyYAML](https://github.com/yaml/pyyaml) | YAML 读写 | MIT |

开发测试使用 pytest，打包脚本可使用 PyInstaller。当前发行物为源码，不包含旧运行时或预装第三方依赖。依赖通过安装工具从各自来源取得。

自己的文章、风格和参考资料按各自授权使用，不因导入工具而改变许可。
