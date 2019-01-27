from typing import List, Set, Generator, Optional, Tuple
from ravestate.spike import Spike
from ravestate.iactivation import IActivation

from reggol import get_logger
logger = get_logger(__name__)


def s(signal_name: str, *, min_age=0, max_age=5., detached=False) -> 'Signal':
    """
    Alias to call Signal-constructor

    * `signal_name`: Name of the Signal

    * `min_age`: Minimum age for the signal, in seconds.

    * `max_age`: Maximum age for the signal, in seconds.
     Set to less-than zero for unrestricted age.

    * `detached`: Flag which indicates, whether spikes that fulfill this signal
     are going to have a separate causal group from spikes that
     are generated by a state that uses this signal as a constraint.
    """
    return Signal(signal_name, min_age=min_age, max_age=max_age, detached=detached)


class Constraint:
    """
    Superclass for Signal, Conjunct and Disjunct
    """

    def signals(self) -> Generator['Signal', None, None]:
        logger.error("Don't call this method on the super class Constraint")
        yield None

    def conjunctions(self) -> Generator['Conjunct', None, None]:
        logger.error("Don't call this method on the super class Constraint")
        yield None

    def acquire(self, spike: Spike, act: IActivation):
        logger.error("Don't call this method on the super class Constraint")
        pass

    def evaluate(self) -> bool:
        logger.error("Don't call this method on the super class Constraint")
        return False

    def dereference(self, spike: Optional[Spike]=None) -> Generator[Tuple['Signal', 'Spike'], None, None]:
        logger.error("Don't call this method on the super class Constraint")
        yield None, None

    def update(self, act: IActivation) -> Generator['Signal', None, None]:
        logger.error("Don't call this method on the super class Constraint")
        yield None


class Signal(Constraint):
    """
    Class that represents a Signal
    """
    name: str
    spike: Spike
    min_age: float
    max_age: float
    detached: bool
    _min_age_ticks: int  # written on acquire, when act.secs_to_ticks is available

    def __init__(self, name: str, *, min_age=0., max_age=1., detached=False):
        self.name = name
        # TODO: Convert seconds for min_age/max_age to ticks
        self.min_age = min_age
        self.max_age = max_age
        self.spike = None
        self.detached = detached
        self._min_age_ticks = 0

    def __or__(self, other):
        if isinstance(other, Signal):
            return Disjunct(Conjunct(self), Conjunct(other))
        elif isinstance(other, Conjunct):
            return Disjunct(Conjunct(self), other)
        elif isinstance(other, Disjunct):
            return Disjunct(self, *other)

    def __and__(self, other):
        if isinstance(other, Signal):
            return Conjunct(self, other)
        elif isinstance(other, Conjunct):
            return Conjunct(self, *other)
        elif isinstance(other, Disjunct):
            conjunct_list: List[Conjunct] = []
            for conjunct in other:
                conjunct_list.append(Conjunct(*conjunct, self))
            return Disjunct(*conjunct_list)

    def __eq__(self, other):
        return isinstance(other, Signal) and self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def signals(self) -> Generator['Signal', None, None]:
        yield self

    def conjunctions(self) -> Generator['Conjunct', None, None]:
        yield Conjunct(self)

    def acquire(self, spike: Spike, act: IActivation):
        if not self.spike and self.name == spike.name() and (self.max_age < 0 or spike.age() <= act.secs_to_ticks(self.max_age)):
            self._min_age_ticks = act.secs_to_ticks(self.min_age)
            self.spike = spike
            with spike.causal_group() as cg:
                cg.acquired(spike, act)
            return True
        return False

    def evaluate(self) -> bool:
        return self.spike and self._min_age_ticks <= self.spike.age()

    def dereference(self, spike: Optional[Spike]=None) -> Generator[Tuple['Signal', 'Spike'], None, None]:
        if (not spike and self.spike) or (spike and self.spike is spike):
            former_signal_instance = self.spike
            self.spike = None
            yield self, former_signal_instance

    def update(self, act: IActivation) -> Generator['Signal', None, None]:
        # Reject spike, once it has become too old
        if self.spike and self.max_age >= 0 and self.spike.age() > act.secs_to_ticks(self.max_age):
            with self.spike.causal_group() as cg:
                cg.rejected(self.spike, act, reason=1)
                self.spike = None
                yield self

    def __str__(self):
        return self.name


class Conjunct(Constraint):
    """
    Class that represents a Conjunction of Signals
    """
    _signals: Set[Signal]
    _hash: Tuple[str]

    def __init__(self, *args):
        for arg in args:
            if not isinstance(arg, Signal):
                logger.error("Conjunct can only be constructed with Signals.")
                raise ValueError
        self._signals = set(args)
        self._hash = hash(tuple(sorted(sig.name for sig in self._signals)))

    def __iter__(self):
        for signal in self._signals:
            yield signal

    def __or__(self, other):
        if isinstance(other, Signal):
            return Disjunct(self, Conjunct(other))
        elif isinstance(other, Conjunct):
            return Disjunct(self, other)
        elif isinstance(other, Disjunct):
            return Disjunct(self, *other)

    def __and__(self, other):
        if isinstance(other, Signal):
            return Conjunct(other, *self)
        elif isinstance(other, Conjunct):
            return Conjunct(*self, *other)
        elif isinstance(other, Disjunct):
            conjunct_list: List[Conjunct] = []
            for conjunct in other:
                conjunct_list.append(Conjunct(*conjunct, *self))
            return Disjunct(*conjunct_list)

    def __contains__(self, item):
        return item in self._signals

    def __hash__(self):
        return self._hash

    def __eq__(self, other):
        return isinstance(other, Conjunct) and self._hash == other._hash

    def signals(self) -> Generator['Signal', None, None]:
        return (sig for sig in self._signals)

    def conjunctions(self) -> Generator['Conjunct', None, None]:
        yield self

    def acquire(self, spike: Spike, act: IActivation):
        result = False
        for si in self._signals:
            result |= si.acquire(spike, act)
        return result

    def evaluate(self) -> bool:
        return all(map(lambda si: si.evaluate(), self._signals))

    def dereference(self, spike: Optional[Spike]=None) -> Generator[Tuple['Signal', 'Spike'], None, None]:
        return (result for child in self._signals for result in child.dereference(spike))

    def update(self, act: IActivation) -> Generator['Signal', None, None]:
        return (result for child in self._signals for result in child.update(act))

    def __str__(self):
        return "(" + " & ".join(map(lambda si: si.__str__(), self._signals)) + ")"


class Disjunct(Constraint):
    """
    Class that represents a Disjunction of Conjunctions
    """
    _conjunctions: Set[Conjunct]

    def __init__(self, *args):
        for arg in args:
            if not isinstance(arg, Conjunct):
                logger.error("Disjunct can only be constructed with conjuncts.")
                raise ValueError
        self._conjunctions = set(args)

    def __iter__(self):
        for conjunct in self._conjunctions:
            yield conjunct

    def __or__(self, other):
        if isinstance(other, Signal):
            return Disjunct(*self, Conjunct(other))
        elif isinstance(other, Conjunct):
            return Disjunct(*self, other)
        elif isinstance(other, Disjunct):
            return Disjunct(*self, *other)

    def __and__(self, other):
        if isinstance(other, Signal):
            conjunct_list: List[Conjunct] = []
            for conjunct in self:
                conjunct_list.append(Conjunct(*conjunct, other))
            return Disjunct(*conjunct_list)
        elif isinstance(other, Conjunct):
            conjunct_list: List[Conjunct] = []
            for conjunct in self:
                conjunct_list.append(Conjunct(*conjunct, *other))
            return Disjunct(*conjunct_list)
        elif isinstance(other, Disjunct):
            logger.error("Can't conjunct two disjunctions.")
            raise ValueError("Can't conjunct two disjunctions.")

    def signals(self) -> Generator['Signal', None, None]:
        return (signal for conjunct in self._conjunctions for signal in conjunct._signals)

    def conjunctions(self) -> Generator['Conjunct', None, None]:
        return (conj for conj in self._conjunctions)

    def acquire(self, spike: Spike, act: IActivation):
        result = False
        for conjunct in self._conjunctions:
            result |= conjunct.acquire(spike, act)
        return result

    def evaluate(self) -> bool:
        return any(map(lambda si: si.evaluate(), self._conjunctions))

    def dereference(self, spike: Optional[Spike]=None) -> Generator[Tuple['Signal', 'Spike'], None, None]:
        return (result for child in self._conjunctions for result in child.dereference(spike))

    def update(self, act: IActivation) -> Generator['Signal', None, None]:
        return (result for child in self._conjunctions for result in child.update(act))

    def __str__(self):
        return " | ".join(map(lambda conjunct: conjunct.__str__(), self._conjunctions))
