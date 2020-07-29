import pytest

from ..state import State


def test_state_get():
    state = State()

    with pytest.raises(KeyError):
        state.get('test')


def test_state_has():
    state = State()

    state.create('test')
    assert state.has('test')


def test_state_set():
    state = State()

    state.create('test')
    state.create('test2')
    state.set('test', 123)

    assert state.get('test') == 123
    assert state.get('test2') is None
