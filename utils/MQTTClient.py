import aiomqtt
import sys
import paho.mqtt as mqtt
from time import sleep
from secrets import HOSTNAME, USERNAME, PASSWORD
import asyncio
import ssl

# To validate certificates, a valid time is required

def get_traceback(err):
    try:
        with StringIO() as f:  # type: ignore
            sys.print_exception(err, f)
            return f.getvalue()
    except Exception as err2:
        print(err2)
        return f"Failed to extract file and line number due to {err2}.\nOriginal error: {err}"  # noqa: E501


# Read and obtain cert
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


async def main():
    async with aiomqtt.Client(
        hostname=HOSTNAME,
        identifier = 'ot2_test',
        port=8883,
        username=USERNAME,
        password=PASSWORD,
        keepalive=120,
        tls_context=ssl_context
    ) as client:
        # sanity testing
        print('MQTT Client Connected')

        await client.subscribe("your/topic", qos=0)
        
        # Example publishing
        await client.publish("your/topic", "Hello, MQTT!")

        # Keep the connection alive
        async for messages in client.messages:
            print(messages.payload.decode('utf-8'))


# Run the main function
asyncio.run(main())
