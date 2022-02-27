all: venv netcheck_check_dhcp

venv:
	python3 -m venv venv
	. venv/bin/activate; pip3 install -r requirements.txt

netcheck_check_dhcp:
	gcc check_dhcp.c -o netcheck_check_dhcp
	chmod +x ./netcheck_check_dhcp
