from ExperimentManager import Experiment
from typing import Any, Callable, List, Dict, Generator, Tuple
from datetime import datetime
import asyncio
import numpy as np
import json
from multiprocessing.connection import Connection

from AsyncServerCommandHandler import AsyncServerCommandHandler
from ContactAngleAnalyzer import raise_precheck

#ContactAngleMeasurementExperiment
class ContactAngleMeasurementExperiment(Experiment):
    METADATA_TEMPLATE = {'DATE': None,
                         'DECK_LOCATION': None,
                         'DATA_FILEPATH': None}
    def __init__(self, profile: Dict[str, List[int]] | None = None, usages: Dict[str, int] | None = None) -> None:
        super().__init__(profile, usages)
        self.ignore_pipette(left=False, right=False)
    
    def ignore_pipette(self, left: bool = False, right: bool = False):
        self.ignore_left = left
        self.ignore_right = right
    
    def set_liquid_locations(self, liquids: Dict[str, str]) -> None:
        self.liquids = liquids
    
    def get_liquid_location(self, liquid: Tuple[str, float]) -> str:
        liquid_name, conc = liquid
        return self.liquids[liquid_name][conc]
    
    def get_experiment_parameters(self, name: str| None = None) -> float | Dict[str, float]:
        if isinstance(name, str):
            return self.parameters[name]
        else:
            return self.parameters

    def get_experiment_metadata(self): 
        pass

    def well_generator(self, well_lst: List[str]) -> Generator[str, None, None]:
        for well_str in well_lst:
            yield well_str

    def get_z_offset(self, well_name: str, increment: float, z_additional: float = 0.0) -> float:
        # mx+b
        x: int = -1
        name: str = well_name.upper()
        if 'A' in name:
            x = 0
        elif 'B' in name:
            x = 1
        elif 'C' in name:
            x = 2
        elif 'D' in name:
            x = 3
        elif 'E' in name:
            x = 4
        elif 'F' in name:
            x = 5    
        else:
            raise ValueError
        
        return increment * x + z_additional
    
    
    async def run(self, command_handler: AsyncServerCommandHandler, 
                  allocated_wells: Dict[str, List[str]], 
                  connection: Connection) -> None:
        lw_usage = self.get_well_usage()
        for k in lw_usage.keys():
            assert lw_usage[k] == len(allocated_wells[k])

        # Create a variable to keep track of allocated wells/tips/space
        resource_tracker = {lw_group: self.well_generator(wells) for (lw_group, wells) in allocated_wells.items()}

        # Drop previous tip attached to P20 pipette used to transfer liquid onto stage.
        for pipette in ['left']:
            await command_handler.drop_tip(pipette)
        
        # Get mixing well
        mixing_well_1: str = next(resource_tracker['mixing_wells'])

        # Get target formulation
        print(f'Target Concentration: {self.get_target_concentration()} {type(self.get_target_concentration())}')
        experiment_parameters: Dict[Tuple[str, str], float] = self.get_experiment_parameters()
        
        # Temporary hard-code maximum pipette volumes.
        # REPLACE THIS LATER!!!
        LEFT_MAX: float = 20.0
        #RIGHT_MAX: float = 1000.0

        # Transfer liquid from stock solutions to the mixing well to mix reagents together
        for i, (liquid_name, volume) in enumerate(experiment_parameters.items(), start=1):
            PIPETTE_NAME: str = ''
            if volume <= LEFT_MAX:
                PIPETTE_NAME = 'LEFT'
            else:
                PIPETTE_NAME = 'RIGHT'

            print('Pick up 20uL Tip')
            pipette_tip: str = next(resource_tracker[PIPETTE_NAME])
            slot, well_name = self.parse_well_name_string(pipette_tip)
            await command_handler.pick_up_tip(PIPETTE_NAME, slot=slot, well_name=well_name)

            print('Transfer surfactant and mix')
            source: str = self.get_liquid_location(liquid_name)

            await command_handler.transfer(PIPETTE_NAME, volume=volume, source=source, dest=mixing_well_1, 
                                           new_tip='never')
            
            print('Drop Left and Right tips')
            await command_handler.drop_tip(PIPETTE_NAME)
        
        
        mixing_slot, mixing_well_name = self.parse_well_name_string(mixing_well_1)
        
        # Pick up new tip to mix solution
        print('Mixing')
        pipette_tip: str = next(resource_tracker['RIGHT'])
        slot, well_name = self.parse_well_name_string(pipette_tip)
        await command_handler.pick_up_tip('right', slot=slot, well_name=well_name)
        #await command_handler.move_to('right', slot=mixing_slot, well_name=mixing_well_name, position='bottom', z=1)
        await command_handler.mix('right', repetitions=10, volume=100, 
                                  slot=mixing_slot, well_name=mixing_well_name, z=0.5, 
                                  rate=2.0)
        await command_handler.drop_tip('right')
        
        
        # Pick up new 20uL tip to transfer liquid from mixing well to stage
        print('Pick up 20uL Tip')
        left_tip_2: str = next(resource_tracker['LEFT'])
        slot, well_name = self.parse_well_name_string(left_tip_2)
        await command_handler.pick_up_tip('left', slot=slot, well_name=well_name)

        # Pick up camera tool with other pipette
        await command_handler.pick_up_tip('right', slot=10, well_name='A1')

        # Pick up camera
        print('Pick up Camera')
        print('Transfer solution to stage')
        
        # Perform replicate static contact angle measurement experiments
        # depending on how many dest_wells are allocated.
        for dest_well in allocated_wells['dest_wells']:
            # Aspirate
            await command_handler.aspirate('left', volume=3.5, slot=mixing_slot, well_name=mixing_well_name, 
                                      position='bottom', z=1)
            # Dispense
            dest_slot, dest_well_name = self.parse_well_name_string(dest_well)

            m_left: float = 20.5 # z_offset = mx + b
            b_left: float = 22.0
            await command_handler.dispense('left', volume=3.0, slot=dest_slot, well_name=dest_well_name, 
                                           position='bottom', z=self.get_z_offset(dest_well_name, m_left, b_left + 2.5), 
                                           rate=4/5)

            # move to lower drop (~2mm) (slow speed)
            await command_handler.move_to('left', slot=dest_slot, well_name=dest_well_name, 
                                           position='bottom', z=self.get_z_offset(dest_well_name, m_left, b_left), 
                                           force_direct=True, speed=2/5)
            
            
            
            # move to camera offset
            x_offset: float = 0.0
            y_offset: float = 67.5 #66
            m_right: float = 10.25
            b_right: float = 4.5 #5.5
            z_offset: float = self.get_z_offset(dest_well_name, m_right, b_right)
            await command_handler.move_to('right', slot=dest_slot, well_name=dest_well_name, 
                                           position='bottom', x=x_offset, y=y_offset, z=z_offset, 
                                           speed=50)
            
            # take picture
            await asyncio.sleep(10)
            fname: str = f'{self.get_output_dir()}{dest_slot}-{dest_well_name}-{self.get_counter()}.jpg'
            img: np.ndarray = await command_handler.capture_image(fname=fname)

            if not raise_precheck(img):
                # move to lower drop (~3.5mm) (slow speed)
                b_left: float = 20.0
                await command_handler.move_to('left', slot=dest_slot, well_name=dest_well_name, 
                                              position='bottom', z=self.get_z_offset(dest_well_name, m_left, b_left + 2), 
                                              speed=50)
                # move to lower drop (~1.5mm) (slow speed)
                await command_handler.move_to('left', slot=dest_slot, well_name=dest_well_name, 
                                              position='bottom', z=self.get_z_offset(dest_well_name, m_left, b_left), 
                                              force_direct=True, speed=2/5)
                
                await command_handler.move_to('right', slot=dest_slot, well_name=dest_well_name, 
                                              position='bottom', x=x_offset, y=y_offset, z=z_offset, 
                                              speed=50)

                # take picture
                await asyncio.sleep(5)
                img: np.ndarray = await command_handler.capture_image(fname=fname)
            
            # If there is a connection to a database, upload image metadata
            entry_id = np.nan
            if self.database_interface is not None:
                entry_id = self.database_interface.write_metadata_to_db(slot_num=dest_slot, 
                                                                        well_name=dest_well_name, 
                                                                        timepoint='0_mins',
                                                                        img_height=img.shape[0], 
                                                                        img_width=img.shape[1], 
                                                                        fname=fname,
                                                                        formulation=experiment_parameters,
                                                                        datetime=datetime.now())
            
            # Send information about the experiment to the contact angle analyzer 
            # to measure static contact angle of the captured image.
            experiment_parameters_cpy = dict()
            for k, v in experiment_parameters.items():
                liquid_name, concentration = k
                experiment_parameters_cpy[f'{liquid_name}_{concentration}'] = v
            
            connection.send((fname, 
                             dest_slot, 
                             dest_well_name, 
                             self.get_counter(), 
                             entry_id, 
                             json.dumps(self.get_target_concentration()), 
                             json.dumps(experiment_parameters_cpy)))

        # Return camera tool
        await command_handler.drop_tip('right', slot=10, well_name='A1', position='bottom', z=5)
        
        # Sleep for 3 secs
        await asyncio.sleep(3)
        return