#!/usr/bin/env python3

from check_all import *
from influxdb_client import InfluxDBClient, Point

def write_throughput_influx(config, iface, server, throughput):
    client = InfluxDBClient(
        url=config['influx_url'],
        token=config['influx_token'],
        org=config['influx_org'])
    write_api = client.write_api()

    write_api.write(
        config['influx_bucket'],
        config['influx_org'],
        Point('troughput_down')
            .tag('iface', iface)
            .tag('server', server)
            .field('mbps', throughput)
        )

    write_api.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Perform tests on networks.')
    parser.add_argument('iface', metavar='IFACE',
                        help='interface to test on')
    parser.add_argument('servers', metavar='SERVER', nargs='+',
                        help='servers to test for that interface')
    parser.add_argument('-v', '--verbose', type=bool, action='store_true', default=False)

    args = parser.parse_args()

    for server in args.servers:
        config = get_config('conf.ini', args.iface, server)

        ns = prepare(config, args.iface)

        # measure
        throughput = speedtest_cli(ns)

        # write to influx
        write_throughput_influx(config, args.iface, server, throughput)