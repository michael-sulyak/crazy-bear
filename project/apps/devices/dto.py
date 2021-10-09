import typing
from dataclasses import dataclass


@dataclass
class Device:
    mac_address: str
    name: typing.Optional[str] = None
    is_defining: bool = False

    @classmethod
    def from_dict(cls, data: typing.Dict[str, typing.Any]) -> 'Device':
        return cls(**data)

    def to_dict(self) -> typing.Dict[str, typing.Any]:
        return {
            'mac_address': self.mac_address,
            'name': self.name,
            'is_defining': self.is_defining,
        }
