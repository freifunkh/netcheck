#!/usr/bin/env python3

import re
import os
import sys
import os.path
import shutil
import pyroute2
import subprocess
from pyroute2 import IPRoute, NetNS, netns


TMP_DIR = '/tmp/netcheck/'
DHCP_TIMEOUT = 5
NETNS_NAME = 'test'
TESTIF_NAME = 'testif'
PING_TEST_IP4 = '8.8.8.8'
SCRIPT_DIR = os.path.dirname(__file__)
CHECK_DHCP_BINARY = os.path.join(SCRIPT_DIR, 'netcheck_check_dhcp')

cleanup_after_run = False

def init():
    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR)

    os.mkdir(TMP_DIR)

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
        return False
    
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

iface = 'veth0'
gateway_ip4 = '10.118.1.1'
static_ip4 = '10.118.1.190'

# iface = 'wlp3s0'
# gateway_ip4 = '192.168.178.165'
# static_ip4 = '192.168.178.170'
static_ip4_plen = 24

test_3rd_party_tool_availability()

# cleanup
if NETNS_NAME in netns.listnetns():
    ns = NetNS(NETNS_NAME)
    cleanup_remove_iface(ns, TESTIF_NAME)
    ns.close()
    netns.remove(NETNS_NAME)

netns.create(NETNS_NAME)

ip = IPRoute()

cleanup_remove_iface(ip, TESTIF_NAME)
ip.link('add', ifname=TESTIF_NAME, kind="macvtap", link=lookup_iface(ip, iface), net_ns_fd=NETNS_NAME, state='up')

ns = NetNS(NETNS_NAME)

# create ip if not existing
install_ip(ns, TESTIF_NAME, static_ip4, static_ip4_plen)

if not is_reachable(ns, gateway_ip4):
    print(f'Config error. The gateway_ip4 {gateway_ip4} you specified is not in the range of {static_ip4}/{static_ip4_plen}.', file=sys.stderr)
    exit(1)

print('Is gateway reachable?: ', end='', flush=True)
print(ping(ns, gateway_ip4), flush=True)
print('Does gateway answer DHCP?: ', end='', flush=True)
print(check_dhcp(ns, TESTIF_NAME, gateway_ip4), flush=True)

install_default_router(ns, TESTIF_NAME, gateway_ip4)

print(f'Is {PING_TEST_IP4} reachable via gateway?: ', end='', flush=True)
print(ping(ns, PING_TEST_IP4), flush=True)

if cleanup_after_run:
    cleanup_remove_iface(ns, TESTIF_NAME)
    ns.close()
    netns.remove(NETNS_NAME)