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
