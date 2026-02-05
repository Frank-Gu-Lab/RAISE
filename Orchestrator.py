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
from utils.secret_credentials import HOSTNAME, USERNAME, PASSWORD
from UserInputParser import process_user_inputs, get_target_count

import sys
import os

if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())



async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                        ):
    try:
        # Instantiate command handler
        command_handler = AsyncServerCommandHandler()
        command_handler.set_device(CameraDevice(cam_idx=0, name='Camera 1'))

        #db_interface: dbi = dbi(db_name='SDL5', collection_name='TESTS')
        db_interface = None

        # Read user inputs from file system
        with open('./PARAMETERS/USER_INPUTS.json', mode='r') as fd:
            usr_inputs = json.load(fd)
        print(usr_inputs)
        process_user_inputs(raise_param_form=usr_inputs, usr_param_dir='./PARAMETERS/')
        
        num_targets: int = get_target_count(usr_inputs)

        # Choose which type of campaign experiment to run
        if num_targets == 1:
            experiment_manager: ExperimentManager = ContactAngleMeasurementExperimentManager(command_handler, 
                                                                                             db_interface
                                                                                             )
            print(f"One Target Selected: [{usr_inputs['t1_name']}]")
        elif num_targets == 2:
            experiment_manager: ExperimentManager = ContactAngleMeasurementTwoTargetDesirabilityExperimentManager(command_handler, 
                                                                                                                  db_interface
                                                                                                                  )
            print(f"Two Target Selected: [{usr_inputs['t1_name']}, {usr_inputs['t2_name']}]")
        else:
            raise ValueError

        # Attach reader and writer streams for communicating with OT-2
        experiment_manager.command_handler.set_reader_writer(reader, writer)
        
        await writer.drain()

        data = await reader.read(1024)
        if not data:
            print('Connection closed by client')
            return
        print(f"Received data: {data.decode()}")
        
        await writer.drain()


        await experiment_manager.set_experiment_profile()

        await experiment_manager.main_loop()
    except:
        traceback.print_exc()
    finally:
        if experiment_manager.data_analysis_process is not None:
            experiment_manager.data_analysis_process.close()

        if experiment_manager.bo_campaign_process is not None:
            experiment_manager.bo_campaign_process.close()
        
        print('Disconnecting from client...')
        writer.close()
        await writer.wait_closed()


async def ot_server(server: AsyncServer):
    # await server.__aenter__()
    async with server:
        server_socket = server.get_socket()
        server_socket.setblocking(False)
        
        async def handle_connection(reader, writer):
            await handle_client(reader, writer)

        
        server = await asyncio.start_server(
            handle_connection,
            sock=server_socket
        )

        async with server:
            await server.serve_forever()


if __name__ == '__main__':
    # Instantiate main server
    server_main = AsyncServer(name='Camera Server', port=1200)

    async def main(server_main):
        await asyncio.gather(
            ot_server(server_main), 
            )
        

    # Run the main function
    asyncio.run(main(server_main))
    
