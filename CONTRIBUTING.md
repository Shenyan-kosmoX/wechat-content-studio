# 一起改进公众号工作台

遇到安装、排版或复制问题，可以先开 Issue。附上工具版本、操作步骤，以及可以公开的最小输入，说明期待的效果与实际结果。

如果改进涉及某种排版，请用自己编写的小文章和基础样式说明。参考账号模板、私人文章和风格库保留在各自工作区，便于维护公共代码和个人素材各自的版本。

## 本地检查

```powershell
.venv/Scripts/python -m pip install -e packages/core -e apps/cli pytest
.venv/Scripts/python -m pytest -q
.venv/Scripts/python tools/check_public_release.py
```

提交 PR 时说明修改目的、检查方法和实际结果。涉及复制效果时，补充浏览器和编辑器中的观察；文章内容可以使用仓库示例。

## 代码结构

确定性处理放在 Core，命令解析放在 CLI。Skill 负责帮助 Agent 选择模式、保留用户要求和调用工具。修改安装或运行入口时，请同时检查三个 skill 的指引。

社区交流见 [Shenyan-kosmoX](https://github.com/Shenyan-kosmoX/community)。
