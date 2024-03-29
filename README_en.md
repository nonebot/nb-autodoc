<div align="center">

<img src="https://raw.githubusercontent.com/nonebot/nb-autodoc/main/logo/logo.png" width=200, height=200 alt="nb-autodoc"></img>

# nb-autodoc

![python version](https://img.shields.io/badge/python-3.8+-%233eca5d)
![pypi version](https://img.shields.io/pypi/v/nb-autodoc)

[简体中文](https://github.com/nonebot/nb-autodoc/blob/main/README.md)
·
[English](https://github.com/nonebot/nb-autodoc/blob/main/README_en.md)

</div>

## Overview

nb-autodoc is a tool designed to automatically generate API documentation from Python source code with [Type hints]((https://docs.python.org/3/library/typing.html)) and [Docstring](https://peps.python.org/pep-0257/).

This tool finds and imports all modules from the package, analyzes the AST and runtime of each module, links internal objects, resolves function signatures and docstring syntax trees, and finally generates complete, reliable and linked API documentation.

## Feature

- type annotation analysis system based on AST

- modern typing representation, such as `X | Y`, `list[str]`, `(*args) -> Any`

- stub (.pyi) support

- TYPE_CHECKING support

- Re-export support, resolve import reference from AST

- Overload function support

## Usage

Install via pip:

```
pip install nb-autodoc
```

Run nb-autodoc:

```
nb-autodoc {package_name}
```

Other CLI options:

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

**tip:** use `--undoc` rather than `--skip`，the latter will skip the module import and analysis.
