# 从一份现成稿件开始

先用仓库自带的小文章走一遍流程，再换成自己的稿件。这样容易区分安装问题与素材问题。

## 安装

在仓库根目录打开终端。Windows 使用以下命令：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e packages/core -e apps/cli
.venv/Scripts/python -m wechat_studio_cli --version
```

在 Linux/macOS 上，将 `.venv/Scripts/python` 换成 `.venv/bin/python`。公众号编辑器中的粘贴结果需要在自己的浏览器确认。

## 创建与渲染

```powershell
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace workspace init
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article create --name "一次整理" --mode layout_only --project-id first-article --article-file examples/first-article.md
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article validate first-article
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article render first-article
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace preview serve --project first-article
```

`layout_only` 用于已有完整稿件；另外还有共同写作的 `co_write` 与整理零散材料的 `organize` 模式。CLI 管理文件和渲染，具体写作由作者或所用 Agent 完成。

文章保存在 `.local/workspace/articles/first-article/`。其中 `article.md` 为正文，`article-plan.yaml` 记录结构，`materials` 保存登记素材。`build` 包含预览、正文 HTML、图片清单和交付检查记录。

渲染命令结束后不会自动发布文章。预览服务会一直运行，结束预览后在终端按 Ctrl+C。

## 修改已有文章

准备好新稿件以后，更新同一项目：

```powershell
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article update first-article --article-file my-article.md
.venv/Scripts/python -m wechat_studio_cli --workspace .local/workspace article render first-article
```

图片通过 `--image path/to/image.png` 登记。想规定某张图的位置，可以让文章 skill 将它写入段落计划；指定“这段不改”“图放在第二节之后”时，工具保留对应的锁定信息。

## 复制到公众号

预览中的主按钮复制 HTML 富文本和纯文本。粘贴到公众号编辑器后，检查图片、字号和间距。如果某张本地图片未随粘贴保留，可以使用占位复制，并按 `image-checklist.md` 补传图片。

素材和风格库默认保存在个人工作区。本文使用 `.local/workspace` 便于试用；正式使用时，可以通过 `--workspace` 选择自己的文章目录。

[让 Agent 使用这些操作](SKILLS.md) · [风格库](STYLES.md)
