"""Prayer times calculated from the sun's position, as calendar events that protect your salah."""
from .ics import Meeting, clashes, prayer_events, read_meetings, to_ics
from .places import PLACES
from .times import METHODS, PRAYERS, Settings, compute, label

__version__ = "1.0.0"
