# nb-autodoc

![Python Version](https://img.shields.io/badge/Python-3.7%2B-%233eca5f)

### Module 处理标准

1. 成员寻找和顺序

    所有子模块都会在内部 import (`config.skip_import_modules`)，严格依照 `__dict__` 或者有 stub 时调用 stub 的 definitions 进行解析

2. definition 和 external

    definition 规定在本模块的定义成员。external 规定来自外部模块的成员，只有 from...import 中解析到对应模块名才会认为是 external

    动态创建的函数或类都可以由 definition finder 配合 inspect 解决

3. stub 和 real

    stub 会以 CO_FUTURE_ANNOTATIONS flag compile 并执行。

    当存在 stub 和 real 时，real 仅用于获取 docstring（可能是 c extension）

    当 real 不是 sourcefile (etc. c extension) 并且没有 stub 时，不做处理

    当 stub 是独立的，没有实际模块时，也会进行输出（相当于把 real docstring 设为空）

    以上信息由 Module 解析提供，Module 仅向外部提供可访问的 definition 和 external

4. docstring 绑定则不可变，annotation 重复出现则覆盖

### Class 处理标准

待定，估计有一些 type parameter 和成员类型的问题。

### autodoc problem

考虑这样一个情况:

```
./
main.py
internal/
    __init__.py
external/
    __init__.py
```

internal 有个 Foo 类，包括成员 a 和 b，需要在 external 控制 Foo 和其成员要怎么做？


解决方案：根据 ast from...import 进行链式解析。

### Literal annotation

1. 验证是否 new style，由于 new style 处理过于复杂（FunctionType 嵌套和转换问题），对其只进行 refname 替换

2. 不是 new style 则进行 evaluate

### others

问题:
    1. 来自其他模块的对象在本模块输出，链接问题
