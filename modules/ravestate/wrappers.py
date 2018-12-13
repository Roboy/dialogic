# Ravestate wrapper classes which limit a state's context access

from ravestate.property import PropertyBase
from ravestate import state
from ravestate import icontext
from typing import Any, List, Generator

from ravestate.constraint import s

from reggol import get_logger
logger = get_logger(__name__)


class PropertyWrapper:
    """
    Encapsulates a property, and annotates it with additional r/w perms and a context.
    The context is used to trigger the proper :changed, :pushed, :popped, :deleted
    signals when the property is accessed. The wrapper also takes care of locking the property
    when it is supposed to be written to, and freezing the property's value if it is supposed to
    be read from.
    """
    def __init__(self, *, prop: PropertyBase, ctx: icontext.IContext, allow_read: bool, allow_write: bool):
        self.prop = prop
        self.ctx = ctx
        self.allow_read = allow_read and prop.allow_read
        self.allow_write = allow_write and prop.allow_write
        self.frozen_value = None

        self.prop.lock()
        if self.allow_read:
            self.frozen_value = prop.value
        if not self.allow_write:
            self.prop.unlock()

    def __del__(self):
        if self.allow_write:
            self.prop.unlock()

    def get(self) -> Any:
        """
        Read the current property value or the value of children of the property if child-param is given
        :param child: top-down list of child ancestry of the child to get the value from
        """
        if not self.allow_read:
            logger.error(f"Unauthorized read access in property-wrapper for {self.prop.fullname()}!")
            return None
        elif self.allow_write:
            return self.prop.read()
        return self.frozen_value

    def set(self, value: Any):
        """
        Write a new value to the property.
        :param value: The new value.
        :return: True if the value has changed and :changed should be signaled, false otherwise.
        """
        if not self.allow_write:
            logger.error(f"Unauthorized write access in property-wrapper {self.prop.fullname()}!")
            return False
        if self.prop.write(value):
            self.ctx.emit(s(f"{self.prop.fullname()}:changed"))
            return True
        return False

    def push(self, child: PropertyBase):
        """
        Add a child to the property or to children of the property
        :param child: Parent-less, child-less property object to add.
         Name of the child must be unique among existing children of this property.
        :return: True if the push was successful, False otherwise
        """
        if not self.allow_write:
            logger.error(f"Unauthorized push access in property-wrapper {self.prop.fullname()}!")
            return False
        if self.prop.push(child):
            self.ctx.emit(s(f"{self.prop.fullname()}:pushed"))
            return True
        return False

    def pop(self, childname: str):
        """
        Remove a child from the property or from children of the property
        :param childname: Name of the direct child to be removed
        :return: True if the pop was successful, False otherwise
        """
        if not self.allow_write:
            logger.error(f"Unauthorized pop access in property-wrapper {self.prop.fullname()}!")
            return False
        if self.prop.pop(childname):
            self.ctx.emit(s(f"{self.prop.fullname()}:popped"))
            return True
        return False

    def enum(self) -> Generator[str, None, None]:
        """
        Get the full pathes of each of this propertie's children.
        """
        if not self.allow_read:
            logger.error(f"Unauthorized read access in property-wrapper for {self.prop.fullname()}!")
            return iter([])
        return (child.fullname() for _, child in self.prop.children.items())



class ContextWrapper:
    """
    Encapsulates a context towards a state, only offering properties with permissions
    as declared by the state beforehand.
    """

    def __init__(self, ctx: icontext.IContext, st: state.State):
        self.st = st
        self.ctx = ctx
        self.properties = dict()
        # Recursively complete properties dict with children:
        for propname in st.write_props+st.read_props:
            # May have been covered by a parent before
            if propname not in self.properties:
                prop_and_children = ctx.get_prop(propname).gather_children()
                for prop in prop_and_children:
                    # Child may have been covered by a parent before
                    if prop.fullname() not in self.properties:
                        self.properties[prop.fullname()] = PropertyWrapper(
                            prop=prop, ctx=ctx,
                            allow_read=propname in st.read_props,
                            allow_write=propname in st.write_props)

    def __setitem__(self, key, value):
        if key in self.properties:
            return self.properties[key].set(value)
        else:
            logger.error(f"State {self.st.name} attempted to write property {key} without permission!")

    def __getitem__(self, key) -> Any:
        if key in self.properties:
            return self.properties[key].get()
        else:
            logger.error(f"State {self.st.name}` attempted to access property {key} without permission!")

    def add_state(self, st: state.State):
        self.ctx.add_state(st=st)

    def shutdown(self):
        self.ctx.shutdown()

    def shutting_down(self):
        return self.ctx.shutting_down()

    def conf(self, *, mod=None, key=None):
        if not mod:
            mod = self.st.module_name
        return self.ctx.conf(mod=mod, key=key)

    def push(self, parentpath: str, child: PropertyBase):
        """
        Add a child to a property.
         Note: Child must not yet have a parent or children of itself.
          Write-access to parent is needed.
        :param parentpath: Path of the parent that should receive the new child.
        :param child: Parent-less, child-less property object to add.
        :return: True if the push was successful, False otherwise
        """
        if child.parent_path:
            logger.error(f"State {self.st.name} attempted to push child property {child.name} to parent {parentpath}, but it already has parent {child.parentpath}!")
            return False
        if parentpath in self.properties:
            if self.properties[parentpath].push(child):
                self.properties[child.fullname()] = PropertyWrapper(
                    prop=child, ctx=self.ctx,
                    allow_read=self.properties[parentpath].allow_read,
                    allow_write=self.properties[parentpath].allow_write)
                return True
        else:
            logger.error(f'State {self.st.name} attempted to add child-property {child.name} to non-accessible parent {parentpath}!')
            return False

    def pop(self, path: str):
        """
        Delete a property (remove it from context and it's parent).
         Note: Write-access to parent is needed!
        :param path: Path to the property. Must be nested (not root-level)!
        :return: True if the pop was successful, False otherwise
        """
        path_parts = path.split(":")
        if len(path_parts) < 3:
            logger.error("State {self.st.name}: Path to pop is not a nested property: f{path}")
            return False
        parentpath = ":".join(path_parts[:-1])
        if parentpath in self.properties:
            if self.properties[parentpath].pop(path_parts[1]):
                # Remove property from own dict
                del self.properties[path]
                # Also remove the deleted propertie's children
                for childpath in list(self.properties.keys()):
                    if childpath.startswith(path+":"):
                        del self.properties[childpath]
                return True
        else:
            logger.error(f'State {self.st.name} attempted to remove child-property {path} from non-existent parent-property {parentpath}')
            return False

    def enum(self, path) -> Generator[str, None, None]:
        """
        Enumerate a propertie's children by their full pathes.
        """
        if path in self.properties:
            return self.properties[key].enum()
        else:
            logger.error(f"State {self.st.name} attempted to enumerate property {key} without permission!")

