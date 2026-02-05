import json
from typing import Any, Coroutine, Dict, List, Tuple
from Layout import Layout
from CameraDevice import Camera, CameraDevice
import asyncio


class AsyncServerCommandHandler:
    def __init__(self, layout: Layout | None = None, 
                 reader: asyncio.StreamReader | None = None, 
                 writer: asyncio.StreamWriter | None = None, 
                 device: Camera | None = None) -> None:
        self.layout = layout
        self.reader = reader
        self.writer = writer
        self.device = device
        self.alock = asyncio.Lock()
    
    def __enter__(self) -> None:
        return self
    
    def __exit__(self, exc_type, exc_val, traceback) -> None:
        if self.device is not None:
            self.device.close()
        if self.writer is not None:
            self.writer.close()
    
    def set_layout(self, layout: Layout) -> None:
        self.layout = layout

    def set_reader_writer(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        print('Reader and Writer have been attached to this handler...')
    
    def set_device(self, device: Camera | CameraDevice) -> None:
        self.device = device
        print('A device has been attached to this handler...')
        if isinstance(device, CameraDevice):
            self.device.start_preview()
    
    async def capture_image(self, fname: str = ''):
        assert isinstance(self.device, CameraDevice)
        await asyncio.sleep(2)
        img = self.device.read(fname, nt=64)
        await asyncio.sleep(2)
        return img

    async def send_command(self, command: dict[str, Any], return_data: bool = False):
        command['return_data'] = return_data
        print(f'Printing command in ASCH {command}')
        async with self.alock:
            json_str: str = json.dumps(command)
            assert self.writer is not None

            self.writer.write(json_str.encode('utf-8'))
            await self.writer.drain()
            print('Waiting for response...', end='\n')
            if return_data:
                message_size_bytes: bytes = await self.reader.readuntil(b'\n')
                #print('Message 1 ', message_size_bytes)
                message_size_str = message_size_bytes.decode('utf-8')
                print(message_size_str, type(message_size_str))
                message_size: int = (json.loads(str(message_size_str)))['size']
                assert isinstance(message_size, int)
                #print('Message 2 ', message_size)
                message_bytes: bytes = await self.reader.readuntil(b'\n')
                #print('Message 3 ', message_bytes)
                message_obj: Dict[str, Any] = (json.loads(message_bytes.decode('utf-8')))['return']
                #print('Message 4 ', message_obj)
                return message_obj
            else:
                await self.reader.read(1024)
        return

    def print_message(self, msg: str) -> None:
        print(msg)

    def get_location(self, slot: int, well_name: str, 
                     position: str | None = None, 
                     x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Dict[str, int | str | Tuple[float] | None]:
        if isinstance(position, str):
            if position.lower() not in ['bottom', 'center', 'top']:
                raise ValueError
            return {'slot': slot,
                    'well_name': well_name.upper(),
                    'position': position.lower(),
                    'offset': (x, y, z)}
        return {'slot': slot,
                'well_name': well_name.upper(),
                'position': None,
                'offset': (x, y, z)}
    
    async def establish_client_connection(self) -> None:
        async def establish_connection() -> Coroutine[Any, Any, None]:
            async with self.alock:
                response = await self.reader.read(1024)
                print(response.decode('utf-8'))
                await self.writer.drain()
        await establish_connection()
    
    async def set_deck_layout(self, layout_params: Dict[int | str, Any]) -> None:
        command = {'CMD': 'SET_DECK_LAYOUT',
                   'kwargs': layout_params}
        print(command)
        await self.send_command(command)
    
    async def get_well_names_from_labwares(self, order: str | Dict[str, str] = 'default'):
        if isinstance(order, str):
            if order.lower() not in ['default', 'by_rows', 'by_columns']:
                raise ValueError
        cmd = {'CMD': 'GET_WELL_NAMES',
               'kwargs': {'ORDER': order}}
        return await self.send_command(cmd, return_data=True)

    async def air_gap(self, instrument: str, volume: float | None = None, height: float | None = None) -> None:
        command = {'CMD': 'AIR_GAP',
                   'kwargs': {'instrument': instrument.lower(), 
                              'volume': volume,
                              'height': height
                              }
                    }
        await self.send_command(command)

    async def move_to(self, instrument: str, 
                      slot: int | None = None, well_name: str | None = None, 
                      position: str | None = None, 
                      x: float = 0.0, y: float = 0.0, z: float = 0.0, 
                      force_direct: bool = False, minimum_z_height: float | None = None,
                      speed: float | None = None, publish: bool = True
                      ) -> None:
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        location = self.get_location(slot, well_name, position, x, y, z)
        
        command = {'CMD': 'MOVE_TO',
                   'kwargs': {'instrument': instrument.lower(), 
                              'location': location, 
                              'force_direct': force_direct,
                              'minimum_z_height': minimum_z_height, 
                              'speed': speed, 
                              'publish': publish
                              }
                    }
        await self.send_command(command)

    async def transfer(self, instrument: str, volume: float | List[float], 
                       source: str | List[str], dest: str | List[str],
                       new_tip: str = 'Once', trash: bool = True, 
                       touch_tip: bool = False, blow_out: bool = False,
                       blowout_location: str = '', mix_before: Tuple[int, float] = (0, 0.0),
                       mix_after: Tuple[int, float] = (0, 0.0), disposal_volume: float | None = None
                       ) -> None:
        #self.tip_tracker.use_tip(instrument, 'A1')
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if blow_out and (blowout_location != ''):
            if blowout_location.lower() not in ['trash', 'source_well', 'destination_well']:
                raise ValueError
        
        command = {'CMD': 'TRANSFER',
                   'kwargs': {'instrument': instrument.lower(), 
                              'volume': volume, 
                              'source': source, 
                              'dest': dest, 
                              'new_tip': new_tip,
                              'trash': trash, 
                              'touch_tip': touch_tip, 
                              'blow_out': blow_out, 
                              'blowout_location': blowout_location.lower(),
                              'mix_before': mix_before,
                              'mix_after': mix_after,
                              'disposal_volume': disposal_volume
                              }
                    }
        await self.send_command(command)
    
    async def distribute(self, instrument: str, volume: float | List[float], 
                         source: str, dest: List[str], 
                         new_tip: str = 'Once', trash: bool = True, 
                         touch_tip: bool = False, blow_out: bool = False,
                         blowout_location: str = '', mix_before: Tuple[int, float] = (0, 0.0),
                         mix_after: Tuple[int, float] = (0, 0.0), disposal_volume: float | None = None) -> None:
        #self.tip_tracker.use_tip(instrument, 'A1')
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if blow_out and (blowout_location != ''):
            if blowout_location.lower() not in ['trash', 'source_well', 'destination_well']:
                raise ValueError
        
        command = {'CMD': 'DISTRIBUTE',
                   'kwargs': {'instrument': instrument.lower(), 
                              'volume': volume, 
                              'source': source, 
                              'dest': dest, 
                              'new_tip': new_tip,
                              'trash': trash, 
                              'touch_tip': touch_tip, 
                              'blow_out': blow_out, 
                              'blowout_location': blowout_location.lower(),
                              'mix_before': mix_before,
                              'mix_after': mix_after,
                              'disposal_volume': disposal_volume
                              }
                    }
        await self.send_command(command)

    async def consolidate(self, instrument: str, volume: float | List[float], 
                          source: List[str], dest: str, 
                          new_tip: str = 'Once', trash: bool = True, 
                          touch_tip: bool = False, blow_out: bool = False,
                          blowout_location: str = '', mix_before: Tuple[int, float] = (0, 0.0),
                          mix_after: Tuple[int, float] = (0, 0.0), disposal_volume: float | None = None) -> None:
        #self.tip_tracker.use_tip(instrument, 'A1')
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if blow_out and (blowout_location != ''):
            if blowout_location.lower() not in ['trash', 'source_well', 'destination_well']:
                raise ValueError
        
        command = {'CMD': 'CONSOLIDATE',
                   'kwargs': {'instrument': instrument.lower(), 
                              'volume': volume, 
                              'source': source, 
                              'dest': dest, 
                              'new_tip': new_tip,
                              'trash': trash, 
                              'touch_tip': touch_tip, 
                              'blow_out': blow_out, 
                              'blowout_location': blowout_location.lower(),
                              'mix_before': mix_before,
                              'mix_after': mix_after,
                              'disposal_volume': disposal_volume
                              }
                    }
        await self.send_command(command)
    
    async def aspirate(self, instrument: str, volume: float, 
                       slot: int | None = None, well_name: str | None = None, 
                       position: str | None = None, 
                       x: float = 0.0, y: float = 0.0, z: float = 0.0, 
                       rate: float = 1.0) -> None:
        #self.tip_tracker.use_tip(instrument, 'A1')
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if (slot is None) or (well_name is None):
            location = None
        else:
            location = self.get_location(slot, well_name, position, x, y, z)
        
        command = {'CMD': 'ASPIRATE',
                   'kwargs': {'instrument': instrument.lower(), 
                              'volume': volume, 
                              'location': location, 
                              'rate': rate
                              }
                   }
        await self.send_command(command)
    
    async def dispense(self, instrument: str, volume: float | None, 
                       slot: int | None = None, well_name: str | None = None, 
                       position: str | None = None, 
                       x: float = 0.0, y: float = 0.0, z: float = 0.0, 
                       rate: float = 1.0, push_out: bool | None = None) -> None:
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if (slot is None) or (well_name is None):
            location = None
        else:
            location = self.get_location(slot, well_name, position, x, y, z)
        
        command = {'CMD': 'DISPENSE',
                   'kwargs': {'instrument': instrument.lower(), 
                              'volume': volume, 
                              'location': location, 
                              'rate': rate, 
                              'push_out': push_out}
                   }
        await self.send_command(command)

    async def mix(self, instrument: str, repetitions: int = 1, volume: float | None = None, 
                  slot: int | None = None, well_name: str | None = None, 
                  position: str | None = None, 
                  x: float = 0.0, y: float = 0.0, z: float = 0.0, 
                  rate: float = 1.0) -> None:
        # location can be of type Location or Well
        if instrument.lower() not in ['left', 'right']:
            raise ValueError
        
        if (slot is None) or (well_name is None):
            location = None
        else:
            location = self.get_location(slot, well_name, position, x, y, z)

        command = {'CMD': 'MIX',
                   'kwargs': {'instrument': instrument.lower(),
                              'repetitions': repetitions,
                              'volume': volume, 
                              'location': location, 
                              'rate': rate}
                   }
        await self.send_command(command)
    
    async def pick_up_tip(self, instrument: str, 
                          slot: int | None = None, well_name: str | None = None, 
                          position: str | None = None, 
                          x: float = 0.0, y: float = 0.0, z: float = 0.0, 
                          presses: int | None = None, increment: float | None = None
                          ):
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if (slot is None) or (well_name is None):
            location = None
        else:
            location = self.get_location(slot, well_name, position, x, y, z)
        
        command = {'CMD': 'PICK_UP_TIP',
                   'kwargs': {'instrument': instrument.lower(), 
                              'location': location, 
                              'presses': presses,
                              'increment': increment
                              }
                    }
        await self.send_command(command)

    async def drop_tip(self, instrument: str, 
                       slot: int | None = None, well_name: str | None = None, 
                       position: str | None = None, 
                       x: float = 0.0, y: float = 0.0, z: float = 0.0, 
                       home_after: bool = True):
        if instrument.lower() not in ['left', 'right']:
            raise ValueError

        if (slot is None) or (well_name is None):
            location = None
        else:
            location = self.get_location(slot, well_name, position, x, y, z)

        command = {'CMD': 'DROP_TIP',
                   'kwargs': {'instrument': instrument.lower(), 
                              'location': location,
                              'home_after': home_after
                              }
                    }
        await self.send_command(command)
    
    async def get_min_max_volume(self, instrument: str):
        if instrument.lower() not in ['left', 'right']:
            raise ValueError
        command = {'CMD': 'GET_MIN_MAX_VOLUME',
                   'kwargs': {'instrument': instrument.lower()
                              }
                    }
        return tuple(await self.send_command(command, return_data=True))

    async def new_tip(self, instrument: str):
        if self.tip_status[instrument]:
            await self.drop_tip(instrument)
        await self.pick_up_tip(instrument)
    
    def is_clean(self, instrument: str) -> bool:
        return self.tip_tracker.is_clean(instrument)
    
