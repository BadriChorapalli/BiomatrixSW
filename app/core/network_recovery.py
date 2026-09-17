"""Auto-recovery for LAN devices whose DHCP-assigned IP changes.

Two recovery methods, tried in order:

1. MAC lookup via the OS ARP table. Fast and free of network noise, but
   ARP is a link-layer protocol — it only sees hosts on the same physical
   subnet as this machine's own network interface. A device reached only
   through a router (different subnet, routed rather than switched) will
   never show up here no matter how much the ARP cache is refreshed.

2. Port-scan-and-verify. Probes every host on a candidate /24 for the
   device's known port, then calls test_connection() with the device's
   real credentials to confirm it's actually this device before accepting
   the match (a port being open proves nothing on its own). Works across
   routed subnets since it's plain TCP, not ARP — this is what covers a
   device like a Morx unit on 192.168.0.x reached from a sync machine on
   192.168.1.x with no direct L2 visibility between them.
"""

import concurrent.futures
import ipaddress
import re
import socket
import subprocess
import sys

from . import database as db

_MAC_RE = re.compile(r"([0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2}")
_IP_RE = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")

_PORT_PROBE_TIMEOUT = 0.6
_MAX_SCAN_WORKERS = 128

# Without this, each arp/ping/ipconfig call below flashes its own console
# window on Windows — refresh_arp_cache() alone can spawn up to 254 of them.
_CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _normalize_mac(mac):
    return mac.lower().replace("-", ":").strip()


def _run(args, timeout=5):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        ).stdout
    except Exception:
        return ""


# ── Method 1: ARP / MAC lookup (same-subnet devices only) ──────────────────

def get_mac_for_ip(ip):
    """Return the MAC address currently associated with ip in the OS ARP table, or None."""
    out = _run(["arp", "-a", ip] if sys.platform == "win32" else ["arp", "-n", ip])
    m = _MAC_RE.search(out)
    return _normalize_mac(m.group(0)) if m else None


def _parse_arp_table():
    out = _run(["arp", "-a"])
    entries = {}
    for line in out.splitlines():
        ip_m = _IP_RE.search(line)
        mac_m = _MAC_RE.search(line)
        if ip_m and mac_m:
            entries[_normalize_mac(mac_m.group(0))] = ip_m.group(1)
    return entries


def find_ip_for_mac(mac_address):
    if not mac_address:
        return None
    return _parse_arp_table().get(_normalize_mac(mac_address))


def _local_subnets():
    """This machine's own directly-attached /24 subnets, e.g. ['192.168.1.0/24']."""
    if sys.platform == "win32":
        out = _run(["ipconfig"])
        ips = re.findall(r"IPv4 Address[.\s]*:\s*(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", out)
    else:
        out = _run(["ifconfig"])
        ips = [ip for ip in re.findall(r"inet (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", out)
               if not ip.startswith("127.")]
    subnets = [f"{'.'.join(ip.split('.')[:3])}.0/24" for ip in ips]
    return list(dict.fromkeys(subnets))


def refresh_arp_cache():
    """Ping-sweep this machine's own local subnet(s) to populate the ARP table.

    Only reaches subnets this machine is directly attached to.
    """
    def ping(ip):
        try:
            args = ["ping", "-n", "1", "-w", "300", ip] if sys.platform == "win32" \
                else ["ping", "-c", "1", "-W", "300", ip]
            subprocess.run(args, capture_output=True, timeout=2, creationflags=_CREATE_NO_WINDOW)
        except Exception:
            pass

    hosts = []
    for subnet in _local_subnets():
        hosts.extend(str(h) for h in ipaddress.ip_network(subnet, strict=False).hosts())
    if not hosts:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SCAN_WORKERS) as ex:
        list(ex.map(ping, hosts))


def learn_device_mac(device_id, ip, stored_mac):
    """Call after a successful connection — records the device's MAC if not already known.

    No manual setup needed. Only useful when the device is later found on
    the same subnet as the sync machine; harmless no-op cost otherwise.
    """
    if stored_mac:
        return
    mac = get_mac_for_ip(ip)
    if mac:
        db.update_device_mac(device_id, mac)


# ── Method 2: port-scan + credential verification (works across subnets) ───

def _port_open(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=_PORT_PROBE_TIMEOUT):
            return True
    except Exception:
        return False


def _scan_subnet_for_port(subnet_cidr, port):
    """Return every host in subnet_cidr with `port` open (usually 0 or 1 hosts)."""
    try:
        hosts = [str(h) for h in ipaddress.ip_network(subnet_cidr, strict=False).hosts()]
    except ValueError:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_SCAN_WORKERS) as ex:
        results = list(ex.map(lambda h: (h, _port_open(h, port)), hosts))
    return [h for h, open_ in results if open_]


def _verify_and_pick(candidates, port, password, force_udp, brand):
    """Try real credentials against each port-open candidate; return the first that authenticates."""
    from .device import test_connection
    for ip in candidates:
        try:
            ok, _ = test_connection(ip, port, password, force_udp=force_udp, brand=brand)
        except Exception:
            ok = False
        if ok:
            return ip
    return None


def _candidate_subnets(last_known_ip):
    subnets = []
    if last_known_ip:
        subnets.append(f"{'.'.join(last_known_ip.split('.')[:3])}.0/24")
    for s in _local_subnets():
        if s not in subnets:
            subnets.append(s)
    return subnets


def scan_for_device(last_known_ip, port, password, force_udp, brand):
    """Port-scan candidate subnets and verify with real credentials.

    Tries the device's last-known subnet first (most likely — DHCP usually
    reassigns within the same pool), then this machine's own local
    subnet(s) as a secondary guess. Returns the verified IP, or None.
    """
    for subnet in _candidate_subnets(last_known_ip):
        candidates = _scan_subnet_for_port(subnet, port)
        if not candidates:
            continue
        found = _verify_and_pick(candidates, port, password, force_udp, brand)
        if found:
            return found
    return None


# ── Combined recovery ───────────────────────────────────────────────────────

def recover_device_ip(device, mac_address=None):
    """Try every available method to find the device's current IP; persist it if found.

    device: a devices-table row dict (needs id, ip, port, password, brand, force_udp).
    Returns the new IP on success, or None if every method was exhausted.
    """
    mac_address = mac_address or device.get("mac_address")

    ip = find_ip_for_mac(mac_address)
    if not ip:
        refresh_arp_cache()
        ip = find_ip_for_mac(mac_address)

    if not ip:
        ip = scan_for_device(
            device.get("ip"),
            device["port"],
            device["password"],
            bool(device.get("force_udp", 0)),
            device.get("brand", "essl"),
        )

    if ip:
        db.update_device_ip(device["id"], ip)
    return ip
