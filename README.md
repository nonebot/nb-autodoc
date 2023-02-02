<div align="center">

<img src="https://raw.githubusercontent.com/nonebot/nb-autodoc/main/logo/logo.png" width=200, height=200 alt="nb-autodoc"></img>

# nb-autodoc

![python version](https://img.shields.io/badge/python-3.8+-%233eca5d)
![pypi version](https://img.shields.io/pypi/v/nb-autodoc)

[简体中文](https://github.com/nonebot/nb-autodoc/blob/main/README.md)
·
[English](https://github.com/nonebot/nb-autodoc/blob/main/README_en.md)

</div>

## 简介

nb-autodoc 是一个从 Python 源码的 [类型注解](https://docs.python.org/3/library/typing.html) 和 [Docstring](https://peps.python.org/pep-0257/) 自动生成 API 文档的工具。

本工具从包里查找所有的模块并导入，解析各模块的抽象语法树、运行时类型，链接内部对象，解析函数签名和 docstring 语法树，最终生成完整、可靠、带有链接的 API 文档。

## 主要特性

- 基于 AST 的类型分析系统

- stub (.pyi) 支持

- TYPE_CHECKING 支持

- Re-export 支持，从 AST 解析导入引用

- Overload 重载函数支持

## 用法

从 pip 安装:

```
pip install nb-autodoc
```

运行 nb-autodoc:

```
nb-autodoc {package_name}
```

其他命令行选项:

```
Usage: nb-autodoc [OPTIONS] MODULE

Options:
  -o, --output-dir DIRECTORY      [default: build]
  -s, --skip TEXT                 skip import modules
  -u, --undoc TEXT                undocument modules
  --markdown-linkmode [heading_id|vuepress]
                                  [default: heading_id]
  --help                          Show this message and exit.
```

**提示:** 使用 `--undoc` 而不是 `--skip`，后者会跳过模块的导入和分析。
