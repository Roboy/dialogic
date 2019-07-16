# Ravestate property classes

from threading import Lock
from typing import Dict, List, Generator, Any, Tuple
from ravestate.constraint import Signal
from ravestate.threadlocal import ravestate_thread_local

from reggol import get_logger
logger = get_logger(__name__)


class Property:
    """
    Base class for context properties. Controls read/write/push/pop/delete permissions,
    property name basic impls. for the property value, parent/child mechanism.

    _Example (Creating a module containing a property named my_property):_
    ```python
    with Module(name="my_module"):
        my_property = Property(name="my_property")
    ```
    """

    def __init__(
            self, *,
            name="",
            allow_read=True,
            allow_write=True,
            allow_push=True,
            allow_pop=True,
            default_value=None,
            none_value=None,
            always_signal_changed=False,
            wipe_on_changed=True):

        self.name = name
        self.allow_read = allow_read
        self.allow_write = allow_write
        self.allow_push = allow_push
        self.allow_pop = allow_pop
        self.value = default_value
        self.children: Dict[str, Property] = dict()
        self._lock = Lock()
        self.parent_path: str = ""
        self.none_value = none_value
        self.always_signal_changed = always_signal_changed
        self.wipe_on_changed = wipe_on_changed
        self.changed_signal = Signal(f"{name}:changed")
        self.pushed_signal = Signal(f"{name}:pushed")
        self.popped_signal = Signal(f"{name}:popped")

        # add property to module in current `with Module(...)` clause
        module_under_construction = getattr(ravestate_thread_local, 'module_under_construction', None)
        if module_under_construction:
            module_under_construction.add(self)

    def id(self):
        return f'{self.parent_path}:{self.name}'

    def clone(self):
        result = Property(
            name=self.name,
            allow_read=self.allow_read,
            allow_write=self.allow_write,
            allow_push=self.allow_push,
            allow_pop=self.allow_pop,
            default_value=self.value,
            always_signal_changed=self.always_signal_changed,
            wipe_on_changed=self.wipe_on_changed)
        result.set_parent_path(self.parent_path)
        return result

    def __hash__(self):
        return hash(self.id())

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def set_parent_path(self, path: str):
        """
        Set the ancestors (including modulename) for a property

        * `path`: ancestry in the form of modulename:parent_prop_name (or simply modulename)
        """
        if not self.parent_path:
            self.parent_path = path
            for signal in self.signals():
                signal.parent_path = path
        else:
            logger.error(f'Tried to override parent_path of {self.id()}')

    def gather_children(self) -> List['Property']:
        """
        Collect this property, and all of it's children.
        """
        result = [self]
        for child in self.children.values():
            result += child.gather_children()
        return result

    def lock(self):
        self._lock.acquire()

    def unlock(self):
        self._lock.release()

    def read(self) -> Any:
        """
        Read the current property value
        """
        if not self.allow_read:
            logger.error(f"Unauthorized read access in property {self.id()}!")
            return None
        return self.value

    def write(self, value) -> Tuple[Signal]:
        """
        Write a new value to the property

        * `value`: The new value.

        **Returns:** Tuple of Signals which should be emitted based on
          the new value (either (changed(),) or ()). Spikes will be
          emitted for all returned signals, with the payload set
          to `value`.
        """
        if not self.allow_write:
            logger.error(f"Unauthorized write access in property {self.id()}!")
            return ()
        if self.always_signal_changed or self.value != value:
            self.value = value
            return (self.changed_signal,)
        else:
            return ()

    def push(self, child: 'Property') -> Tuple[Signal]:
        """
        Add a child to the property

        * `child`: The child object

        **Returns:** Tuple of Signals which should be emitted based on
          the pushed child (either (pushed(),) or ()). Spikes will be
          emitted for all returned signals, with the payload set
          to the new path of the pushed child.
        """
        if not self.allow_push:
            logger.error(f"Unauthorized push in property {self.id()}!")
            return ()
        if child.name in self.children:
            logger.error(f"Tried to add already existing child-property {self.id()}:{child.name}")
            return ()
        child.set_parent_path(self.id())
        self.children[child.name] = child
        return (self.pushed_signal,)

    def pop(self, child_name: str) -> Tuple[Signal]:
        """
        Remove a child from the property by it's name.

        * `child_name`: Name of the child to be removed.

        **Returns:** Tuple of Signals which should be emitted based on
          the popped child (either (pushed(),) or ()). Spikes will be
          emitted for all returned signals, with the payload set
          to the old path of the popped child.
        """
        if not self.allow_pop:
            logger.error(f"Unauthorized pop in property {self.id()}!")
            return ()
        elif child_name in self.children:
            self.children.pop(child_name)
            return (self.popped_signal)
        else:
            logger.error(f"Tried to remove non-existent child-property {self.id()}:{child_name}")
            return ()

    def changed(self) -> Signal:
        """
        Signal that is emitted by PropertyWrapper when #write() returns True.
        """
        return self.changed_signal

    def pushed(self) -> Signal:
        """
        Signal that is emitted by PropertyWrapper when #push() returns True.
        """
        return self.pushed_signal

    def popped(self) -> Signal:
        """
        Signal that is emitted by PropertyWrapper when #pop() returns True.
        """
        return self.popped_signal

    def signals(self) -> Generator[Signal, None, None]:
        """
        Yields all signals that may be emitted because of
         this property, given it's write/push/pop permissions.
        """
        if self.allow_write:
            yield self.changed()
        if self.allow_push:
            yield self.pushed()
        if self.allow_pop:
            yield self.popped()
