#!/bin/sh

set -x

sudo ip link add veth1 type veth peer name veth0
sudo pkill dnsmasq
sudo ip netns add test-dnsmasq
sudo ip link set veth1 netns test-dnsmasq
sudo ip netns exec test-dnsmasq ip addr add 10.118.1.1/24 dev veth1
sudo ip netns exec test-dnsmasq dnsmasq -i veth1 -C test/test_dnsmasq.conf

sudo ip netns exec test-dnsmasq ip link set veth1 up

set +x

echo
echo TO JOIN THE NETNS, USE:
echo 
echo "- sudo ip netns exec test $SHELL"
echo "- sudo ip netns exec test-dnsmasq $SHELL"
