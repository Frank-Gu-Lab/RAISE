from ExperimentManager import ExperimentManager, Experiment
from ContactAngleMeasurementExperiment import ContactAngleMeasurementExperiment
from ContactAngleAnalyzer import analyze_data

from typing import Any, Callable, List, Dict, Generator, Tuple
from pickle import dumps, loads
from datetime import datetime
import math
import json
import os
import ssl
import traceback
from multiprocessing import Event, Pipe, Process

from AsyncServerCommandHandler import AsyncServerCommandHandler
from DBInterface import DBInterface as dbi
from json_creator import load_labware_usage_parameters
from Formulation_Creator import *
from BO_Client import bo_main_loop

import aiomqtt
from DBInterface import DBInterface as dbi
from utils.secret_credentials import HOSTNAME, USERNAME, PASSWORD

#Experiment Manager
class ContactAngleMeasurementExperimentManager(ExperimentManager):
    '''
    Experimennt manager class that is responsible for coordinating experimental procedures.
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
        """
        Reads configuration files and loads information necessary for coordinating experiments.
        """
        # Set static contact angle measuring experiment procedure as the experiment.
        self.set_experiment(ContactAngleMeasurementExperiment())

        # Load the labware groups json file that maps labware types to locations on the OT-2 deck.
        with open('./PARAMETERS/RAISE_STATIC_CA_LABWARE_GROUPS.json', mode='r') as fd:
            LW_GROUPS = json.load(fd)
        # Pass the labware group dictionary to the experiment object
        self.experiment.set_labware_profile(LW_GROUPS)

        # Load the liquid location json file to help locate liquids on the OT-2 deck.
        with open('./PARAMETERS/RAISE_STATIC_CA_LIQUID_LOCATIONS.json', mode='r') as fd:
            LIQUID_LOCATIONS_DICT = json.load(fd)
        # Pass the liquid location dictionary to the experiment object
        self.experiment.set_liquid_locations(LIQUID_LOCATIONS_DICT)
        print(LIQUID_LOCATIONS_DICT)

        print('Creating Experiment Manager...')
        # Send OT-2 client deck layout configuration.
        print('Setting Deck Layout...')
        await self.set_deck_layout('./PARAMETERS/RAISE_STATIC_CA_LAYOUT.json')
        
        # Connect database to experiment object
        print('Loading Experiment...')
        self.experiment.set_database_interface(self.database_interface)

        # Create output folder to store experiment data, if one does not exist
        # Data folders are created dynamically and contain the date on which the experiment began on.
        date_now = datetime.now()
        dir_name = f'../DATA/{date_now.strftime("%Y-%m-%d")}/'
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)
        
        # Allow up to 10 sub-folders within the main data folder.
        sub_dir_name = f'{dir_name}{0}/' 
        for i in range(1, 11):
            sub_dir_name = f'{dir_name}{i}/' 
            if os.path.exists(sub_dir_name):
                continue
            else:
                os.mkdir(sub_dir_name)
                break
        # Pass the output folder name to the experiment object
        self.experiment.set_output_dir(sub_dir_name)

        # Load the labware usage json file to help allocate the enough resources to perform each round of experiments.
        LW_USAGE = load_labware_usage_parameters('./PARAMETERS/RAISE_STATIC_CA_LABWARE_USAGE.json')
        self.set_labware_usage_template(LW_USAGE)
        
        # Define which wells on the defined labwares should be used and in which order.
        print('Retrieving wells for labwares...')
        await self.set_labware_wells(LW_GROUPS, 
                                    {'mixing_wells': 'by_rows', 'dest_wells': 'by_rows'},
                                    subset={'dest_wells': self.get_labware_subset(1, ['E', 'D', 'C', 'B', 'A'], list(range(2, 11)))})
        print(self.labware_wells)
        
        # Start tracking well usage
        self.track_labware_wells()

        # Get information from the OT-2 about the minimum/maximum volumes that each pipette can handle.
        await self.set_min_max_pipette_volumes()

        # Load the reagent json file to define which reagents are loaded on the OT-2 deck and at what concentrations.
        self.set_reagents('./PARAMETERS/RAISE_STATIC_CA_REAGENTS.json')

        print('Setup Complete!!!')

    def set_reagents(self, fname: str) -> None:
        """
        Load the reagent configuration file and stores reagent information in a dictionary.
        """
        with open(fname, mode='r') as fd:
            REAGENTS: Dict[str, List[float]] = json.load(fd)
        self.reagents: Dict[str: Reagent] = {reagent_name: Reagent(reagent_name, conc_list) for reagent_name, conc_list in REAGENTS.items()}
    
    def set_database_interface(self, database_inferface: dbi) -> None:
        """
        Set the database interface.
        """
        self.database_interface = database_inferface
    
    # For each type of labware, get and store list of all wells...
    def get_labware_subset(self, slot: int, rows: List[str], cols: List[int]) -> List[str]:
        """
        Return a list of string combinations representating wells on a labware.
        """
        well_list: List[str] = []
        for row in rows:
            for col in cols:
                well_list.append(f'{slot}-{row}{col}')
        return well_list
    
    def start_experiment(self) -> None:
        self.experiment_running = True

    def stop_experiment(self) -> None:
        self.experiment_running = False
    
    def is_running_experiment(self) -> bool:
        return self.experiment_running

    def set_experiment(self, experiment: Experiment) -> None:
        """
        Sets a Experiment object to the experiment manager.
        """
        self.experiment: Experiment = experiment
    
    async def set_deck_layout(self, fname: str) -> None:
        """
        Send OT-2 client the deck layout configuration.
        """
        with open(fname, mode='r') as fd:
            layout_dict: Dict[int | str, Any] = json.load(fd)
        
        print(f'Printing Layout in EM {layout_dict}')
        await self.command_handler.set_deck_layout(layout_dict)
    
    async def set_labware_wells(self, labware_group_dict: Dict[str, List[int]], 
                                order: str | Dict[str, str] = 'default',
                                subset: Dict[str, List[str]] | None = None):
        """
        Sets wells on labware that are available to use for the experiment.
        Has the option to define subsets of wells on labware or the ordering of wells.
        """
        # Send the OT-2 client a string or a formated dictionary to receive the wells on loaded labwares.
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
        
        # Process the dictionary mapping strings to lists of well names and store them in a labware_wells attribute
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
        """
        Set concentrations of reagents for the experiment orchestrator to prepare.
        """
        self.experiment.set_target_concentration(params)
    
    def get_target_concentration(self) -> Dict[str, float]:
        """
        Get concentrations of reagents for the experiment orchestrator to prepare.
        """
        return self.experiment.get_experiment_parameters()

    def well_generator(self, well_lst: List[str]) -> Generator[str, None, None]:
        """
        Create generator object to yield well name string representations.
        """
        for well_str in well_lst:
            yield well_str

    def track_labware_wells(self) -> None:
        """
        Store a dictionary mapping labware groups to generators of well names.
        """
        self.well_allocator = {}
        for labware_group, well_lst in self.labware_wells.items():
            if well_lst != []:
                self.well_allocator[labware_group] = self.well_generator(well_lst)
    
    def allocate_wells(self, well_generator: Generator[str, None, None], num_wells: int) -> List[str]:
        """
        Returns a list of well name strings. 
        Raises error if there is insufficient amount of free wells/tips/space on the corresponding labware.
        """
        assert num_wells >= 0
        try:
            return [next(well_generator) for _ in range(num_wells)]
        except StopIteration as err:
            return err
    
    def set_experiment_parameters(self, params: Dict[Tuple[str, float], float]) -> None:
        """
        Set dictionary of reagents and corresponding reagent volumes to mix together.
        """
        self.experiment.set_experiment_parameters(params=params)
    
    def get_experiment_parameters(self) -> Dict[Tuple[str, float], float]:
        """
        Get dictionary of reagents and corresponding reagent volumes to mix together.
        """
        return self.experiment.get_experiment_parameters()

    async def set_min_max_pipette_volumes(self) -> None:
        """
        Receives and stores information from the OT-2 about the minimum/maximum volumes that each pipette can handle.
        """
        self.volume_limits = {}
        for instrument in ['LEFT', 'RIGHT']:
            self.volume_limits[instrument] = await self.command_handler.get_min_max_volume(instrument)
            print(f'{instrument} pipette: {self.volume_limits[instrument][0]}uL - {self.volume_limits[instrument][1]}uL')
    
    def get_min_max_pipette_volumes(self) -> Dict[str, Tuple[float, float]]:
        """
        Returns the minimum/maximum volumes that each pipette can handle.
        """
        return self.volume_limits
    
    def set_labware_usage_template(self, labware_usage_template: Dict[str, int | Callable[[int], int]]) -> None:
        """
        Set the dictionary for calculating how many wells/resources on the deck are required for each experiment.
        """
        self.labware_usage_template = labware_usage_template
    
    def get_labware_usage_template(self) -> Dict[str, int | Callable[[int], int]]:
        """
        Get the dictionary for calculating how many wells/resources on the deck are required for each experiment.
        """
        return self.labware_usage_template
    
    def get_pipette_usage(self, ignore_left: bool = False, ignore_right: bool = False) -> Dict[str, int]:
        """
        Calculate and return how may pipette tips each loaded pipette requires to transfer the amount of liquid
        defined by the target formulation.
        """
        # Get formulation of reagents to mix together
        experiment_parameters: Dict[str, float] = self.get_experiment_parameters()
        # Get the volume ranges for each loaded pipette
        pipette_volume_limits: Dict[str, Tuple[float, float]] = self.get_min_max_pipette_volumes()
        left_min, left_max = pipette_volume_limits['LEFT']
        right_min, right_max = pipette_volume_limits['RIGHT']

        left_counter = 0
        right_counter = 0

        # Calculate number of pipette tips required to transfer each reagent.
        # Ignore the use of one pipette if the experiment protocol calls for it.
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
        
        # Store the required pipette usage in a dictionary and return the dictionary
        pipette_counter = {'LEFT': left_counter, 'RIGHT': right_counter}
        print(pipette_counter)
        return pipette_counter

    def set_labware_usage(self, counter: Dict[str, int]) -> None:
        """
        Calculate and store the total number of wells/tips/spaces on the corresponding labware 
        required to complete an experiment.
        """
        # Get the templete for calculating wells/tips/space for each labware
        lw_usage_copy = dict(self.get_labware_usage_template())
        for group, num in lw_usage_copy.items():
            # If there is a specific labware resources that is required for an experiment, 
            # keep the amount required the same or make modification as defined in the template.
            if (group in counter.keys()) and (not isinstance(num, int)):
                func: Callable[[int], int] = lw_usage_copy[group]
                lw_usage_copy[group] = func(counter[group])
        print(lw_usage_copy)
        # Set the labware usage in the experiment object
        self.experiment.set_labware_usage(lw_usage_copy)
    
    async def allocate_wells_for_new_experiment(self) -> Dict[str, List[str]]:
        """
        Return a dictionary that maps labware groups to lists of corresponding wells/tips/spaces
        required to perform an experiment.
        """
        # Get the pipette usage to mix the formulation of reagents
        pipette_counter: Dict[str, int] = self.get_pipette_usage()

        # Set the labware usage in the experiment object
        self.set_labware_usage(pipette_counter)

        # Allocate the correct amount of wells/tips/spaces to complete the experiment
        dict : Dict[str, List[str]] = {}
        experiment_wells_usage = self.experiment.get_well_usage()
        for labware_group, well_generator in self.well_allocator.items():
            num_wells = experiment_wells_usage[labware_group]
            result = self.allocate_wells(well_generator, num_wells)
            if isinstance(result, StopIteration):
                # Alert user to refill labwares before experiment can begin
                labware_profile = self.experiment.get_labware_profile()
                self.refill_labwares(labware_group, labware_profile[labware_group])
                # If the dest_wells labware (i.e. the stage) needs to be cleaned, 
                # increment the internal counter so that previous saved image files 
                # do not get overwritten by files with the same filename.
                if labware_group == 'dest_wells':
                    self.experiment.increment_counter()
                # Update well generator in well allocator
                new_well_generator = self.well_generator(self.labware_wells[labware_group])
                self.well_allocator[labware_group] = new_well_generator
                result = self.allocate_wells(new_well_generator, num_wells)
            dict[labware_group] = result
        return dict

    def refill_labwares(self, labware_group: str, deck_slots: List[int] | None = None):
        """
        If there is not enough wells/tips/spaces to complete an experiment,
        use an input prompt to block the user from continuing with the campaign until 
        the corresponding labware is refilled.
        """
        if deck_slots is None:
            prompt_message = f"Please refill/replace labware(s) \'{labware_group}\'. Continue [Enter]?"
        else:
            prompt_message = f"Please refill/replace labware(s) \'{labware_group}\' at slots {deck_slots}. Continue [Enter]?"
        input(prompt_message)
    
    def get_experiment_formulation(self, target: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate the volumes of each reagents necessary to create the formulation with 
        specific reagent target concentrations.
        """
        # Ensure that the reagent in the target formulation are already defined in reagents attribute.
        try:
            for reagent_name in target.keys():
                #reagent_name = reagent_name.split('_')[0]
                assert reagent_name in self.reagents.keys()
        except:
            pass

        # Get stored reagents dictionary
        reagents: Dict[str, Reagent] = self.reagents

        # If the target is just water, return a simple formulation of just water.
        if target == {'H2O': 100.0}:
            return {'H2O': 200}
        
        # Calculate the reagents volumes required to mix 300uL of the target formulation
        formulation: Dict[Tuple[str, float], float] = get_mixture_formulation(reagents, target, total_volume=300)

        # Sort the formulation so that reagents are ordered based on descending volumes.
        # This ensures that small volumes of reagents are not mishandled during the reagent mixing procedure.
        sorted_reagents = sorted(zip(formulation.keys(), formulation.values()), key=lambda x: x[1], reverse=True)

        # Remove any reagents that have 0.0 volume, as attempting to pipette 0.0uL will just discard a tip.
        formulation_sorted: Dict[Tuple[str, float], float] = dict()
        for reagent_vol in sorted_reagents:
            reagent_name, vol = reagent_vol
            if vol > 0.0:
                formulation_sorted[reagent_name] = vol
        
        #Return the final formulation of reagents
        return formulation_sorted

    async def main_loop(self):
        # Read and obtain cert for MQTT communication
        der_fname = "hivemq-com-chain.der"
        try:
            print("Obtaining CA Certificate")
            with open(der_fname, "rb") as f:
                cacert = f.read()
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print(f"{der_fname} file not found. For versions 0.4.2+, this file is required. Please upload this to the Pico W directly, you can generate this cert with cert_generator.py")

        # Create SSL context
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.load_verify_locations(cadata=cacert)

        # Initiate data analysis process
        conn_1, conn_2 = Pipe()
        self.connection = conn_1
        self.event = Event()
        self.data_analysis_process: Process = Process(target=analyze_data, args=(conn_2, self.event))
        self.data_analysis_process.start()
        print(f'Spawned processess for data analysis (PID:{self.data_analysis_process.pid})')

        # Initiate MQTT client
        async with aiomqtt.Client(
            hostname=HOSTNAME,
            identifier = 'ot2_test',
            port=8883,
            username=USERNAME,
            password=PASSWORD,
            keepalive=5*60,
            tls_context=ssl_context
        ) as client:
            # Sanity testing
            print('MQTT Client Connected')

            # Add experiment manager to mqtt interface
            await client.subscribe("logging", qos=0)
            
            # Example publishing
            await client.publish("logging", dumps("Manager Server Connected to MQTT"))
            await client.subscribe('output/bayesian', qos=0)
            print('Output folder' + self.experiment.get_output_dir())
            self.bo_campaign_process: Process = Process(target=bo_main_loop, args=(self.experiment.get_output_dir(), ))
            self.bo_campaign_process.start()
            print(f'Spawned processess for data analysis (PID:{self.bo_campaign_process.pid})')

            # Keep the connection alive
            i = 1
            try:
                while True:
                    print('Waiting for message from BO client...')

                    # Receive a message from the BO client
                    message = await anext(client.messages)
                    # async for message in client.messages:
                    # Attempt to deserialize or decode the message
                    if isinstance(message.payload, bytes):
                        try:
                            payload = loads(message.payload)

                        except:
                            payload = message.payload.decode()
                    else:
                        raise ValueError(f'Unexpected message type: {type(message)}')

                    print(message.topic)
                    if str(message.topic) == 'output/bayesian':
                        # For new experiments, the message payload is a new formulation recommendation
                        # Store the target recommendation in the experiment
                        print('Experiment Target Concentration: ', payload, type(payload))
                        self.set_target_concentration(payload)

                        # Take experiment recommendation and create formulation
                        experiment_fomulation: Dict[str, float] = self.get_experiment_formulation(payload)
                        print('Experiment Formulation: ', experiment_fomulation, type(payload))

                        # Store the calculated formulation in the experiment
                        self.set_experiment_parameters(experiment_fomulation)
                        # Allocate wells/tips/spaces to complete the experiment
                        allocated_wells = await self.allocate_wells_for_new_experiment()
                        print(f'Allocated wells: {allocated_wells}')

                        # Send contact angle measuring process a signal to begin a new experiment and 
                        # provid information about the new experiment
                        # including filename (.csv) for replicate measurements and output folder name.
                        self.event.clear()
                        output_fname = f'{self.experiment.get_output_dir()}Experiment_{i}.csv'
                        self.connection.send('START_EXPERIMENT')
                        self.connection.send(output_fname)
                        self.connection.send(self.experiment.get_output_dir())
                        
                        # Run the main contact angle measuring procedure.
                        await self.experiment.run(self.command_handler,
                                                allocated_wells=allocated_wells, 
                                                connection=self.connection)
                        
                        # Send contact angle measuring process a signal to end the experiment. 
                        self.connection.send('END_EXPERIMENT')
                        self.event.wait()

                        # Receive the average and standard deviation of static contact angle measurements 
                        # accross a set of replicates.
                        result = self.connection.recv()
                        assert isinstance(result, tuple)
                        assert len(result) == 2
                        ca_avg, ca_std = result
                        print(f'Contact Angle Mean: {round(ca_avg, 3)}\nSTD: {round(ca_std, 3)}')

                        # Append the average static measurement to the original payload message
                        # and send the payload + measurement back to the BO client.
                        datapoint = payload
                        datapoint['StaticContactAngle'] = round(ca_avg, 3)
                        datapoint = {k: [v] for k, v in datapoint.items()}
                        payload = ('dict', datapoint)
                        await client.publish('input/bayesian', dumps(payload))

                        # Request a new experiment from the BO client.
                        payload = ('str', 'next_experiment')
                        await client.publish('input/bayesian', dumps(payload))

                        i += 1
            except:
                traceback.print_exc()
            finally:        
                # Close child processes
                print('Closing Child Processes...')
                self.bo_campaign_process.terminate()
                self.data_analysis_process.terminate()

                print('Disconnecting from client...')
                if self.command_handler.writer is not None:
                    self.command_handler.writer.close()
                    await self.command_handler.writer.wait_closed()