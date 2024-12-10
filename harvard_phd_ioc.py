
import logging
import socket
import sys
import attrs
from datetime import datetime, timezone
from caproto.server import PVGroup, pvproperty, PvpropertyString, run, template_arg_parser, AsyncLibraryLayer
from caproto import ChannelData

import logging

logger = logging.getLogger("HarvardPhDIOC")
logger.setLevel(logging.INFO)

# Validators for IP and Port
def validate_ip_address(instance, attribute, value):
    try:
        socket.inet_aton(value)
    except socket.error:
        raise ValueError(f"Invalid IP address: {value}")


def validate_port_number(instance, attribute, value):
    if not (0 <= value <= 65535):
        raise ValueError(f"Port number must be between 0 and 65535, got {value}")


# PortentaClient encapsulates connection logic
class HarvardClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def _connect(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        return sock

    def read(self, parameter: str, element:int = -1, rstrip: str='') -> str|float:
        message = f"parameter\n"
        with self._connect() as sock:
            sock.sendall(message.encode('utf-8'))
            response = sock.recv(1024).decode('utf-8')
            firstline = response.strip().split('\n')[0]
            statusline = response.strip().split('\n')[1]
        try:
            return float(firstline.strip().split(' ')[element].rstrip(rstrip))
        except TypeError:
            return 


    def write(self, bus: str, pin: int, value: int | float | str):
        if isinstance(value, str):
            value = 1 if value.lower() in {'on', '1', 'true'} else 0
        message = f"SET {bus} {pin} {value}\n"
        logger.debug(f"Writing message: {message}")
        with self._connect() as sock:
            sock.sendall(message.encode('utf-8'))
            response = sock.recv(1024).decode('utf-8')
        if response != "OK":
            raise ValueError(f"Unexpected response: {response}")



@attrs.define
class HarvardPhDIOC(PVGroup):
    host: str = attrs.field(default="172.17.1.14", validator=validate_ip_address, converter=str)
    port: int = attrs.field(default=4011, validator=validate_port_number, converter=int)
    client: HarvardClient = attrs.field(init=False)

    def __init__(self, *args, **kwargs) -> None:
        for k in list(kwargs.keys()):
            if k in ['host', 'port']:
                setattr(self, k, kwargs.pop(k))
        self.client = HarvardClient(self.host, self.port)
        super().__init__(*args, **kwargs)

    do0 = pvproperty(name="do0", doc="Digital output 0, can be 0 or 1", dtype=bool, record='bi')
    do0_RBV = pvproperty(name="do0_RBV", doc="Readback value for digital output 0", dtype=bool, record='bi')
    @do0.putter
    async def do0(self, instance, value: bool):
        self.client.write("DO", 0, value)
    @do0.scan(period=6, use_scan_field=True)
    async def do0(self, instance: ChannelData, async_lib: AsyncLibraryLayer):
        await self.do0_RBV.write(self.client.read("DO", 0))

    diameter = pvproperty(name="diameter", doc="diameter of the syringe in mm", dtype=float, record='ai')
    diameter_RBV = pvproperty(name="diameter_RBV", doc="Readback value for diameter of the syringe in mm", dtype=float, record='ai')
    @diameter.putter
    async def ao0(self, instance, value: float):
        self.client.write("AO", 0, value)
    @diameter.scan(period=6, use_scan_field=True)
    async def ao0(self, instance: ChannelData, async_lib: AsyncLibraryLayer):
        await self.diameter_RBV.write(self.client.read("AO", 0))



def main(args=None):
    parser, split_args = template_arg_parser(
        default_prefix="Portenta:",
        desc="EPICS IOC for accessing I/O on the Arduino Portenta Machine Control (PMC) over network",
    )

    if args is None:
        args = sys.argv[1:]

    parser.add_argument("--host", required=True, type=str, help="IP address of the host/device")
    parser.add_argument("--port", required=True, type=int, help="Port number of the device")

    args = parser.parse_args()

    logging.info("Running Networked Portenta IOC")

    ioc_options, run_options = split_args(args)
    ioc = HarvardPhDIOC(host=args.host, port=args.port, **ioc_options)
    run(ioc.pvdb, **run_options)


if __name__ == "__main__":
    main()
