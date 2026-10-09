"""Small, type-indexed entity-component-system primitives."""

from collections.abc import Iterator
from typing import Any, TypeVar

Entity = int
Component = TypeVar("Component")


class World:
    """Store entities and their components."""

    def __init__(self) -> None:
        self._next_entity: Entity = 0
        self._alive: set[Entity] = set()
        self._components: dict[type[object], dict[Entity, object]] = {}

    def create(self) -> Entity:
        """Create and return a new entity identifier."""
        entity = self._next_entity
        self._next_entity += 1
        self._alive.add(entity)
        return entity

    def destroy(self, entity: Entity) -> None:
        """Destroy an entity and remove all of its components."""
        self._require_entity(entity)
        self._alive.remove(entity)
        for components in self._components.values():
            components.pop(entity, None)

    def add(self, entity: Entity, component: Component) -> Component:
        """Add a component instance to an entity."""
        self._require_entity(entity)
        component_type = type(component)
        components = self._components.setdefault(component_type, {})
        if entity in components:
            raise ValueError(
                f"Entity {entity} already has a {component_type.__name__} component"
            )
        components[entity] = component
        return component

    def get(self, entity: Entity, component_type: type[Component]) -> Component:
        """Return an entity's component of the requested type."""
        self._require_entity(entity)
        components = self._components.get(component_type, {})
        try:
            component = components[entity]
        except KeyError as error:
            raise KeyError(
                f"Entity {entity} has no {component_type.__name__} component"
            ) from error
        return component  # type: ignore[return-value]

    def remove(self, entity: Entity, component_type: type[Component]) -> Component:
        """Remove and return an entity's component of the requested type."""
        self._require_entity(entity)
        components = self._components.get(component_type, {})
        try:
            component = components.pop(entity)
        except KeyError as error:
            raise KeyError(
                f"Entity {entity} has no {component_type.__name__} component"
            ) from error
        return component  # type: ignore[return-value]

    def has(self, entity: Entity, component_type: type[object]) -> bool:
        """Return whether an entity has a component of the requested type."""
        self._require_entity(entity)
        return entity in self._components.get(component_type, {})

    def query(self, *component_types: Any) -> Iterator[Any]:
        """Yield matching entities followed by their components.

        Components appear in the same order as ``component_types``. With no
        component types, all entities are returned as one-item tuples.
        """
        if not component_types:
            for entity in sorted(self._alive):
                yield (entity,)
            return

        stores = [
            self._components.get(component_type, {})
            for component_type in component_types
        ]
        candidates = set.intersection(*(set(store) for store in stores))
        for entity in sorted(candidates):
            # The component stores are untyped at runtime, so the unpacked
            # generator is typed as ``object`` even though the stores are
            # keyed by concrete component types.
            yield (entity, *(store[entity] for store in stores))

    def _require_entity(self, entity: Entity) -> None:
        if entity not in self._alive:
            raise KeyError(f"Unknown entity: {entity}")
