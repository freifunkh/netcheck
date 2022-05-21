#!/usr/bin/env python3

import re
import os
import sys
import json
import time
import os.path
import shutil
import argparse
import datetime
import pyroute2
import subprocess
import configparser
from pyroute2 import IPRoute, NetNS, netns
import pyroute2.netlink


DHCP_TIMEOUT = 5
NETNS_NAME = 'test'
TESTIF_NAME = 'testif'
PING_TEST_IP4 = '8.8.8.8'
SCRIPT_DIR = os.path.dirname(__file__)
CHECK_DHCP_BINARY = os.path.abspath(os.path.join(SCRIPT_DIR, 'netcheck_check_dhcp'))

cleanup_after_run = False

def test_3rd_party_tool_availability():
    tools = ['speedtest-cli', 'ping', 'ip']
    for tool in tools:
        if not shutil.which(tool):
            print(f'Tool {tool} not found in PATH. Exiting. Please install it or add it to path.', file=sys.stderr)
            exit(1)

    if not os.path.exists(CHECK_DHCP_BINARY):
        print(f'Tool {CHECK_DHCP_BINARY} not found. Please build it using make.', file=sys.stderr)
        exit(1)

def ping(ns, dest, timeout=5):
    p = subprocess.run(f"ip netns exec {ns.netns} ping -c 1 {dest} -w {timeout}", shell=True, capture_output=True)
    return p.returncode == 0

def check_dhcp(ns, iface, server):
    p = subprocess.run(f"ip netns exec {ns.netns} {CHECK_DHCP_BINARY} -t {DHCP_TIMEOUT} {iface} {server}", shell=True)
    return p.returncode == 0

def speedtest_cli(ns):
    p = subprocess.run(f"ip netns exec {ns.netns} speedtest-cli --no-upload --json", shell=True, capture_output=True)
    
    if p.returncode != 0:
        return 0.0

    stdout = p.stdout.decode('utf-8')
    download_rate = json.loads(stdout)['download']

    return download_rate

def iperf3(ns, server, duration=10):
    p = subprocess.run(f"ip netns exec {ns.netns} iperf3 -c {server} -R -J -t {duration}", shell=True, capture_output=True)

    if p.returncode != 0:
        return 0.0

    stdout = p.stdout.decode('utf-8')
    result = json.loads(stdout)

    download_rate = float(result['end']['sum_received']['bits_per_second'])
    systime_to_utc = datetime.utcnow() - datetime.now()
    start = datetime.datetime.fromtimestamp(
        result['start']['timestamp']['timesecs']) + systime_to_utc

    download_rates_details = {}
    for interval_result in result['intervals']:
        bits_per_second = float(interval_result['sum']['bits_per_second'])
        timedelta_since_start = datetime.timedelta(seconds=interval_result['sum']['end'])
        timestamp = start + timedelta_since_start

        download_rates_details[timestamp] = bits_per_second

    return download_rate, download_rates_details
    
def lookup_iface(ns, iface):
    if_idx = ns.link_lookup(ifname=iface)
    if len(if_idx) < 1:
        print(f"Iface {iface} not found!", file=sys.stderr)
        exit(1)
    
    return if_idx[0]

def install_ip(ns, iface, address, prefixlen):
    if_idx = lookup_iface(ns, iface)

    if len(ns.get_addr(index=if_idx, address=address, prefixlen=prefixlen)) < 1:
        ns.addr('add', index=if_idx, address=address, prefixlen=prefixlen)

def install_default_router(ns, iface, gateway):
    if_idx = lookup_iface(ns, iface)

    if len(ns.get_default_routes()) < 1:
        ns.route("add", dst="0.0.0.0/0", gateway=gateway)

def cleanup_remove_iface(ns, ifname):
    if len(ns.get_links(ifname=ifname)):
        ns.link('del', ifname=ifname)

def is_reachable(ns, ip):
    try:
        return len(ns.route('get', dst=ip)) > 0
    except pyroute2.netlink.exceptions.NetlinkError as e:
        if e.code == 101: # Network is unreachable
            return False

        raise e

def get_config(configfile, iface, server):
    config = configparser.ConfigParser()
    server_section = f"{iface}:{server}"

    if len(config.read(configfile)) < 1:
        print(f'Config {configfile} not found. Exiting.', file=sys.stderr)
        exit(1)

    if iface not in config.sections():
        print(f'Section {iface} not in {configfile}. Exiting.', file=sys.stderr)
        exit(1)
    
    if server_section not in config.sections():
        print(f'Section {server_section} not in {configfile}. Exiting.', file=sys.stderr)
        exit(1)

    conf = dict(config['all'])
    conf.update(dict(config[iface]))
    conf.update(dict(config[server_section]))

    return conf

def prepare(config, iface):
    static_ip4 = config['static_ip4']
    gateway_ip4 = config['gateway_ip4']
    mac = config['mac']

    if '/' not in static_ip4:
        print(f'Format for {static_ip4} is invalid. Use format like this: 10.23.10.1/24. Exiting.', file=sys.stderr)
        exit(1)

    static_ip4_plen = int(static_ip4.split('/')[1])
    static_ip4 = static_ip4.split('/')[0]

    test_3rd_party_tool_availability()

    # cleanup unclean state
    if NETNS_NAME in netns.listnetns():
        ns = NetNS(NETNS_NAME)
        cleanup_remove_iface(ns, TESTIF_NAME)
        ns.close()
        netns.remove(NETNS_NAME)

    netns.create(NETNS_NAME)

    ip = IPRoute()

    cleanup_remove_iface(ip, TESTIF_NAME)
    ip.link('add', ifname=TESTIF_NAME, kind="macvtap", link=lookup_iface(ip, iface), net_ns_fd=NETNS_NAME, state='up', address=mac)

    ns = NetNS(NETNS_NAME)

    # create ip if not existing
    install_ip(ns, TESTIF_NAME, static_ip4, static_ip4_plen)

    if not is_reachable(ns, gateway_ip4):
        print(f'Config error. The gateway_ip4 {gateway_ip4} you specified is not in the range of {static_ip4}/{static_ip4_plen}.', file=sys.stderr)
        exit(1)

    install_default_router(ns, TESTIF_NAME, gateway_ip4)

    return ns

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Perform tests on networks.')
    parser.add_argument('iface', metavar='IFACE',
                        help='interface to test on')
    parser.add_argument('server', metavar='SERVER',
                        help='server to test for that interface')

    args = parser.parse_args()

    iface = args.iface
    server = args.server
    config = get_config('conf.ini', iface, server)

    gateway_ip4 = config['gateway_ip4']

    ns = prepare(config, iface)

    print('Is gateway reachable?: ', end='', flush=True)
    print(ping(ns, gateway_ip4), flush=True)
    print('Does gateway answer DHCP?: ', end='', flush=True)
    print(check_dhcp(ns, TESTIF_NAME, gateway_ip4), flush=True)

    print(f'Is {PING_TEST_IP4} reachable via gateway?: ', end='', flush=True)
    print(ping(ns, PING_TEST_IP4), flush=True)

    print('Are more than 20 Mbit/s available?: ', end='',flush=True)
    print(speedtest_cli(ns) > 20e6)

    if cleanup_after_run:
        cleanup_remove_iface(ns, TESTIF_NAME)
        ns.close()
        netns.remove(NETNS_NAME)
