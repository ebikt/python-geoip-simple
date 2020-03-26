import bisect, socket
import os, sys, imp

DEFAULT_PATH=os.getenv('GEOIP_COUNTRY_ASN_PYC', '/var/lib/python-geoip-simple/geoip_country_asn.pyc')

class Geo(object):
    _instances = dict()
    _counter = 0
    data = None
    def __new__(cls, path = DEFAULT_PATH):
        """ Return instance that corresponds to path """
        if path not in cls._instances:
            cls._counter += 1
            cls._instances[path] = object.__new__(cls, path)
        return cls._instances[path]

    def __init__(self, path = DEFAULT_PATH):
        f = open(path, 'r')
        self.path = path
        self.name = "geoip_data_%d" % self._counter
        self.mtime = os.fstat(f.fileno()).st_mtime
        self.data = imp.load_module(self.name, f, path, ("pyc","rb",imp.PY_COMPILED))

    def check_reload(self):
        try:
            f = open(self.path, 'r')
            m = os.fstat(f.fileno()).st_mtime
            if m == self.mtime:
                return
        except Exception:
            return
        self.data = imp.load_module(self.name, f, self.path, ("pyc", "rb", imp.PY_COMPILED))
        self.mtime = m

    def get_data(self, ip):
        try:
            if ':' in ip:
                baddr = socket.inet_pton(socket.AF_INET6, ip)
                keys   = self.data.ipv6_a
                values = self.data.ipv6_v
            else:
                baddr = socket.inet_pton(socket.AF_INET, ip)
                keys   = self.data.ipv4_a
                values = self.data.ipv4_v
        except Exception:
            return self.data.none
        i = bisect.bisect_right(keys, baddr) - 1
        if i >= 0:
            return values[i]
        else:
            return self.data.none

    def get_headers(self):
        return self.data.value_names
