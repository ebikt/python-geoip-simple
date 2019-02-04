import socket
import csv
import sys, os
import imp, py_compile
import zipfile, shutil, urllib2, time


class GeoIPCSVReader(csv.DictReader, object): # {{{
    """ DictReader which remembers its filename """
    def __init__(self, namedfile):
        self.filename = namedfile.name
        csv.DictReader.__init__(self, namedfile.f, dialect=GeoIPCSV)

class GeoIPCSV(csv.Dialect):
    """ GeoIP CSV """
    delimiter         = ','
    quotechar         = '"'
    doublequote       = True
    lineterminator    = "\n" #Currently ignored
    quoting           = csv.QUOTE_MINIMAL
    skipinitialspace  = True #Not needed
    strict            = True #Be on the safe side
# }}}

ZEROES = "\0" * 256
ONES   = "\xff" * 256
class Network(object):
    """ Represents a network parsed from GeoIP file.
        Networks are comparable for sorting and merging lists of newtorks.

        Network(item, key, family, errprefix)
        parses: socket.inet_pton(family, item["network"]) and creates network with
            `first` - first address of range
            `next`  - first address after range (or None if range ends with address space)
            `value` - content of item[key]
        thus family is one of socket.AF_INET, socket.AF_INET6
        errprefix is prepended before text of raised exception in case of parsing error
    """ # {{{
    first = None
    next  = None
    value = None

    def __init__(self, item, key, family, errprefix):
        self.first, self.next = self._parse_network(item['network'], family, errprefix)
        self.value = item[key]

    def __cmp__(self, other):
        if self.first < other.first: return -1
        if self.first > other.first: return 1
        if self.next < other.next: return 1
        if self.next > other.next: return -1
        if self.value < other.value: return -1
        if self.value > other.value: return 1
        return 0

    def _parse_network(self, netstr, family, errprefix):
        """ Returns binary representation of first address in network and first
            address after network (or None, if network spans to the end of address range)"""
        addr, bits = netstr.split('/')
        baddr = socket.inet_pton(family, addr)
        bits = int(bits)
        if not 0 <= bits <= len(baddr)*8:
            raise ValueError("%s: cannot parse network %s, bits out of range" % (errprefix, netstr))
        m = bits % 8
        bits -= m
        prefix = bits/8
        suffix = len(baddr) - prefix
        if m:
            mask = 2**(8-m)-1
            inner = ord(baddr[prefix]) & (255-mask)
            inner_lo = chr(inner)
            inner_hi = chr(inner + mask)
            suffix -= 1
        else:
            inner_lo = ''
            inner_hi = ''
        first = baddr[:prefix] + inner_lo + ZEROES[:suffix]
        last = [ord(x) for x in baddr[:prefix] + inner_hi + ONES[:suffix]]
        assert len(first) == len(last) == len(baddr)
        i = len(last)
        # increment last
        while True:
            if i > 0:
                i -= 1
                if last[i] == 255:
                    last[i] = 0
                else:
                    last[i] += 1
                    next = ''.join([ chr(x) for x in last ])
                    break
            else:
                next = None
                break
        if next and first >= next:
            raise AssertionError("Next address computation failed: %r %r" % (first, next))
        return first, next
# }}}

class NetList(object):
    """ Represents list of networks as list of tuples (first, value).
        Instead of end of network, tuple (next, None) is used. The list
        automatically merges consecutive networks with same value.
        It also includes manual iterator for merging NetList objects.

        NetList(netlist, family, valuemap)
          creates new list of networks form list of Network objects `netlist`,
          it needs to know `family`, to create first
          address of address space. Optional valuemap is translation mapping
          of values (e.g. geoname_id to country code).

        .this()     returns current tuple (startaddr, value) (or None)
        .next()     returns next tuple (startaddr, value) (or None)
        .advance()  advances internal pointer used in .this() and .next()
    """ # {{{
    l   = None
    ptr = None

    _FIRST_ADDRESS = {
        socket.AF_INET:  ZEROES[:4],
        socket.AF_INET6: ZEROES[:16]
    }

    def __init__(self, netlist, family, valuemap):
        netlist.sort()
        self.l = []
        hole = (self._FIRST_ADDRESS[family], None)
        for net in netlist:
            if not (hole[0] <= net.first < net.next):
                raise AssertionError("Assertion %r <= %r < %r failed" % (hole[0], net.first, net.next))
            if net.value is None or net.value == '':
                continue
            if valuemap:
                value = valuemap[net.value]
            else:
                value = net.value
            if net.first > hole[0]:
                self.l.append(hole)
            if len(self.l) == 0 or value != self.l[-1][1]:
                self.l.append( (net.first, value) )
            # else: merge with previous interval
            hole = (net.next, None)
        if hole[0]:
            self.l.append(hole)
        self.rewind()

    def rewind(self):
        self.ptr = 0

    def get(self, i):
        if i >= len(self.l):
            return None
        else:
            return self.l[i]

    def next(self):
        return self.get(self.ptr+1)

    def this(self):
        return self.get(self.ptr)

    def advance(self):
        self.ptr += 1
# }}}

def parse_netcsv(namedfile, family, key, valuemap):
    """
        Parses GeoIP CSV Block, needs to know `family` (socket.AF_INET or socket.AF_INET6)
        `key` is column to retrieve values from
        `valuemap` is optional translation dictionary of values
        `prefix` + `fname` is path of parsed file
    """ # {{{

    rn = GeoIPCSVReader(namedfile)
    ret = list()
    for item in rn:
        net = Network(item, key, family, rn.filename)
        ret.append(net)
    return NetList(ret, family, valuemap)
# }}}

def merge_lists(*lists):
    """
        Merges NetList objects into array of tuples (first_address, value, value, ...),
        so the final tuple of values can be found with single search.
    """ # {{{

    #safe and fast removal of lists
    active = set(range(len(lists)))
    for l in lists:
        l.rewind()
    current_address = ZEROES[:len(lists[0].this()[0])]
    for l in lists:
        assert l.this()[0] == current_address

    ret = []
    while True:
        ret.append( tuple( sum([list(l.this()[1:]) for l in lists],  [current_address])))
        for i in list(active):
            if lists[i].next() is None:
                active.remove(i)
        if len(active) == 0:
            break
        current_address = min([lists[i].next()[0] for i in active])
        for i in active:
            if lists[i].next()[0] == current_address:
                lists[i].advance()
            else:
                assert lists[i].next()[0] > current_address
    return ret
# }}}

class RawNamedFile(object):
    name = None
    f    = None
    def __init__(self, f, name):
        self.f = f
        self.name = name

class NamedFile(RawNamedFile): # {{{
    def __init__(self, prefix, filename):
        self.name = "%s%s" % (prefix, filename)
        self.f = open(self.name, "rb")
# }}}

class GeoZipFile(object): # {{{
    def __init__(self, filename):
        self.f = zipfile.ZipFile(filename)
        self.name = filename

    def open(self, filename):
        for member in self.f.namelist():
            if member.endswith(filename):
                return RawNamedFile(self.f.open(member), "%s:%s" % (self.name, member))
        raise IOError(os.errno.ENOENT , "File %s not found in zip file %s" %(filename, self.name) )
# }}}

def country_asn(cy_zip_name, asn_zip_name, output_path):
    cy_zip = GeoZipFile(cy_zip_name)
    asn_zip = GeoZipFile(asn_zip_name)

    countries = dict()
    rc = GeoIPCSVReader(cy_zip.open('/GeoLite2-Country-Locations-en.csv'))
    for item in rc:
        if item['geoname_id'] in countries:
            raise ValueError('%s: Duplicate location %s' % (rc.filename, item['geoname_id']))
        countries[item['geoname_id']] = item['country_iso_code']
    # add possible overrides here

    TMPNAME = "/tmp/geocompile.%d.tmp.py" % (os.getpid(),)
    out = open(TMPNAME, 'w')

    for desc, family in [('IPv4',socket.AF_INET), ('IPv6', socket.AF_INET6)]:
        asn = parse_netcsv(
                asn_zip.open('/GeoLite2-ASN-Blocks-' + desc + '.csv'),
                family, 'autonomous_system_number', None)
        cy  = parse_netcsv(
                cy_zip.open('/GeoLite2-Country-Blocks-' + desc + '.csv'),
                family, 'geoname_id', countries)
        data = merge_lists(asn, cy)
        out.write(desc.lower() + "_a = [\n")
        for a in data:
            addr = [ "\\x%02x" % ord(x) for x in a[0] ]
            out.write('  b"%s",\n' % (''.join(addr),))
        out.write("]\n")
        out.write(desc.lower() + "_v = [\n")
        for a in data:
            out.write('  %r,\n' % (a[1:],))
        out.write("]\n")

    out.write('none = (None, None)\n')
    out.write('value_names = ("asn", "country")\n')
    out.close()
    py_compile.compile(TMPNAME)
    COPYTMP = '%s.%d.tmp' % (output_path, os.getpid())
    shutil.move(TMPNAME + 'c', COPYTMP)
    os.remove(TMPNAME)
    os.rename(COPYTMP, output_path)

def download(url, path, name, proxy):
    """ Return true if downloaded file differs from previous. """
    class NotModifiedHandler(urllib2.ProxyHandler):
        def __init__(self):
            if proxy:
                urllib2.ProxyHandler.__init__(self, {'http':proxy, 'https':proxy})
            else:
                urllib2.ProxyHandler.__init__(self, {})

        def http_error_304(self, req, fp, code, message, headers):
            addinfourl = urllib2.addinfourl(fp, headers, req.get_full_url())
            addinfourl.code = code
            return addinfourl

    assert '/' not in name
    output_name = os.path.join(path, name)

    req = urllib2.Request(url.rstrip('/') + '/' + name)
    try:
        last_modified = os.stat(output_name).st_mtime
    except Exception:
        last_modified = None
    if last_modified is not None:
        last_modified = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(last_modified))
        req.add_header('If-Modified-Since', last_modified)

    opener = urllib2.build_opener(NotModifiedHandler())
    url_handle = opener.open(req)
    headers = url_handle.info()

    if hasattr(url_handle, 'code') and url_handle.code == 304:
        print '%s not modified since %s' % (name, last_modified)
        return False

    data = url_handle.read()

    try:
        old_data = open(output_name, 'rb')
    except Exception:
        old_data = None
    if old_data == data:
        print "%s data are equal"
        return False

    server_filename = name
    for disposition in headers['Content-Disposition'].split(';'):
        if '=' in disposition:
            k, v = disposition.split('=',1)
            if k.strip().lower() == 'filename':
                v = v.strip()
                if name.rsplit('.')[-1].lower() == v.rsplit('.')[-1].lower():
                    server_filename = v
    inc = 0
    save_name = os.path.join(datadir, server_filename)
    while os.path.exists(save_name):
        inc += 1
        save_name = os.path.join(datadir, "%s.%d" % (server_filename, inc))
    print "Saving new version of %s into %s" % (name, server_filename)

    f = open(save_name, "wb")
    f.write(data)
    f.close()
    try:
        os.unlink(output_name)
    except OSError as e:
        if e.errno != os.errno.ENOENT:
            raise
    os.symlink(os.path.basename(save_name), output_name)
    return True


if __name__ == '__main__':
    output      = 'geoip_country_asn.pyc'
    country_zip = 'GeoLite2-Country-CSV.zip'
    asn_zip     = 'GeoLite2-ASN-CSV.zip'
    url         = 'https://geolite.maxmind.com/download/geoip/database/'
    if os.getuid() == 0:
        datadir = '/var/lib/python-geoip-simple/'
        if not os.path.exists(datadir):
            os.mkdir(datadir)
    else:
        datadir = os.path.join(os.path.dirname(__file__), '../data/')

    if len(sys.argv) > 1:
        if sys.argv[1] == 'compile':
            compile_only = True
        else:
            proxy = sys.argv[1]
            compile_only = False
    else:
        proxy = None
        compile_only = False

    if not compile_only:
        changed = not os.path.exists(os.path.join(datadir, output))
        if download(url, datadir, country_zip, proxy): changed = True
        if download(url, datadir, asn_zip, proxy): changed = True
    else:
        changed = True

    if changed:
        print "Compiling new version of %s" % (output,)
        country_asn(os.path.join(datadir,country_zip), os.path.join(datadir, asn_zip), os.path.join(datadir, output))
