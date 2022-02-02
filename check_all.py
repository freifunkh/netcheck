#!/usr/bin/env python3

import subprocess
import re
import os
import os.path
import shutil
import pyroute2
from pyroute2 import IPRoute, NetNS, netns


TMP_DIR = '/tmp/netcheck/'
DHCP_TIMEOUT = 5
NETNS_NAME = 'test'
TESTIF_NAME = 'testif'

cleanup_after_run = False

def init():
    if os.path.exists(TMP_DIR):
        shutil.rmtree(TMP_DIR)

    os.mkdir(TMP_DIR)

def check_dhcp(ns, iface, server, timeout=5):
    p = subprocess.run(f"ip netns exec {ns.netns} ./a.out -t {DHCP_TIMEOUT} {iface} {server}", shell=True)
    return p.returncode == 0

def install_ip(ns, iface, address, prefixlen):
    if_idx = ns.link_lookup(ifname=iface)
    if len(if_idx) < 1:
        print(f"Iface {iface} not found!")
        exit(1)

    if len(ns.get_addr(index=if_idx[0], address=address, prefixlen=prefixlen)) < 1:
        ns.addr('add', index=if_idx[0], address=address, prefixlen=prefixlen)

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
dhcp_server_ip4 = '10.118.1.1'
static_ip4 = '10.118.1.190'
static_ip4_plen = 24


# cleanup
if NETNS_NAME in netns.listnetns():
    ns = NetNS(NETNS_NAME)
    cleanup_remove_iface(ns, TESTIF_NAME)
    ns.close()
    netns.remove(NETNS_NAME)

netns.create(NETNS_NAME)

ip = IPRoute()

idx = ip.link_lookup(ifname=iface)
if len(idx) < 1:
    print(f"Iface {iface} not found!")
    exit(1)
idx = idx[0]

cleanup_remove_iface(ip, TESTIF_NAME)
ip.link('add', ifname=TESTIF_NAME, kind="macvtap", link=idx, net_ns_fd=NETNS_NAME, state='up')

ns = NetNS(NETNS_NAME)

# create ip if not existing
install_ip(ns, TESTIF_NAME, static_ip4, static_ip4_plen)

if not is_reachable(ns, dhcp_server_ip4):
    print(f'The dhcp_server_ip4 {dhcp_server_ip4} you specified is not in the range of {static_ip4}/{static_ip4_plen}.')
    exit(1)

print(check_dhcp(ns, TESTIF_NAME, dhcp_server_ip4))

if cleanup_after_run:
    cleanup_remove_iface(ns, TESTIF_NAME)
    ns.close()
    netns.remove(NETNS_NAME)