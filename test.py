#!/usr/bin/python2
import os, sys
from geoip_simple import Geo

if __name__ == '__main__':
    g = Geo(os.path.join(os.path.dirname(__file__), 'data/geoip_country_asn.pyc'))
    print g.get_data(sys.argv[1])
    import time
    print "waiting for enter"
    sys.stdin.readline()
    print "attempting reload"
    g.check_reload()
    print g.get_data(sys.argv[1])
