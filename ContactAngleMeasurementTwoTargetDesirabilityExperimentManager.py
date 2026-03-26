from ExperimentManager import ExperimentManager, Experiment
from ContactAngleMeasurementExperimentManager import ContactAngleMeasurementExperimentManager
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
class ContactAngleMeasurementTwoTargetDesirabilityExperimentManager(ContactAngleMeasurementExperimentManager):
    '''
    Responsibilities:
    * Store Experiment object
    * Keep track of experiment consumable/resource usage
    * Allocate resources for experiments
    '''
    def __init__(self, command_handler: AsyncServerCommandHandler | None = None, 
                 database_interface: dbi | None = None
                 ) -> None:
        super().__init__(command_handler=command_handler, database_interface=database_interface)

    async def main_loop(self):
        # Read and obtain cert for MQTT communication
        der_fname = "hivemq-com-chain.der"
        try:
            print("Obtaining CA Certificate")
            with open(der_fname, "rb") as f:
                cacert = f.read()
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print(f"{der_fname} file not found. For versions 0.4.2+, this file is required.")

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
                            payload: Dict[str, float] = loads(message.payload)

                        except:
                            payload = message.payload.decode()
                    else:
                        raise ValueError(f'Unexpected message type: {type(message)}')

                    print(message.topic)
                    if str(message.topic) == 'output/bayesian':
                        # For new experiments, the message payload is a new formulation recommendation
                        # Store the target recommendation in the experiment
                        print('Experiment Target Concentration: ', payload)
                        self.set_target_concentration(payload)

                        total_conc: float = sum(payload.values())
                        print(f'Total Surfactant Concentration: {total_conc:.2f}%')

                        payload_copy: Dict[str, float] = dict(payload)

                        # Take experiment recommendation and create formulation
                        experiment_fomulation: Dict[str, float] = self.get_experiment_formulation(payload)
                        print('Experiment Formulation: ', experiment_fomulation)

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
                        payload_copy['StaticContactAngle'] = round(ca_avg, 3)

                        # Append addition Target Parameter for Multi-Objective Campaigns
                        payload_copy['TotalSurfactantConcentration'] = total_conc

                        # Send the payload + measurement back to the BO client.
                        payload_copy = {k: [v] for k, v in payload_copy.items()}
                        payload = ('dict', payload_copy)
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