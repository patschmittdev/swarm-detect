from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from types import FunctionType, MethodType

import numpy as np

from swarmtrace.sim.engine import Engine
from swarmtrace.sim.recorder import Recorder
from swarmtrace.trace.io import AgentLabel, Labels
from swarmtrace.world import World


def assert_isolated(policy: object, forbidden_ids: set[int]) -> None:
    """Walk instance data, containers, slots and closures, including cycles."""
    seen = set()

    def visit(value: object, path: str) -> None:
        if id(value) in seen:
            return
        assert id(value) not in forbidden_ids, path
        assert not isinstance(value, (Engine, Recorder, World, AgentLabel, Labels)), path
        if value is not policy:
            assert not callable(getattr(value, "act", None)), path
        seen.add(id(value))
        if value is None or isinstance(value, (str, bytes, bool, int, float, np.generic)):
            return
        if isinstance(value, np.random.Generator):
            visit(value.bit_generator.state, path + ".rng_state")
        elif isinstance(value, np.ndarray):
            visit(value.tolist(), path + ".array")
        elif isinstance(value, Mapping):
            for key, item in value.items():
                visit(key, path + ".key")
                visit(item, path + f"[{key!r}]")
        elif isinstance(value, (tuple, list, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, path + f"[{index}]")
        elif isinstance(value, MethodType):
            visit(value.__self__, path + ".bound_to")
            visit(value.__func__, path + ".function")
        elif isinstance(value, FunctionType):
            visit(value.__defaults__, path + ".defaults")
            visit(value.__kwdefaults__, path + ".kwdefaults")
            for cell in value.__closure__ or ():
                visit(cell.cell_contents, path + ".closure")
        elif is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                visit(getattr(value, field.name), path + "." + field.name)
        else:
            assert hasattr(value, "__dict__") or hasattr(type(value), "__slots__"), path
            for name, item in vars(value).items() if hasattr(value, "__dict__") else ():
                visit(item, path + "." + name)
            for cls in type(value).__mro__:
                slots = getattr(cls, "__slots__", ())
                for name in (slots,) if isinstance(slots, str) else slots:
                    if name not in {"__dict__", "__weakref__"} and hasattr(value, name):
                        visit(getattr(value, name), path + "." + name)

    visit(policy, "policy")
