from dataclasses import dataclass

import pytest

from sat_sim.ecs import World


@dataclass
class Health:
    value: int


@dataclass
class Name:
    value: str


def test_create_returns_unique_entities() -> None:
    world = World()

    first = world.create()
    second = world.create()

    assert first != second
    assert list(world.query()) == [(first,), (second,)]


def test_component_crud() -> None:
    world = World()
    entity = world.create()
    health = Health(100)

    assert world.add(entity, health) is health
    assert world.has(entity, Health)
    assert world.get(entity, Health) is health
    assert world.remove(entity, Health) is health
    assert not world.has(entity, Health)


def test_query_returns_matching_components_in_requested_order() -> None:
    world = World()
    entity = world.create()
    health = Health(100)
    name = Name("satellite")
    world.add(entity, health)
    world.add(entity, name)

    assert list(world.query(Name, Health)) == [(entity, name, health)]


def test_destroy_removes_entity_and_components() -> None:
    world = World()
    entity = world.create()
    world.add(entity, Health(100))

    world.destroy(entity)

    assert list(world.query()) == []
    with pytest.raises(KeyError, match="Unknown entity"):
        world.get(entity, Health)


def test_invalid_component_operations_raise_clear_errors() -> None:
    world = World()
    entity = world.create()
    world.add(entity, Health(100))

    with pytest.raises(ValueError, match="already has"):
        world.add(entity, Health(50))
    with pytest.raises(KeyError, match="has no Name component"):
        world.get(entity, Name)
    with pytest.raises(KeyError, match="Unknown entity"):
        world.has(999, Health)
