# 三个 skill，各自处理一件事

文章编排、整理参考风格、维护风格库，可以在不同时间进行。三个 skill 使用同一套本地 Core 与 CLI，让已经登记的素材和样式能够继续使用。

| Skill | 什么时候用 | 可以怎样提出需求 |
| --- | --- | --- |
| [wechat-compose-article](../plugins/wechat-content-studio/skills/wechat-compose-article/SKILL.md) | 从选题、素材或完整稿件开始制作文章 | “把这份文字和两张图片排成公众号文章，第二张图放在结尾之前。” |
| [wechat-distill-style](../plugins/wechat-content-studio/skills/wechat-distill-style/SKILL.md) | 从选定参考文章整理写作与排版特点 | “比较这几篇文章的标题、引用和图片节奏，整理一份可调整的候选风格。” |
| [wechat-manage-style-library](../plugins/wechat-content-studio/skills/wechat-manage-style-library/SKILL.md) | 查看、导入、确认和归档自己的风格 | “列出我的风格，把这套已经确认的排版保存为新版本。” |

## 安装到本地 skills 目录

先按 [快速开始](QUICKSTART.md) 安装 Core 与 CLI。然后用同一个 Python 运行安装脚本，明确指定你的 Agent 使用的 skills 目录：

```powershell
.venv/Scripts/python tools/install_skills.py --target "C:/path/to/your/skills"
```

脚本复制三个 skill，并记录当前 Python 的位置供调用。选择 Agent 已配置为读取的位置；需要重新载入会话时按该工具的方式操作。已有同名目录时安装脚本会停止，保留原版本。

安装后可以检查其中一个入口：

```powershell
.venv/Scripts/python "C:/path/to/your/skills/wechat-compose-article/scripts/run_cli.py" --version
```

仓库、Python 环境或安装位置改变后，在新的 skills 目录重新运行安装脚本，或先备份旧 skill 再安装。当前源码使用 editable 安装，请保留代码仓库。

## 在项目源码中使用

也可以直接读取仓库中的 SKILL.md，并使用已安装的 CLI。仓库内的 launcher 会在当前 Python 环境执行命令；`WECHAT_STUDIO_PYTHON` 可以指定安装过工具的 Python。

## 如何选择样式

首次使用附带基础排版。自己的 Style Pack 可以导入工作区；从参考文章整理的风格先保存为候选，查看后再决定是否作为常用样式。个人文章和风格库不需要提交到项目仓库。
