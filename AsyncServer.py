# Server Class
from ADC import AbstractDeviceConnection, Device
import socket
from time import time, sleep

class AsyncServer(AbstractDeviceConnection):
    def __init__(self, name: str | None = None, port: int = 1200) -> None:
        self.name = name
        self.hostname = socket.gethostname()
        self.ip_addr = socket.gethostbyname(self.hostname)
        self.port = port
        self.is_connected = False
        self.socket = None
        self.device = None
        print(self)

    def __str__(self) -> str:
        return f'Server Name: {self.name}\nHostname: {self.hostname}\nIP Address: {self.ip_addr}\nPort #: {self.port}\n'

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.ip_addr, self.port))
        self.socket.listen(1)
        self.socket.setblocking(False)  # Set to non-blocking mode

    def get_socket(self) -> socket.socket:
        return self.socket

    def set_device(self, device: Device):
        self.device = device

    async def __aenter__(self):
        self.connect()
        self.is_connected = True
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        if self.socket:
            self.socket.close()
        if self.device:
            self.device.close()


if __name__ == '__main__':
    server = AsyncServer(port=1200)
    
    with server:
        soc = server.get_socket()
        client_socket, client_addr = soc.accept()
        print(f'Client IP Address: {client_addr[0]}')
        #sleep(5)
        '''
        for i, command in  enumerate(TEST_COMMANDS):
            client_socket.send(command.encode('utf-8'))
            msg = client_socket.recv(1024)
            print(msg.decode('utf-8'))
        '''
        # asyncio.run(repeat_simple_routine(client_socket, 5, 60))

