from unittest.mock import Mock

import pytest

from ..state import State


def test_state_get():
    state = State()

    with pytest.raises(KeyError):
        state.get('test')

    with pytest.raises(KeyError):
        state['test']


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
    assert state['test'] == 123
    assert state.get('test2') is None
    assert state['test2'] is None


def test_state_subscribe_toggle():
    state = State()

    f1 = Mock()
    f2 = Mock()
    f3 = Mock()

    state.create('TEST', None)
    state.subscribe_toggle('TEST', {
        (None, True,): f1,
        (False, True,): f2,
        (True, False,): f3,
    })

    f1.assert_not_called()
    f2.assert_not_called()
    f3.assert_not_called()

    state['TEST'] = True
    f1.assert_called_once()
    f2.assert_not_called()
    f3.assert_not_called()

    state['TEST'] = False
    f1.assert_called_once()
    f2.assert_not_called()
    f3.assert_called_once()

    state['TEST'] = True
    f1.assert_called_once()
    f2.assert_called_once()
    f3.assert_called_once()

