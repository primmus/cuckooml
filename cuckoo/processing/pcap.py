#!/usr/bin/python
# Cuckoo Sandbox - Automated Malware Analysis
# Copyright (C) 2010-2011  Claudio "nex" Guarnieri (nex@cuckoobox.org)
# http://www.cuckoobox.org
#
# This file is part of Cuckoo.
#
# Cuckoo is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Cuckoo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.

import os
import re
import sys
import socket
from urlparse import urlunparse

try:
    import dpkt
    IS_DPKT = True
except ImportError, why:
    IS_DPKT = False

class Pcap:
    """
    Network PCAP
    """
    
    def __init__(self, filepath):
        """
        Creates a new instance
        @param filepath: path to PCAP file
        """ 
        self.filepath = filepath
        self.tcp_connections = []
        self.udp_connections = []
        self.http_requests = []
        self.dns_requests = []
        self.dns_performed = []
        self.results = {}
        
    def check_http(self, tcpdata):
        """
        Checks for HTTP traffic
        @param tcpdata: tcp data flow
        """ 
        try:
            dpkt.http.Request(tcpdata)
            return True
        except dpkt.dpkt.UnpackError:
            return False
        
    def add_http(self, tcpdata, dport):
        """
        Adds an HTTP flow
        @param tcpdata: TCP data in flow
        @param dport: destination port
        """  
        http = dpkt.http.Request(tcpdata)
        
        entry = {}
        entry["host"] = http.headers['host']
        entry["port"] = dport
        entry["data"] = tcpdata
        if entry["port"] != 80:
            entry["uri"] = urlunparse(('http', "%s:%d" % (entry['host'], entry["port"]), http.uri, None, None, None))
        else:
            entry["uri"] = urlunparse(('http', entry['host'], http.uri, None, None, None))
        entry["body"] = http.body
        entry["path"] = http.uri
        entry["user-agent"] = http.headers["user-agent"]
        entry["version"] = http.version
        entry["method"] = http.method

        self.http_requests.append(entry)
        return True
    
    def check_dns(self, udpdata):
        """
        Checks for DNS traffic
        @param udpdata: UDP data flow
        """ 
        try:
            dpkt.dns.DNS(udpdata)
            return True
        except:
            return False
    
    def add_dns(self, udpdata):
        """
        Adds a DNS data flow
        @param udpdata: data inside flow
        """ 
        dns = dpkt.dns.DNS(udpdata)
        name = dns.qd[0].name
        
        if name not in self.dns_performed:
            if re.search("in-addr.arpa", name):
                return False
            # This is generated by time-sync of the virtual machine.
            if name.strip() == "time.windows.com":
                return False
            
            entry = {}
            entry["hostname"] = name

            try:
                ip = socket.gethostbyname(name)
            except socket.gaierror:
                ip = ""

            entry["ip"] = ip

            self.dns_requests.append(entry)
            self.dns_performed.append(name)
            
            return True
        return False
    
    def process(self):
        """
        Process PCAP
        @return: dict with network analysis data
        """
        if not IS_DPKT:
            return None

        if not os.path.exists(self.filepath):
            return None

        if os.path.getsize(self.filepath) == 0:
            return None

        file = open(self.filepath, "rb")

        try:
            pcap = dpkt.pcap.Reader(file)
        except dpkt.dpkt.NeedData:
            return None

        for ts, buf in pcap:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                ip = eth.data

                if ip.p == dpkt.ip.IP_PROTO_TCP:
                    tcp = ip.data

                    if len(tcp.data) > 0:
                        if self.check_http(tcp.data):
                            self.add_http(tcp.data, tcp.dport)

                        connection = {}
                        connection["src"] = socket.inet_ntoa(ip.src)
                        connection["dst"] = socket.inet_ntoa(ip.dst)
                        connection["sport"] = tcp.sport
                        connection["dport"] = tcp.dport
                          
                        self.tcp_connections.append(connection)
                    else:
                        continue
                elif ip.p == dpkt.ip.IP_PROTO_UDP:
                    udp = ip.data

                    if len(udp.data) > 0:
                        if udp.dport == 53:
                            if self.check_dns(udp.data):
                                self.add_dns(udp.data)

                        connection = {}
                        connection["src"] = socket.inet_ntoa(ip.src)
                        connection["dst"] = socket.inet_ntoa(ip.dst)
                        connection["sport"] = udp.sport
                        connection["dport"] = udp.dport

                        self.udp_connections.append(connection)
                #elif ip.p == dpkt.ip.IP_PROTO_ICMP:
                    #icmp = ip.data
            except AttributeError, why:
                continue
            except dpkt.dpkt.NeedData, why:
                continue

        file.close()

        self.results["tcp"] = self.tcp_connections
        self.results["udp"] = self.udp_connections
        self.results["http"] = self.http_requests
        self.results["dns"] = self.dns_requests
        
        return self.results
