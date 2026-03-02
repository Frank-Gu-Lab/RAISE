import asyncio
import aiomqtt
from pickle import loads, dumps
from utils.secret_credentials import HOSTNAME, USERNAME, PASSWORD
from utils.helper_functions import parameter_creator
import ssl
from baybe import Campaign
from baybe.utils.random import temporary_seed, set_random_seed
from BO_Campaign_Designer import get_BO_campaign
import pandas as pd
import sys
import os
import numpy as np
import json
from typing import Dict
from argparse import ArgumentParser
from datetime import datetime
import traceback


# This block of code is necessary for running on devices with Windows OS
if sys.platform.lower() == "win32" or os.name.lower() == "nt":
    from asyncio import set_event_loop_policy, WindowsSelectorEventLoopPolicy
    set_event_loop_policy(WindowsSelectorEventLoopPolicy())



#channels for input, output, and logging
BO_INPUT_CHANNEL = 'input/bayesian'
BO_LOGGING_CHANNEL = 'logging/bayesian'
BO_OUTPUT_CHANNEL = 'output/bayesian'


# Read and obtain certificate
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


async def main(campaign: Campaign, output_path: str):
    counter: int = 1
    try:
        async with aiomqtt.Client(
            hostname=HOSTNAME,
            identifier = 'bo_client_test',
            port=8883,
            username=USERNAME,
            password=PASSWORD,
            keepalive=5 * 60,
            tls_context=ssl_context
        ) as client:
            # sanity testing
            print('MQTT Client Connected')

            await client.subscribe(BO_INPUT_CHANNEL, qos=0) #setup input, we listen for commands here
            await client.publish(BO_LOGGING_CHANNEL, f"BO_Client connected, listening on {BO_INPUT_CHANNEL}") #setup output, we publish params here


            print('starting new experiment')
            experiment_to_do = campaign.recommend(batch_size=1)
            print(experiment_to_do.to_dict())
            experiment_output = dict(map(lambda item: (item[0],item[1][experiment_to_do.index[0]]), experiment_to_do.to_dict().items()))
            await client.publish (BO_OUTPUT_CHANNEL, dumps(experiment_output))
            print(f'First experiment is : {experiment_output}')


            async for message in client.messages:
                print(f'data received of type {type(message)}')

                dtype, data = loads(message.payload) #comment if testing, uncomment try except above
                print(data)
                if dtype == 'str':
                    if data == 'next_experiment':
                        await client.publish(BO_LOGGING_CHANNEL, 'Request for new experiment received')
                        experiment_to_do = campaign.recommend(batch_size=1)
                        experiment_output = dict(map(lambda item: (item[0],item[1][experiment_to_do.index[0]]), experiment_to_do.to_dict().items()))
                        print(f'Recommended experiment is : {experiment_output}')

                        #this outputs the nexzt set of parameters as a serialized pandas dataframe
                        await client.publish (BO_OUTPUT_CHANNEL, dumps(experiment_output))

                elif dtype == 'dict':
                    await client.publish(BO_LOGGING_CHANNEL, 'Measurement data received, attaching to campaign')
                    #this is to do, which depends on the experiment object received
                    campaign.add_measurements(pd.DataFrame(data))
                    if counter % 3 == 0:
                        campaign.measurements.to_csv(output_path)
                    counter += 1


                else:
                    await client.publish(BO_LOGGING_CHANNEL, 'Received invalid request')
                
    except:
        traceback.print_exc()
    finally:
        print('Writing data in CSV file...')
        campaign.measurements.to_csv(output_path)

def load_campaign_parameters(fname: str) -> Dict[str, str | bool | int]:
    with open(fname, mode='r') as fd:
        param_dict = json.load(fd)
    return param_dict

def load_campaign_from_json(fname: str) -> Campaign:
    with open(fname, mode='r') as fd:
        campaign_json = json.load(fd)
    return Campaign.from_json(campaign_json)

def load_previous_measurements(campaign: Campaign, output_path: str) -> None:
    df: pd.DataFrame = pd.read_csv(output_path, header=0, index_col=0)
    print(df)

    # isolate target parameter
    # NEED WORK TO MAKE MORE GENERIC
    prev_measurements = df.iloc[:, -3]
    for measurement in prev_measurements:
        rec = campaign.recommend(batch_size=1)
        rec['StaticContactAngle'] = [measurement]
        campaign.add_measurements(rec)




def bo_main_loop(output_dir: str = '', seed: int = 0):
    if output_dir == '':
        date_now = datetime.now()
        dir_name = f'../DATA/{date_now.strftime("%Y-%m-%d")}/'
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)
        OUTPUT_PATH: str = dir_name + 'CAMPAIGN_MEASUREMENTS.csv'
    else:
        OUTPUT_PATH: str = output_dir + 'CAMPAIGN_MEASUREMENTS.csv'
    print(OUTPUT_PATH)
    
    # Set randomization seed
    set_random_seed(seed)

    # Design BO Campaign based on user inputs
    campaign: Campaign = get_BO_campaign('./PARAMETERS/RAISE_BO_PARAMETERS.json', './PARAMETERS/RAISE_BO_TARGETS.json')
    print(campaign)

    asyncio.run(main(campaign, OUTPUT_PATH))

if __name__ == '__main__':
    arg_parser: ArgumentParser = ArgumentParser(prog='BO_Client.py', description='Combines API and polymers to screen for gelation.')
    arg_parser.add_argument('CAMPAIGN_PARAMETERS', help='Path to JSON file for setting up Bayesian Optimization experiment campaign.')
    args = arg_parser.parse_args()

    # parse command-line arguments for location of initial experiment parameters
    campaign_params = load_campaign_parameters(args.CAMPAIGN_PARAMETERS)
    #print(campaign_params)
    CAMPAIGN_PATH = campaign_params['CAMPAIGN_PATH']
    NEW_CAMPAIGN = campaign_params['NEW_CAMPAIGN']
    SEED = campaign_params['SEED']
    OUTPUT_PATH = campaign_params ['OUTPUT_PATH']

    i: int = 1
    date_now = datetime.now()
    dir_name = f'../DATA/{date_now.strftime("%Y-%m-%d")}/'
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    OUTPUT_PATH = dir_name + 'CAMPAIGN_MEASUREMENTS.csv'
    print(OUTPUT_PATH)

    # Set randomization seed
    set_random_seed(SEED)

    # Load cached campaign, if one exists
    campaign = load_campaign_from_json(CAMPAIGN_PATH)
    print(campaign)

    PREVIOUS_DATA_PATH = '../DATA/2025-05-30/CAMPAIGN_MEASUREMENTS.csv'
    load_previous_measurements(campaign, PREVIOUS_DATA_PATH)
    print(campaign.measurements)

    asyncio.run(main(campaign, OUTPUT_PATH))