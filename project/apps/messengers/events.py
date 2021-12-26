from ..common.events import Event


input_command = Event(providing_kwargs=('command',))
new_message = Event(providing_kwargs=('message',))
