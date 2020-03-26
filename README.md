GEOIP-SIMPLE
============

Simple GeoIP database for python, implemented in native python code.

This small library downloads zipped CSV files from MaxMind and compiles them
into native python code (just four python lists provided as compiled (.pyc) module).
It also provides function that parses address (using _socket.inet\_pton_)
and runs simple binary search (using _bisect_ module) on data to return geoip
information. (Currently country code and ASN number only, but this can be easily extended.)

SYNOPSIS
--------

`python -m geoip_simple.download <proxy>` downloads data from MaxMind and compiles them. `<proxy>` is optional
address of http/https proxy.

_New in version 0.2:_ your lincense key must be stored in `maxmind.lic` file.

Correct location is /etc/python_geoip_simple/maxmind.loc when downloading as root.
Or you can provide other file by specifying path in environment variable LICENSE_FILE.

Usage:
```
from geoip_simple import Geo

g = Geo()

asn, country = g.get_data('8.8.8.8')
asn, country = g.get_data('2a00:1450:4014:801::200e')

g.check_reload() # tries to reload data files if mtime has changed
```
  

TODO
----
 * python3 support (should be simple)
 * other fields than country code and asn (naming schema of datafiles)

