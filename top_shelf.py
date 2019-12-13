import functools
import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from numbers import Number, Complex
from typing import *

import hypothesis.strategies as st
from hypothesis import given, infer


Scalar = Union[AnyStr, int, bool]

RegularFunction = Callable[[Scalar], Scalar]


def identity(x: Any) -> Any:
    return x


class Monad(ABC):
    @classmethod
    @abstractmethod
    def unit(cls, value: Any) -> "Monad":
        raise NotImplementedError

    @abstractmethod
    def map(self, function: RegularFunction) -> "Monad":
        raise NotImplementedError

    @abstractmethod
    def apply(self, lifted: "Monad") -> "Monad":
        raise NotImplementedError

    @abstractmethod
    def bind(self, function: Callable[[Scalar], "Monad"]) -> "Monad":
        raise NotImplementedError


def unit(M: Type[Monad], value: Scalar) -> Monad:
    """
    AKA: return, pure, yield, point
    """
    return M(value)


def map(monad: Monad, function: RegularFunction) -> Monad:
    """AKA: fmap, lift, Select"""
    return monad.unit(
        function(monad.value)
        if not callable(monad.value)
        else lambda x: monad.value(function(x))
    )


def apply(lifted_function: Monad, lifted: Monad) -> Monad:
    """AKA: ap, <*>"""
    lifted_function.value: RegularFunction

    return map(lifted, lifted_function.value)


def bind(monad: Monad, function: Callable[[Scalar], Monad]) -> Monad:
    """AKA: flatMap, andThen, collect, SelectMany, >>=, =<<"""
    return function(monad.value)


@dataclass
class Identity(Monad):
    """
    The identity monad. It does nothing but wrap a value.
    """

    value: Union[Scalar, Callable]

    @classmethod
    def unit(cls, value: Any) -> "Monad":
        return unit(cls, value) if not isinstance(value, cls) else value

    def map(self, function: RegularFunction) -> "Monad":
        return map(self, function)

    def apply(self, lifted: "Monad") -> "Monad":
        return apply(self, lifted)

    def bind(self, function: Callable[[Scalar], "Monad"]) -> "Monad":
        return bind(self, function)

    def __eq__(self, other: "Monad"):

        if callable(self.value) and callable(other.value):
            i = random.randrange(0, 100)
            return self.value(i) == other.value(i)

        return self.value == other.value


# ---- tests ---- #


@st.composite
def monads(draw):

    scalars = st.one_of(
        st.integers(), st.floats(allow_nan=False), st.text(), st.booleans()
    )

    unary_functions = st.functions(like=lambda x: x, returns=scalars)

    value = draw(st.one_of(scalars, unary_functions))

    value = (
        value
        if not callable(value)
        else functools.lru_cache(maxsize=None)(value)
    )

    return Identity(value)


@given(monad=monads(), integer=st.integers(), f=infer, g=infer)
def test_map(
    monad: Monad,
    integer: int,
    f: Callable[[int, int], int],
    g: Callable[[int, int], int],
):
    """
    fmap id  ==  id
    fmap (f . g)  ==  fmap f . fmap g
    """
    # make our generated function `f deterministic

    f = functools.lru_cache(maxsize=None)(f)

    assert map(monad, identity) == monad
    # method form
    assert monad.map(identity) == monad

    f = functools.partial(f, integer)

    g = functools.partial(f, integer)

    f_after_g = lambda x: f(g(x))

    m = monad.unit(integer)

    assert map(m, f_after_g) == map(map(m, g), f)
    # method form
    assert m.map(f_after_g) == m.map(g).map(f)


@given(monad=monads(), value=infer, f=infer, g=infer)
def test_bind(
    monad: Monad, value: Scalar, f: RegularFunction, g: RegularFunction
):
    """
    unit(a) >>= λx → f(x) ↔ f(a)
    ma >>= λx → unit(x) ↔ ma
    ma >>= λx → (f(x) >>= λy → g(y)) ↔ (ma >>= λx → f(x)) >>= λy → g(y)
    """
    f, g = _modify(f), _modify(g)

    # left identity

    assert bind(unit(Identity, value), f) == f(value)
    # method form
    assert monad.unit(value).bind(f) == f(value)

    # right identity

    assert bind(monad, monad.unit) == monad
    # method form
    assert monad.bind(monad.unit) == monad

    # associativity

    assert bind(bind(monad, f), g) == bind(monad, lambda x: bind(f(x), g))
    # method syntax
    assert monad.bind(f).bind(g) == monad.bind(lambda x: bind(f(x), g))


@given(monad=monads(), integer=st.integers(), f=infer, g=infer)
def test_app(
    monad, integer, f: Callable[[int], int], g: Callable[[int, int], int]
):
    """
    identity

        pure id <*> v = v

    homomorphism

        pure f <*> pure x = pure (f x)

    interchange

        u <*> pure y = pure ($ y) <*> u

    composition

        pure (.) <*> u <*> v <*> w = u <*> (v <*> w)
    """

    determinize = functools.lru_cache(maxsize=None)

    # f, g = monad.unit(determinize(f)), monad.unit(determinize(g))

    f = determinize(f)

    # identity

    assert apply(monad.unit(identity), monad) == monad
    # method syntax
    assert monad.unit(identity).apply(monad) == monad

    """
    homomorphism

        pure f <*> pure x = pure (f x)
    """

    m = monad.unit(integer)

    assert apply(monad.unit(f), m) == monad.unit(f(m.value))

    assert monad.unit(f).apply(m) == monad.unit(f(m.value))

    """
    The third law is the interchange law. 
    It’s a little more complicated, so don’t sweat it too much. 
    It states that the order that we wrap things shouldn’t matter. 
    One on side, we apply any applicative over a pure wrapped object. 
    On the other side, first we wrap a function applying the object as an argument. 
    Then we apply this to the first applicative. These should be the same.

        u <*> pure y = pure ($ y) <*> u
    
    """

    # assert m.apply(monad.unit(f)) == monad.unit(lambda x: f(x)).apply(f)

    # composition

    # m = monad.unit(identity)
    # m = monad
    #
    # left = apply(apply(apply(monad.unit(compose), m), f), g)
    # right = apply(m, apply(f, g))
    # assert left == right, f'{left} != {right} ; {left.value(1)}'


def _modify(
    function: RegularFunction, pure: Callable[[Any], Monad] = Identity.unit
):
    """Wrap function in a monad, make it deterministic, and avoid NaN since we can't check for equality with it."""

    @functools.lru_cache(maxsize=None)
    def f(x):

        result = pure(function(x))

        if isinstance(result.value, Complex):
            if math.isnan(result.value.imag) or math.isnan(result.value.real):
                return pure(None)
        elif isinstance(result.value, Number) and math.isnan(result.value):
            return pure(None)

        return result

    return f


def compose(f: RegularFunction):
    """
    Compose two functions together in curried form.
    """

    def i(g: RegularFunction):
        def j(x: Scalar):
            return f(g(x))

        return j

    return i


def test():
    test_map()
    test_bind()
    test_app()


if __name__ == "__main__":
    test()
