import logging


def logfilter(record: logging.LogRecord) -> bool:
    """Transform LogRecord to add context info."""
    from nb_autodoc.manager import current_module

    builder = []
    try:
        module = current_module.get()
    except LookupError:
        builder.append(record.name)
    else:
        builder.append(module.name)
    if record.args:
        fno, *_ = record.args
        record.args = None
        if isinstance(fno, tuple):
            builder.append(":".join(map(str, fno)))
        else:
            raise RuntimeError
    builder.append(record.msg)
    record.msg = " ".join(builder)
    return True


logger = logging.getLogger("nb_autodoc")
"""Logger for each user module if in analysis context.

Example:
    ```python
    logger.info("msg", ("util.pyi", 34))
    logger.info("msg", None)
    logger.info("msg")
    ```
"""
logger.addFilter(logfilter)
console_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# class _LogCallProto(Protocol):
#     # posonly future
#     @overload
#     def __call__(self, _msg: Any) -> None:
#         ...

#     @overload
#     def __call__(self, _msg: str, _tp_fileno: Optional[Tuple[str, int]] = None) -> None:
#         ...

#     def __call__(self, _msg: Any, _tp_fileno: Optional[Tuple[str, int]] = None) -> None:
#         ...


# class ModuleLogger:
#     """Log factory for each user module."""

#     def __init__(self, obj: "Module") -> None:
#         self.obj = obj

#     def build(self, _msg: Any, _tp_fileno: Optional[Tuple[str, int]] = None) -> Any:
#         """Format: `usermod.util util.pyi:34 message`"""
#         if isinstance(_msg, str):
#             builder = []
#             builder.append(self.obj.name)
#             if _tp_fileno is not None:
#                 builder.append(":".join(map(str, _tp_fileno)))
#             builder.append(_msg)
#             _msg = " ".join(builder)
#         return _msg

#     def _log(self, *args: Any, logfunc: Callable[[Any], None], **kwargs: Any) -> None:
#         # kwargs should be removed future
#         return logfunc(self.build(*args))

#     def __getattr__(self, attr: str) -> _LogCallProto:
#         # debug,info,warning,error,exception,fatal
#         log = getattr(_logger, attr)
#         return partial(self._log, logfunc=log)
