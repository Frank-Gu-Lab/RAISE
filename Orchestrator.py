from CameraDevice import CameraDevice
from AsyncServer import AsyncServer
from AsyncServerCommandHandler import AsyncServerCommandHandler
from ExperimentManager import ExperimentManager
from ContactAngleMeasurementExperimentManager import ContactAngleMeasurementExperimentManager
from ContactAngleMeasurementTwoTargetDesirabilityExperimentManager import ContactAngleMeasurementTwoTargetDesirabilityExperimentManager

import traceback
import json
import asyncio
import sys
#import paho.mqtt as mqtt
from DBInterface import DBInterface as dbi
from UserInputParser import process_user_inputs, get_target_count

import sys
import os

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """
    Async function to establish connection with the client OT-2 device, 
    parse user inputs, select the corresponding experiment protocol, 
    and connect to external resources (i.e. databases, etc...).
    After everything is set up, the client handler function runs the main experimental loop.
    """
    try:
        # Instantiate command handler that sends commands to the OT-2.
        command_handler = AsyncServerCommandHandler()
        # Open the primary camera device and attach it to the command handler.
        command_handler.set_device(CameraDevice(cam_idx=0, name='Camera 1'))

        # Establish connection to external database .
        # (may requires creating MongoDB accound, creating a cluster, and acquiring private user credentials)
        # Currently, the orchestrator does not connect to a database and will not write data to external database storage.
        #db_interface: dbi = dbi(db_name='SDL5', collection_name='TESTS')
        db_interface = None

        # Read and process user inputs saved to the file system.
        # Processed data should be saved as configuration files within PARAMETERS folder.
        with open('./PARAMETERS/USER_INPUTS.json', mode='r') as fd:
            usr_inputs = json.load(fd)
        print(usr_inputs)
        process_user_inputs(raise_param_form=usr_inputs, usr_param_dir='./PARAMETERS/')
        
        # Based on the user inputs, get the number of target parameters that the Bayesian optimizer client needs to optimize.
        num_targets: int = get_target_count(usr_inputs)

        # Choose which type of campaign experiment to run
        # Currently, the orchestrator only supports running two types of Bayesian optimization campaigns.
        if num_targets == 1:
            experiment_manager: ExperimentManager = ContactAngleMeasurementExperimentManager(command_handler, 
                                                                                             db_interface)
            print(f"One Target Selected: [{usr_inputs['t1_name']}]")
        elif num_targets == 2:
            experiment_manager: ExperimentManager = ContactAngleMeasurementTwoTargetDesirabilityExperimentManager(command_handler, 
                                                                                                                  db_interface)
            print(f"Two Target Selected: [{usr_inputs['t1_name']}, {usr_inputs['t2_name']}]")
        else:
            raise ValueError

        # Attach reader and writer streams to the command handler to communicate with the OT-2.
        experiment_manager.command_handler.set_reader_writer(reader, writer)
        
        # Drain any messages from the writer stream connection.
        await writer.drain()

        # Receive initial message to establish connection with client OT-2
        data = await reader.read(1024)
        if not data:
            print('Connection closed by client')
            return
        print(f"Received data: {data.decode()}")
        
        await writer.drain()

        # Initiate procedure to load experiment and set-up information from generated configuration files
        await experiment_manager.set_experiment_profile()

        # Call the main_loop method to begin the experimental campaign
        await experiment_manager.main_loop()
    except:
        traceback.print_exc()
    finally:
        # If there is an error is raised during set up procedure or during the experimental campaign, 
        # close connections to open pipes or streams.
        if experiment_manager.data_analysis_process is not None:
            experiment_manager.data_analysis_process.close()

        if experiment_manager.bo_campaign_process is not None:
            experiment_manager.bo_campaign_process.close()
        
        print('Disconnecting from client...')
        writer.close()
        await writer.wait_closed()


async def ot_server(server: AsyncServer):
    async with server:
        server_socket = server.get_socket()
        server_socket.setblocking(False)
        
        # Define function for handling connection with clients
        async def handle_connection(reader, writer):
            # The created connections for reading/writting data will be created 
            # and passed through the handle_client function
            await handle_client(reader, writer)

        
        server = await asyncio.start_server(
            handle_connection,
            sock=server_socket
        )

        async with server:
            await server.serve_forever()


if __name__ == '__main__':
    # Instantiate main orchestrator server
    server_main = AsyncServer(name='Camera Server', port=1200)

    # Define async main function to launch the orchestrator server
    async def main(server_main):
        await asyncio.gather(
            ot_server(server_main), 
            )
        

    # Run the main function
    asyncio.run(main(server_main))
    
