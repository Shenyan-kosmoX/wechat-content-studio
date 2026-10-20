# WeChat Content Studio · 公众号内容工作台

文章写完以后，还有不少细活：标题和正文怎样分层，图片放在哪里，引用怎样呈现，复制到编辑器后又要检查哪些地方。WeChat Content Studio 把文字、素材、排版和预览放进一个本地文章项目，让这些工作可以保存下来，下一次继续修改。

你可以直接使用 Python CLI，也可以让 Agent 通过三个 skill 协助整理。文章和样式库保存在自己的电脑上，预览页提供公众号富文本复制。

[开始使用](docs/QUICKSTART.md) · [使用三个 skill](docs/SKILLS.md) · [风格与素材](docs/STYLES.md) · [参与开发](CONTRIBUTING.md)

## 它能帮你做什么

| 需要完成的工作 | 对应能力 |
| --- | --- |
| 从选题或零散材料开始写 | 记录写作要求，组织文章结构，登记文字与图片素材 |
| 给完整稿件排版 | 保存正文与段落计划，保留指定文字、素材顺序和图片位置 |
| 预览并复制到公众号 | 生成本地 HTML 页面，复制富文本与纯文本；图片需要补传时提供插入清单 |
| 整理喜欢的排版特点 | 从自己选定的参考材料分析文字与布局，生成可检查的风格候选 |
| 管理自己的风格库 | 导入、确认、保存版本、组合预设与归档；旧文章保留原来的样式引用 |

文章编排、风格提取、风格管理分别由 [三个 skill](docs/SKILLS.md) 提供入口。它们共用同一套工具，素材和版本也能互相接续。

## 先试一篇文章

源码版需要 Python 3.11+。当前主要面向 Windows，保留仓库并以 editable 方式安装，运行时会读取仓库中的资源。

```powershell
git clone https://github.com/Shenyan-kosmoX/wechat-content-studio.git
cd wechat-content-studio
python -m venv .venv
.venv/Scripts/python -m pip install -e packages/core -e apps/cli
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace workspace init
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article create --name "一次整理" --mode layout_only --project-id first-article --article-file examples/first-article.md
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article render first-article
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace preview serve --project first-article
```

浏览器打开后，先看正文与图片位置，再点击“复制公众号富文本”。到公众号编辑器粘贴后，检查字号、间距和图片；图片传递不成功时，使用预览中的占位复制与图片清单补齐。详细步骤见 [第一次使用](docs/QUICKSTART.md)。

## 用自己的素材和风格

公开版附带一套朴素的基础排版，方便第一次运行。你可以导入自己的 Style Pack，或从已选定的文章中整理新的候选。参考账号的成套模板、私人风格库和已有文章由使用者在本地管理。

排版适合怎样的文章，可以通过输入与输出比较判断。写作特点需要作者自己审阅，导入风格以后也可以继续调整。更多说明见 [风格与素材](docs/STYLES.md)。

## 项目组成

- `packages/core`：文章、素材、样式、验证和渲染。
- `apps/cli`：创建、更新、检查与预览文章的命令。
- `plugins/wechat-content-studio/skills`：三个 Agent skill 及使用参考。
- `resources`：结构定义、预览界面和基础排版组件。
- `tests`：素材锁定、样式版本、文章渲染与 CLI 等检查。

当前发布为 **0.1.1 源码版**。技能会调用本地 CLI，文章创作由你使用的 Agent 配合完成。完成预览后，由作者在公众号后台粘贴、检查和发布。

## 一起改进

排版效果、安装步骤、参考分析和样式管理，都欢迎使用反馈。提问时附上操作步骤、工具版本和可以公开的小样例；想改代码，可以先看 [贡献指南](CONTRIBUTING.md)。

[Shenyan-kosmoX 社区](https://github.com/Shenyan-kosmoX) · [发布内容与许可](docs/SOURCES.md) · [检查方法](docs/VALIDATION.md) · [项目索引](research.yaml)
