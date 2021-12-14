# nb-autodoc

![Python Version](https://img.shields.io/badge/Python-3.9%2B-%233eca5f)

## 简介

适用于 NoneBot 的 API 自动化文档生成器，对模块源码自动生成文档。

在对模块对象进行参数解析和类型注解提取的基础上，还提供遵循 [Google Style Docstring](https://google.github.io/styleguide/pyguide.html) 的 Docstring 解析器，完成了对复杂文档输出的要求。

此外，目前的 nb-autodoc 还基于 ast 模块实现了对 stub file 的处理和重载函数的解析。

## Schedule

1. reduce code redundancy

2. 在第一步的基础上，首先确保生成的文档具有高度的可用性和容错率，优先投入生产

3. 提高代码质量

4. 提高文档质量

## Development Roadmap

- 1.0

    - [ ] 使用 AST 解析整个模块和子模块和命名空间，解除对 import_module 的完全依赖。此处仅在单文件层面操作，并且会获取字符串层面的所有 docstring 和类型注解。最后在保持文档和源码一致的基础上增加功能。

    - [ ] 使用 AST 解析 `if TYPE_CHECKING` 的所有 import 和 importfrom (performance relative import) 并加入到每个模块的 attributes dict，用于实现 `get_type_hints`，理论上可以正确签名所有 callable 对象。

    - [ ] 更好的 pyi 解析逻辑。更好的 overload 解析逻辑。
