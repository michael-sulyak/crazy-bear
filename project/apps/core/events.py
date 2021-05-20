from ..common.events import Event


motion_detected = Event()
new_arduino_logs = Event(providing_kwargs=('arduino_logs ',))
# security_is_enabled = Event()
# security_is_disabled = Event()
user_is_connected_to_router = Event()
user_is_disconnected_to_router = Event()
shutdown = Event()
tick = Event()
request_for_statistics = Event(providing_kwargs=('date_range', 'components',))
