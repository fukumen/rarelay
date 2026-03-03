#!/usr/bin/env python3

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import threading
from scapy.all import Ether, ICMPv6ND_RA, ICMPv6ND_RS, ICMPv6NDOptDNSSL, ICMPv6NDOptPrefixInfo, ICMPv6NDOptRDNSS, ICMPv6NDOptSrcLLAddr, IPv6, ifaces, scapy, sendp, sniff
from config import ethsrc, ethdst, dns, searchlist, rssrc

last_ra = None
timer_ra = None
resource_lock = threading.Lock()

def send_ra_timeout(duration):
    global timer_ra

    pktsnd = None
    with resource_lock:
        pktsnd = last_ra
        timer_ra = threading.Timer(duration, send_ra_timeout, args=[duration])
        timer_ra.daemon = True
        timer_ra.start()
    if pktsnd:
        sendp(iface=ethdst, x=pktsnd, verbose=0, socket=scapy.arch.linux.L2Socket(promisc=False))

def send_ra(pktcap):
    global last_ra
    global timer_ra

    ether = Ether()
    ether.src = ifaces.dev_from_name(ethdst).mac
    ether.dst = "33:33:00:00:00:01"
    ip = IPv6()
    ip.src = pktcap[IPv6].src
    ip.dst = "ff02::1"
    ra = ICMPv6ND_RA()
    ra.M = 0
    ra.O = 0
    ra.prf = 0
    ra.chlim = pktcap[ICMPv6ND_RA].chlim
    ra.routerlifetime = pktcap[ICMPv6ND_RA].routerlifetime
    lladdr = ICMPv6NDOptSrcLLAddr()
    lladdr.lladdr = pktcap[ICMPv6NDOptSrcLLAddr].lladdr
    pktsnd = None
    if pktcap.haslayer(ICMPv6NDOptPrefixInfo):
        prefix = ICMPv6NDOptPrefixInfo()
        prefix.prefixlen = pktcap[ICMPv6NDOptPrefixInfo].prefixlen
        prefix.prefix = pktcap[ICMPv6NDOptPrefixInfo].prefix
        prefix.validlifetime = pktcap[ICMPv6NDOptPrefixInfo].validlifetime
        prefix.preferredlifetime = pktcap[ICMPv6NDOptPrefixInfo].preferredlifetime
        rdnss = ICMPv6NDOptRDNSS()
        rdnss.lifetime = pktcap[ICMPv6NDOptRDNSS].lifetime
        rdnss.dns = []
        for d in dns:
            rdnss.dns.append(pktcap[ICMPv6NDOptPrefixInfo].prefix[:-1] + d)
        dnssl = ICMPv6NDOptDNSSL()
        dnssl.lifetime = pktcap[ICMPv6NDOptRDNSS].lifetime
        dnssl.searchlist = searchlist
        pktsnd=(ether/ip/ra/prefix/rdnss/dnssl/lladdr)
        with resource_lock:
            if timer_ra:
                timer_ra.cancel()
            duration = max(30, prefix.validlifetime - 30)
            timer_ra = threading.Timer(duration, send_ra_timeout, args=[duration])
            timer_ra.daemon = True
            timer_ra.start()
            last_ra = pktsnd
    else:
        pktsnd=(ether/ip/ra/lladdr)
        with resource_lock:
            last_ra = pktsnd
    if pktsnd:
        sendp(iface=ethdst, x=pktsnd, verbose=0, socket=scapy.arch.linux.L2Socket(promisc=False))

def send_rs(pktcap, pktra):
    ether = Ether()
    ether.src = ifaces.dev_from_name(ethdst).mac
    ether.dst = pktcap[Ether].src
    ip = IPv6()
    ip.src = pktra[IPv6].src
    ip.dst = pktcap[IPv6].src
    ra = ICMPv6ND_RA()
    ra.M = 0
    ra.O = 0
    ra.prf = 0
    ra.chlim = pktra[ICMPv6ND_RA].chlim
    ra.routerlifetime = pktra[ICMPv6ND_RA].routerlifetime
    lladdr = ICMPv6NDOptSrcLLAddr()
    lladdr.lladdr = pktra[ICMPv6NDOptSrcLLAddr].lladdr
    pktsnd = None
    if pktra.haslayer(ICMPv6NDOptPrefixInfo):
        prefix = ICMPv6NDOptPrefixInfo()
        prefix.prefixlen = pktra[ICMPv6NDOptPrefixInfo].prefixlen
        prefix.prefix = pktra[ICMPv6NDOptPrefixInfo].prefix
        prefix.validlifetime = pktra[ICMPv6NDOptPrefixInfo].validlifetime
        prefix.preferredlifetime = pktra[ICMPv6NDOptPrefixInfo].preferredlifetime
        rdnss = ICMPv6NDOptRDNSS()
        rdnss.lifetime = pktra[ICMPv6NDOptRDNSS].lifetime
        rdnss.dns = []
        for d in dns:
            rdnss.dns.append(pktra[ICMPv6NDOptPrefixInfo].prefix[:-1] + d)
        dnssl = ICMPv6NDOptDNSSL()
        dnssl.lifetime = pktra[ICMPv6NDOptRDNSS].lifetime
        dnssl.searchlist = searchlist
        pktsnd=(ether/ip/ra/prefix/rdnss/dnssl/lladdr)
    else:
        pktsnd=(ether/ip/ra/lladdr)
    if pktsnd:
        sendp(iface=ethdst, x=pktsnd, verbose=0, socket=scapy.arch.linux.L2Socket(promisc=False))

def sniff_ethsrc(pktcap):
    pktra = None
    with resource_lock:
        pktra = last_ra

    if pktcap.haslayer(ICMPv6ND_RA) and pktcap[Ether].src != ifaces.dev_from_name(ethdst).mac and pktcap[Ether].dst == "33:33:00:00:00:01":
        send_ra(pktcap)
    elif rssrc == "ethsrc" and pktcap.haslayer(ICMPv6ND_RS) and pktra:
        send_rs(pktcap, pktra)

def sniff_ethdst(pktcap):
    pktra = None
    with resource_lock:
        pktra = last_ra

    if pktcap.haslayer(ICMPv6ND_RS) and pktra:
        send_rs(pktcap, pktra)

if rssrc == "ethdst":
    rs_thread = threading.Thread(target=sniff, kwargs={'iface': ethdst, 'filter': "icmp6 and ip6[40] == 133", 'prn': sniff_ethdst, 'store': 0})
    rs_thread.daemon = True
    rs_thread.start()

sniff(iface=ethsrc, filter="icmp6", prn=sniff_ethsrc, store=0)
