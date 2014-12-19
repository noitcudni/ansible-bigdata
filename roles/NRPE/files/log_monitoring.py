#!/usr/bin/python
try:
    import json
except ImportError:
    import simplejson as json

import optparse
import sys
import md5
import re
import time
import glob
import os

class LogMissingException(Exception):
    def __init__(self, message):
        super(LogMissingException, self).__init__(message)


class LogMonitor(object):
    """
    In the cached file, we store the following
    Offset : The starting offset of where we should read from.
    Checkum : md5 hash of the file content from [index 0, offset)
    """

    CACHED_FILE_TMP = "%(root_path)s/logmonitor_%(log_filename)s_cached.dat"

    def __init__(self, log_filename, cached_path,
            warning_pattern=None, critical_pattern=None, ok_pattern=None, rotation_pattern=None):
        self.log_filename = log_filename
        self.cached_filename = self.CACHED_FILE_TMP % {
            'root_path' : cached_path,
            'log_filename' : log_filename.split("/")[-1].split(".")[0],
        }

        self.warning_pattern_regex = None
        if warning_pattern is not None:
            self.warning_pattern_regex = re.compile(warning_pattern)

        self.critical_pattern_regex = None
        if critical_pattern is not None:
            self.critical_pattern_regex = re.compile(critical_pattern)

        self.ok_pattern_regex = re.compile(ok_pattern)
        self.rotation_pattern = rotation_pattern

        self.warning_lst = []
        self.critical_lst = []



    def _store_state(self, new_offset):
        """
        Make sure that the creation time does match.
        If not, restart the offset from zero.
        """
        cached_dict = {
            'offset' : new_offset,
            'checksum' : self._gen_checksum(self.log_filename, new_offset)
        }

        if len(self.critical_lst) > 0:
            cached_dict['critical_lst'] = self.critical_lst
        if len(self.warning_lst) > 0:
            cached_dict['warning_lst'] = self.warning_lst

        json_str = json.dumps(cached_dict)
        with open(self.cached_filename, "w+") as f:
            f.write(json_str)


    def _gen_checksum(self, log_filename, offset):
        try:
            with open(self.log_filename, "r") as f:
                content = f.read(offset)
                m = md5.new(content)
                m.update(content)
                return m.hexdigest()
        except IOError:
            raise LogMissingException("%s log is missing" % self.log_filename)


    def _get_logrotated_log(self):
        """
        Get the most recently rotated log
        """
        file_lst = glob.glob(self.rotation_pattern)
        file_lst.remove(self.log_filename)

        stat_lst = [(os.stat(x).st_mtime, x) for x in file_lst]
        r_tuple = reduce(lambda a,b: a if (a[0] > b[0]) else b, stat_lst)

        return r_tuple[1]


    def _restore_state(self, log_filename):
        """
        Basically, it checks to see if the checksum is correct.
        If not, reset the offset from zero.
        Returns : log_rotated (Boolean), offset (int)
        """
        log_rotated = False
        offset = 0
        try:
            with open(self.cached_filename, "r") as f:
                cached_dict = json.loads(f.read())
                offset = cached_dict['offset']
                checksum = cached_dict['checksum']

                if checksum != self._gen_checksum(log_filename, offset):
                    # Got log rotated
                    offset = 0
                    log_rotated = True
                if 'critical_lst' in cached_dict:
                    self.critical_lst = cached_dict['critical_lst']
                if 'warning_lst' in cached_dict:
                    self.warning_lst = cached_dict['warning_lst']

        except IOError:
            offset = 0
        return log_rotated, offset


    def _monitor(self, offset, log_filename):
        byte_cnt = 0
        curr_t = int(time.time())
        with open(self.log_filename, "r") as f:
            f.seek(offset)
            for line in f:
                byte_cnt += len(line)
                print line

                if self.ok_pattern_regex.match(line):
                    # clear previous warnings and errors
                    self.warning_lst = []
                    self.critical_lst = []

                if self.warning_pattern_regex.match(line):
                    self.warning_lst.append({
                        'time': curr_t,
                        'content' : line,
                    })
                if self.critical_pattern_regex.match(line):
                    self.critical_lst.append({
                        'time': curr_t,
                        'content' : line,
                    })

        self._store_state(offset + byte_cnt)


    def _tally_results(self):
        status_code = 0 #OK
        if len(self.critical_lst) > 0:
            status_code = 3
        elif len(self.warning_lst) > 0:
            status_code = 2


        # TODO: The following if else block needs to be removed
        if status_code == 0:
            print "OK"
        else:
            for x in self.critical_lst:
               print "CRITICAL - %s" %  x['content']
            for x in self.warning_lst:
               print "WARNING - %s" %  x['content']

        return status_code


    def _run_impl(self):
        logrotated, offset = self._restore_state(self.log_filename)

        if logrotated is True:
            # read in the previously rotated log first.
            rotated_log_filename = self._get_logrotated_log()
            self._monitor(offset, rotated_log_filename)
            # reset the offset to zero and read in the current log file.
            self._monitor(0, self.log_filename)
        else:
            self._monitor(offset, self.log_filename)

        status_code = self._tally_results()
        return status_code


    def run(self):
        status_code = self._run_impl()
        sys.exit(status_code)


if __name__ == "__main__":
    parser = optparse.OptionParser(description='Log monitoring intended to be used by nagios, ie. it does not run as a daemon')
    parser.add_option('--log', dest='log_file', type=str, help="The name of the log file you wish to monitor")
    parser.add_option('--cached_path', dest='cached_path', type=str, default="/tmp", help="The location where the log monitor stores its states.")
    parser.add_option('--warning_pattern', dest='warning_pattern', type=str, help="A regular expression that will trigger a critical error. To filter more than one expression use or")
    parser.add_option('--critical_pattern', dest='critical_pattern', type=str, help="A regular expression that will trigger a warning. To filter more than one expression use or")
    parser.add_option('--ok_pattern', dest='ok_pattern', type=str, help="A regular expression that resets all the warnings and errors.")
    parser.add_option('--rotation_pattern', dest='rotation_pattern', type=str, help="A regular expression that describes the commonality among the current log file and the rotated log files.")

    options, args = parser.parse_args()

    if options.log_file is None:
        print "must supply the --log argument"
        sys.exit(3)

    if options.warning_pattern is None and options.critical_pattern is None:
        print "must supply ethier the --warning_pattern argument or the critical_pattern argument."
        sys.exit(3)

    if options.ok_pattern is None:
        print "must supply the --ok_pattern argument"
        sys.exit(3)

    try:
        lm = LogMonitor(
            options.log_file, options.cached_path, options.warning_pattern,
            options.critical_pattern, options.ok_pattern, options.rotation_pattern )
        lm.run()
    except Exception, e:
        print "FAILURE - %s" % e
        sys.exit(3)
