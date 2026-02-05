# Astract Device Connection class
from abc import ABC, abstractmethod

class AbstractDeviceConnection(ABC):
    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def set_device(self):
        pass

class Device(ABC):
    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

class ReadableDevice(Device):
    @abstractmethod
    def read(self):
        pass

class WritableDevice(Device):
    @abstractmethod
    def write(self):
        pass