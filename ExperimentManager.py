from abc import ABC, abstractmethod
from typing import Any, Callable, List, Dict, Generator, Tuple
from pickle import dumps, loads
from datetime import datetime
import math
import cv2
import numpy as np
import json
from multiprocessing import Event
from multiprocessing.connection import Connection

from AsyncServerCommandHandler import AsyncServerCommandHandler
from DBInterface import DBInterface as dbi
#import paho.mqtt as mqtt

import asyncio

#Experiment
class Experiment(ABC):
    def __init__(self, profile: Dict[str, List[int]] | None = None, usages: Dict[str, int] | None = None, 
    #num_replicates: int = 3
    ) -> None:
        self.set_labware_profile(profile)
        self.set_labware_usage(usages)
        #self.set_num_replicates(num_replicates)
        self.counter = 1

    def increment_counter(self) -> None:
        self.counter += 1
    
    def get_counter(self) -> int:
        return self.counter
    
    def set_output_dir(self, dir_name: str) -> None:
        self.output_dir = dir_name

    def get_output_dir(self) -> str:
        return self.output_dir
    
    def set_num_replicates(self, num_replicates: int = 3) -> None:
        self.num_replicates = num_replicates
    
    def set_labware_profile(self, profile: Dict[str, List[int]]) -> None:
        self.labware_profile = profile
    
    def set_liquid_locations(self, liquid_locations: Dict[str, str]) -> None:
        self.liquid_locations = liquid_locations
    
    def set_database_interface(self, database_interface: dbi) -> None:
        self.database_interface = database_interface

    def get_labware_profile(self) -> Dict[str, List[int]]:
        return self.labware_profile
    
    def set_labware_usage(self, usages: Dict[str, int]) -> None:
        self.labware_usage = usages
    
    def get_well_usage(self) -> Dict[str, int]:
        return self.labware_usage
    
    def set_well_allocations(self, wells: Dict[str, List[str]]) -> None:
        self.well_allocations = wells
    
    def set_experiment_parameters(self, params: Dict[str, float]) -> None:
        self.parameters = params
    
    def get_experiment_parameters(self) -> Dict[str, float]:
        return self.parameters
    
    def set_target_concentration(self, params: Dict[str, float]) -> None:
        self.target_concentration = params
    
    def get_target_concentration(self) -> Dict[str, float]:
        return self.target_concentration
    
    def parse_well_name_string(self, well_name: str) -> Tuple[int, str]:
        arg1, arg2 = well_name.split('-')
        return int(arg1), arg2.upper()
    
    @abstractmethod
    async def run(self, command_handler: AsyncServerCommandHandler, 
                  allocated_wells: Dict[str, List[str]], 
                  #queue: asyncio.Queue,
                  connection: Connection) -> None:
        pass



#Experiment Manager
class ExperimentManager:
    '''
    Responsibilities:
    * Store Experiment object
    * Keep track of experiment consumable/resource usage
    * Allocate resources for experiments
    '''
    def __init__(self, command_handler: AsyncServerCommandHandler | None = None, 
                 database_interface: dbi | None = None
                 ) -> None:
        self.command_handler = command_handler
        self.database_interface = database_interface
        self.experiment_running: bool = False

    async def set_experiment_profile(self) -> None:
        pass
    
    def start_experiment(self) -> None:
        self.experiment_running = True

    def stop_experiment(self) -> None:
        self.experiment_running = False
    
    def is_running_experiment(self) -> bool:
        return self.experiment_running

    def set_experiment(self, experiment: Experiment) -> None:
        self.experiment: Experiment = experiment
    
    async def set_deck_layout(self, fname: str) -> None:
        with open(fname, mode='r') as fd:
            layout_dict: Dict[int | str, Any] = json.load(fd)
        
        print(f'Printing Layout in EM {layout_dict}')
        await self.command_handler.set_deck_layout(layout_dict)
    
    async def set_labware_wells(self, labware_group_dict: Dict[str, List[int]], 
                                order: str | Dict[str, str] = 'default',
                                subset: Dict[str, List[str]] | None = None):
        if isinstance(order, str):
            well_names: Dict[str, List[str]] = await self.command_handler.get_well_names_from_labwares(order)
        else:
            new_order: Dict[int, str] = {}
            for k, v in order.items():
                new_k = labware_group_dict[k]
                if isinstance(new_k, int):
                    new_order[new_k] = v
                else:
                    for i in new_k:
                        new_order[i] = v
            well_names: Dict[str, List[str]] = await self.command_handler.get_well_names_from_labwares(new_order)
        
        self.labware_wells: Dict[str, List[str]] = {}
        assert 'LEFT' in labware_group_dict.keys()
        assert 'RIGHT' in labware_group_dict.keys()
        for labware_group, deck_slots in labware_group_dict.items():
            print(labware_group, deck_slots)
            assert isinstance(deck_slots, list)
            
            if deck_slots == []:
                self.labware_wells[labware_group] = []
            else:
                combined_well_list: List[str] = []
                for i in deck_slots:
                    #print(i, type(i))
                    combined_well_list.extend(well_names[str(i)])
                self.labware_wells[labware_group] = combined_well_list
            
            if subset is not None:
                if labware_group in subset.keys():
                    self.labware_wells[labware_group] = subset[labware_group]
        
        return
    
    def set_target_concentration(self, params: Dict[str, float]) -> None:
        self.experiment.set_target_concentration(params)
    
    def get_target_concentration(self) -> Dict[str, float]:
        return self.experiment.get_experiment_parameters()

    def well_generator(self, well_lst: List[str]) -> Generator[str, None, None]:
        for well_str in well_lst:
            yield well_str

    def track_labware_wells(self):
        self.well_allocator = {}
        for labware_group, well_lst in self.labware_wells.items():
            if well_lst != []:
                self.well_allocator[labware_group] = self.well_generator(well_lst)
    
    def allocate_wells(self, well_generator: Generator[str, None, None], num_wells: int) -> None:
        assert num_wells >= 0
        try:
            return [next(well_generator) for _ in range(num_wells)]
        except StopIteration as err:
            return err
    
    def set_experiment_parameters(self, params: Dict[str, float]) -> None:
        self.experiment.set_experiment_parameters(params=params)
    
    def get_experiment_parameters(self) -> Dict[str, float]:
        return self.experiment.get_experiment_parameters()

    async def set_min_max_pipette_volumes(self) -> None:
        self.volume_limits = {}
        for instrument in ['LEFT', 'RIGHT']:
            self.volume_limits[instrument] = await self.command_handler.get_min_max_volume(instrument)
            print(f'{instrument} pipette: {self.volume_limits[instrument][0]}uL - {self.volume_limits[instrument][1]}uL')
    
    def get_min_max_pipette_volumes(self) -> Dict[str, Tuple[float, float]]:
        return self.volume_limits
    
    def set_labware_usage_template(self, labware_usage_template: Dict[str, int | Callable[[int], int]]) -> None:
        self.labware_usage_template = labware_usage_template
    
    def get_labware_usage_template(self) -> Dict[str, int | Callable[[int], int]]:
        return self.labware_usage_template
    
    def get_pipette_usage(self, ignore_left: bool = False, ignore_right: bool = False) -> Dict[str, int]:
        experiment_parameters: Dict[str, float] = self.get_experiment_parameters()
        pipette_volume_limits: Dict[str, Tuple[float, float]] = self.get_min_max_pipette_volumes()
        left_min, left_max = pipette_volume_limits['LEFT']
        right_min, right_max = pipette_volume_limits['RIGHT']
        left_counter = 0
        right_counter = 0

        if (ignore_left ^ ignore_right):
            if ignore_left:
                for volume in experiment_parameters.values():
                    right_counter += math.ceil(volume / right_max)
            else:
                for volume in experiment_parameters.values():
                    left_counter += math.ceil(volume / left_max)
        else:
            for volume in experiment_parameters.values():
                if  volume <= left_max: #left_min <= volume <= left_max:
                    left_counter += 1
                elif volume <= right_max: #right_min <= volume <= right_max:
                    right_counter += 1
                else:
                    raise ValueError
        
        pipette_counter = {'LEFT': left_counter, 'RIGHT': right_counter}
        print(pipette_counter)
        return pipette_counter

    def set_labware_usage(self, counter: Dict[str, int]) -> None:
        lw_usage_copy = dict(self.get_labware_usage_template())
        for group, num in lw_usage_copy.items():
            if (group in counter.keys()) and (not isinstance(num, int)):
                func: Callable[[int], int] = lw_usage_copy[group]
                lw_usage_copy[group] = func(counter[group])
        print(lw_usage_copy)
        self.experiment.set_labware_usage(lw_usage_copy)
    
    async def allocate_wells_for_new_experiment(self) -> Dict[str, List[str]]:
        pipette_counter: Dict[str, int] = self.get_pipette_usage()

        self.set_labware_usage(pipette_counter)

        dict : Dict[str, List[str]] = {}
        experiment_wells_usage = self.experiment.get_well_usage()
        for labware_group, well_generator in self.well_allocator.items():
            num_wells = experiment_wells_usage[labware_group]
            result = self.allocate_wells(well_generator, num_wells)
            if isinstance(result, StopIteration):
                # Alert user to refill labwares before experiment can begin
                labware_profile = self.experiment.get_labware_profile()
                self.refill_labwares(labware_group, labware_profile[labware_group])
                if labware_group == 'dest_wells':
                    self.experiment.increment_counter()
                # Update well generator in well allocator
                new_well_generator = self.well_generator(self.labware_wells[labware_group])
                self.well_allocator[labware_group] = new_well_generator
                result = self.allocate_wells(new_well_generator, num_wells)
            dict[labware_group] = result
        return dict

    def refill_labwares(self, labware_group: str, deck_slots: List[int] | None = None):
        if deck_slots is None:
            prompt_message = f"Please refill/replace labware(s) \'{labware_group}\'. Continue [Enter]?"
        else:
            prompt_message = f"Please refill/replace labware(s) \'{labware_group}\' at slots {deck_slots}. Continue [Enter]?"
        input(prompt_message)

    async def main_loop(self):
        pass


     