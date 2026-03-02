# Astract Device Connection class
from abc import ABC, abstractmethod

class AbstractDeviceConnection(ABC):
    """
    An abstract class representing an object
    """
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def set_device(self):
        pass

class Device(ABC):
    """
    An abstract class representing a device for sending/receiving data that can opened and closed.
    """
    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

class ReadableDevice(Device):
    """
    An abstract class representing a device that can read data.
    """
    @abstractmethod
    def read(self):
        pass

class WritableDevice(Device):
    """
    An abstract class representing a device that can write data.
    """
    @abstractmethod
    def write(self):
        pass