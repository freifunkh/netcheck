#!/usr/bin/env python3

from check_all import *
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


def write_throughput_influx(config, iface, server, throughput, throughput_details):
    
    with InfluxDBClient(
        url=config['influx_url'],
        token=config['influx_token'],
        org=config['influx_org']) as client:

        write_api = client.write_api(write_options=SYNCHRONOUS)

        write_api.write(
            config['influx_bucket'],
            config['influx_org'],
            Point('troughput_down')
                .tag('iface', iface)
                .tag('server', server)
                .field('mbps', throughput)
        )

        if throughput_details is not None:
            for time, throughput_detail in throughput_details.items():
                write_api.write(
                    config['influx_bucket'],
                    config['influx_org'],
                    Point('troughput_down_detail')
                        .tag('iface', iface)
                        .tag('server', server)
                        .field('mbps', throughput_detail)
                        .time(time.isoformat())
                )

        write_api.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Perform tests on networks.')
    parser.add_argument('iface', metavar='IFACE',
                        help='interface to test on')
    parser.add_argument('servers', metavar='SERVER', nargs='+',
                        help='servers to test for that interface')
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    parser.add_argument('--skip-preparation', action='store_true', default=False)
    parser.add_argument('--push-details', action='store_true', default=False)

    args = parser.parse_args()

    for server in args.servers:
        config = get_config('conf.ini', args.iface, server)

        if args.skip_preparation:
            ns = NetNS(NETNS_NAME)
        else:
            ns = prepare(config, args.iface)

        # measure
        throughput, throughput_details = iperf3(ns, config['gateway_ip4'], duration=60)

        if not args.push_details:
            throughput_details = None

        # write to influx
        write_throughput_influx(config, args.iface, server, throughput, throughput_details)
