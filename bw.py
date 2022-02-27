#!/usr/bin/env python3

from check_all import *

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
    iface = "bat10"
    server = "sn10"
    config = get_config('conf.ini', iface, server)

    ns = prepare(config, iface)

    # measure
    throughput = speedtest_cli(ns)

    # write to influx
    write_throughput_influx(config, iface, server, throughput)