# nb-autodoc

![Python Version](https://img.shields.io/badge/Python-3.9%2B-%233eca5f)

## 简介

适用于 NoneBot 的 API 自动化文档生成器，对模块源码自动生成文档。

在对模块对象进行参数解析和类型注解提取的基础上，还提供遵循 [Google Style Docstring](https://google.github.io/styleguide/pyguide.html) 的 Docstring 解析器，完成了对复杂文档输出的要求。

此外，目前的 nb-autodoc 还基于 ast 模块实现了对 stub file 的处理和重载函数的解析。

## Cheat Sheet

文档样板

### Module

```
"""
description.

FrontMatter:
    sidebar: auto
    option:
        (anything nested)
"""
```

**注意:** FrontMatter 需要位于 description 的后面

### Class

```
"""
参数:
    name: desc
    kwargs: other desc

属性:
    attr1: desc
"""
```

`__init__` 无需任何文档，将参数部分写于类的 docstring 便会自动生成

属性一般用于描述三方库的基类属性

### Function

```
"""
参数:
    name: desc, case in ['case1', 'case2']
        - `case1`: desc
        - `case2`: desc
    name2 (Union[pkg.foo.Foo, str]): desc

返回:
    Optional[pkg.foo.Foo]: 描述

用法:
    ```python
    print('hello world!')
    ```
    任何描述
"""
```

参数的类型注释会自动生成，如果需要覆写，请对模块内部成员使用全名便于添加 url link。

参数块之间内允许长描述，长描述的部分会自动缩进并输出。

返回里可以写任何内容，但是当内容符合正则 `^(?! )([\w\.\[\], ]+)(?: *\(([\w\.\[\], ]+)\))?(.*?):` 时，会被认为是可解析并对其做一些处理（对 annotation 添加 url link 之类的），否则直接输出。

### Variable

这部分没啥特别的

### 版本写法

```
版本: 1.1.0+

参数 (1.1.0+):
    name (annotation) {version}`1.1.0+`: desc
```

特别地，Variable 额外添加了类型版本的识别

```
类型版本: 1.1.0+
```

### 描述块拓展语法

- version

  ```
  {version}`1.1.0+`
  ```

- ref

  ```
  {ref}`pkg.foo.Foo`
  ```

## 黑白名单机制

模块上定义 `__autodoc__` 变量来控制成员输出。类型是一个字典。键是成员的名称，值是 True 或者 False。

如:

```
__autodoc__ = {
    "MyClass": True,
    "MyClass.attr": False
}
```

当值为字符串时，会覆盖对应对象的 docstring，这个特性一般用于对三方库的描述。

**注意:** 不建议将来自其他模块的成员设为 True 强制输出。（引发链接问题和 stub file 解析问题）

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
