#!/usr/bin/python
try:
    import json
except ImportError:
    import simplejson as json

import optparse
import sys
import md5

class LogMonitor(object):
    """
    In the cached file, we store the following
    Offset : The starting offset of where we should read from.
    Checkum : md5 hash of the file content from [index 0, offset)
    """

    CACHED_FILE_TMP = "%(root_path)s/%(log_filename)s_logmonitor_cached.dat"

    def __init__(self, log_filename, cached_path):
        self.log_filename = log_filename
        self.cached_filename = self.CACHED_FILE_TMP % {
            'root_path' : cached_path,
            'log_filename' : log_filename.split("/")[-1].split(".")[0],
        }


    def _store_state(self, new_offset):
        """
        Make sure that the creation time does match.
        If not, restart the offset from zero.
        """
        cached_dict = {
            'offset' : new_offset,
            'checksum' : self._gen_checksum(new_offset)
        }
        json_str = json.dumps(cached_dict)
        with open(self.cached_filename, "w") as f:
            f.write(json_str)


    def _gen_checksum(self, offset):
        with open(self.log_filename, "r") as f:
            content = f.read(offset)
            m = md5.new(content)
            m.update(content)
            return m.hexdigest()


    def _recover(self):
        """
        Basically, it checks to see if the checksum is correct.
        If not, reset the offset from zero.
        """
        offset = 0
        try:
            with open(self.cached_filename, "r") as f:
                cached_dict = json.loads(f.read())
                offset = cached_dict['offset']
                checksum = cached_dict['checksum']

                if checksum != self._gen_checksum(offset):
                    offset = 0
        except IOError:
            offset = 0
        return offset


    def _monitor(self, offset):
        byte_cnt = 0
        with open(self.log_filename, "r") as f:
            f.seek(offset)
            for line in f:
                byte_cnt += len(line)
                print line

        #if byte_cnt > 0:
        self._store_state(offset + byte_cnt)



    def run(self):
        offset = self._recover()
        self._monitor(offset)


if __name__ == "__main__":
    parser = optparse.OptionParser(description='Log monitoring intended to be used by nagios, ie. it does not run as a daemon')
    parser.add_option('--log', dest='log_file', type=str, help="The name of the log file you wish to monitor")
    parser.add_option('--cached_path', dest='cached_path', type=str, default="/tmp", help="The location where the log monitor stores its states.")

    options, args = parser.parse_args()


    if options.log_file is None:
        print "Must supply the --log argument"
        sys.exit(1)

    try:
        lm = LogMonitor(options.log_file, options.cached_path)
        lm.run()
    except Exception, e:
        print "CRITICAL - %s" % e
        sys.exit(3)
