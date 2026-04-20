from enum import Enum


class LogMethod(str, Enum):
    TEXT = "TEXT"
    VOICE = "VOICE"
    CAMERA = "CAMERA"
