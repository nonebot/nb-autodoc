from tests.simple_pkg.api import Api

from .base import Base


class Mixin:
    ...


class A(Mixin, Api, Base):
    ...
