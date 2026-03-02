import socket

class Server():
    """
    A class for instantiating a Server in a server-client relationship.
    
    """
    def __init__(self, name: str|None = None, port: int = 1200) -> None:
        self.name = name
        self.hostname = socket.gethostname()
        self.ip_addr = socket.gethostbyname(self.hostname)
        self.port = port
        self.is_connected = False
        self.socket = None
        print(self)
    
    def __repr__(self) -> str:
        return f'Server Name: {self.name}\nHostname: {self.hostname}\nIP Address: {self.ip_addr}\nPort #: {self.port}\n'
    
    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.ip_addr, self.port))
        self.socket.listen(1)
        self.socket.settimeout(60) # in seconds
    
    def get_socket(self) -> socket.socket:
        return self.socket
    
    def get_device(self):
        if self.device is None:
            print('This server does not have a Device connected to it.')
        return self.device
    
    def __enter__(self):
        self.connect()
        self.is_connected = True
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self.socket.close()
