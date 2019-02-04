GEOIP-SIMPLE
============

Simple GeoIP database for python, implemented in native python code.

This small library downloads zipped CSV files from MaxMind and compiles them
into native python code (just four python lists provided as compiled (.pyc) module).
It also provides function that parses address (using _socket.inet\_pton_)
and runs simple binary search (using _bisect_ module) on data to return geoip
information. (Currently country code and ASN number only, but this can be easily extended.)

TODO
----
 * python3 support (should be simple)
 * other fields than country code and asn (naming schema of datafiles)

