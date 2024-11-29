from ..common.events import Event


motion_detected = Event(providing_kwargs=('source',))
new_arduino_data = Event(providing_kwargs=('signals',))
security_is_enabled = Event()
security_is_disabled = Event()
user_is_connected_to_router = Event()
user_is_disconnected_to_router = Event()
user_is_at_home = Event()
user_is_not_at_home = Event()
shutdown = Event()
request_for_statistics = Event(
    providing_kwargs=(
        'date_range',
        'components',
    )
)
frame_from_video_camera = Event(
    providing_kwargs=(
        'frame',
        'fps',
    )
)
getting_doc = Event()
input_command = Event(providing_kwargs=('command',))
new_message = Event(providing_kwargs=('message',))
