# 怎样检查工作结果

0.1.1 源码版在 Windows / Python 3.12 下通过 138 项测试，以及新工作区的文章渲染和三个 skill 启动检查。[运行记录](verification.json)列出命令与范围；远程 CI 结果可在仓库 Actions 查看。

自动测试覆盖文件与项目结构、素材引用和锁定、样式版本、文章渲染、命令输出，以及预览中的复制逻辑。

从一个新的工作区创建示例文章，再检查和渲染，可以验证基本运行路径：

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/python tools/smoke_public.py --output .local/smoke
.venv/Scripts/python tools/check_public_release.py
```

`smoke_public.py` 使用自带文章，生成实际正文、预览和交付报告，并核对复制入口与基础样式。脚本也在临时目录安装三个 skill，执行其 CLI 入口，检查安装路径。

浏览器中的复制行为与粘贴后的图片、间距属于实际使用检查。预览页提供图片占位和清单，便于处理编辑器未接收的图片。测试记录与源码版本一同保留，使用者可在 Actions 查看对应提交的运行结果。

风格分析的输出可以逐项检查来源、内容特征和排版特征。写作是否适合文章，需要作者结合输入和结果作出选择。
