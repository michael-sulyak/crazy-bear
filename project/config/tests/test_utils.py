import datetime
import os
import typing

import pytest
from crontab import CronTab

from ..utils import Env


@pytest.mark.parametrize('method, value, expected_result', (
        ('__call__', 'text', 'text',),
        ('__call__', '', '',),
        ('int', '0', 0,),
        ('int', '-35', -35,),
        ('float', '0', 0,),
        ('float', '5.123', 5.123,),
        ('float', '5.123', 5.123,),
        ('bool', 'yes', True,),
        ('bool', 'no', False,),
        ('tuple', '1,2,3', ('1', '2', '3',),),
        ('frozen_set', '1,2,3', {'1', '2', '3'},),
        ('json', '{"a": "b"}', {'a': 'b'},),
        ('time_range', '00:30,10:55', (datetime.time.fromisoformat('00:30'), datetime.time.fromisoformat('10:55'),),),
        ('time_delta', '5 seconds', datetime.timedelta(seconds=5),),
        ('crontab', '1 * * * *', CronTab('1 * * * *'),),
))
def test_env_types(method: str, value: str, expected_result: typing.Any):
    os.environ['TEST'] = value
    assert getattr(Env(), method)('TEST') == expected_result


def test_env_edge_cases():
    env = Env()

    with pytest.raises(KeyError):
        env('test123')

    with pytest.raises(KeyError):
        env._value('test123', value_converter=str)

    assert env._value('test123', default='1', value_converter=str) == '1'

    os.environ['TEST'] = 'test'

    with pytest.raises(ValueError):
        env.bool('TEST')
