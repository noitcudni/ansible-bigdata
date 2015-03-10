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
import gzip
import bz2

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

    MAGIC_DICT = {
        "\x1f\x8b\x08": "gz",
        "\x42\x5a\x68": "bz2",
    }
    MAX_FILE_HEADER_LEN = max(len(x) for x in MAGIC_DICT.keys())

    @classmethod
    def get_file_type(cls, filename):
        """
        Assume that if the log file isn't in gz nor bz2 format,
        it has to be uncompressed.
        """
        with open(filename) as f:
            file_header = f.read(cls.MAX_FILE_HEADER_LEN)
        for magic, filetype in cls.MAGIC_DICT.items():
            if file_header.startswith(magic):
                return filetype
        return "uncompressed"


    def __init__(self, log_filename, cached_path,
            warning_pattern=None, critical_pattern=None, ok_pattern=None, rotation_pattern=None, log_prefix=None):
        self.log_filename = log_filename

        cached_filename_args = {
            'root_path' : cached_path,
        }
        self.log_prefix = log_prefix

        if log_prefix is not None:
            cached_filename_args['log_filename'] = "_".join(log_prefix.split("/"))
        else:
            cached_filename_args['log_filename'] = log_filename.split("/")[-1].split(".")[0]

        self.cached_filename = self.CACHED_FILE_TMP % cached_filename_args


        #self.cached_filename = self.CACHED_FILE_TMP % {
            #'root_path' : cached_path,
            #'log_filename' : log_filename.split("/")[-1].split(".")[0],
        #}

        self.warning_pattern_regex = None
        if warning_pattern is not None:
            self.warning_pattern_regex = re.compile(warning_pattern)

        self.critical_pattern_regex = None
        if critical_pattern is not None:
            self.critical_pattern_regex = re.compile(critical_pattern)

        if ok_pattern is not None:
            self.ok_pattern_regex = re.compile(ok_pattern)
        else:
            self.ok_pattern_regex = None

        self.rotation_pattern = rotation_pattern

        self.warning_lst = []
        self.critical_lst = []


    @property
    def curr_log_filename(self):
        if self.rotation_pattern is not None and self.log_filename is None:
            return self._get_current_log()
        else:
            return self.log_filename



    def _store_state(self, new_offset):
        """
        Make sure that the creation time does match.
        If not, restart the offset from zero.
        """
        cached_dict = {
            'offset' : new_offset,
            'checksum' : self._gen_checksum(self.curr_log_filename, new_offset)
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
            with open(log_filename, "r") as f:
                content = "%s|%s" % (log_filename, f.read(offset))
                m = md5.new(content)
                m.update(content)
                return m.hexdigest()
        except IOError:
            raise LogMissingException("%s log is missing" % log_filename)


    def _get_log_from_logrotation(self, current_log):
        """
        Get the most recently rotated log if current_log == False.
        If current_log == true, return the current log.
        """
        try:
            if self.log_filename is None:
                log_path_prefix = self.log_prefix
            else:
                log_path_prefix = "/".join(self.log_filename.split("/")[:-1])
                if self.rotation_pattern is not None:
                    log_path_prefix = log_path_prefix + "/" + self.rotation_pattern

                if len(log_path_prefix) == 0:
                    log_path_prefix = "."


            file_lst = []
            if self.rotation_pattern is not None:
                file_lst = [x for x in glob.glob(log_path_prefix) if re.search(self.rotation_pattern, x) and os.path.isfile(x)]

            if self.log_filename is not None and \
               self.log_filename not in set(file_lst):
                file_lst.append(self.log_filename)

            if len(file_lst) == 0:
                return None

            stat_lst = [(os.stat(x).st_mtime, x) for x in file_lst]
            sorted_stat_lst = sorted(stat_lst, key=lambda x: x[0])
            sorted_stat_lst.reverse()

            if current_log == True:
                return sorted_stat_lst[0][1]
            else:
                # return just log rotated log
                if len(sorted_stat_lst) > 1:
                    return sorted_stat_lst[1][1]
                else:
                    return sorted_stat_lst[0][1] #possible that the log file just truncated.
        except OSError, e :
            raise LogMissingException("%s log is missing" % e.filename)


    def _get_current_log(self):
        return self._get_log_from_logrotation(current_log=True)


    def _get_logrotated_log(self):
        return self._get_log_from_logrotation(current_log=False)


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


    def _monitor_impl(self, offset, fh):
        fh.seek(offset)
        curr_t = int(time.time())
        byte_cnt = 0

        # if ok_pattern is ommitted, don't keep old errors and warnings around.
        # start anew.
        if self.ok_pattern_regex is None:
            self.warning_lst = []
            self.critical_lst = []

        for line in fh:
            byte_cnt += len(line)

            if self.ok_pattern_regex is not None and self.ok_pattern_regex.search(line):
                # clear previous warnings and errors
                self.warning_lst = []
                self.critical_lst = []

            if self.warning_pattern_regex is not None and self.warning_pattern_regex.search(line):
                self.warning_lst.append({
                    'time': curr_t,
                    'content' : line,
                })

            if self.critical_pattern_regex is not None and self.critical_pattern_regex.search(line):
                self.critical_lst.append({
                    'time': curr_t,
                    'content' : line,
                })
        return byte_cnt


    def _monitor(self, offset, log_filename):
        ext_type = LogMonitor.get_file_type(log_filename)

        if ext_type == 'uncompressed':
            with open(log_filename, "r") as f:
                byte_cnt = self._monitor_impl(offset, f)
        elif ext_type == 'gz':
            with gzip.open(log_filename, "r") as f:
                byte_cnt = self._monitor_impl(offset, f)
        elif ext_type == 'bz2':
            with bz2.BZ2File(log_filename, 'r') as f:
                byte_cnt = self._monitor_impl(offset, f)

        self._store_state(offset + byte_cnt)


    def _print_content(self, lst):
        for x in lst:
            print x['content']


    def _tally_results(self):
        status_code = 0 #OK
        if len(self.critical_lst) > 0:
            status_code = 2
            self._print_content(self.critical_lst)
        elif len(self.warning_lst) > 0:
            status_code = 1
            self._print_content(self.warning_lst)
        else:
            print "OK"
        return status_code


    def _run_impl(self):
        # if the log file is missing, just return OK?
        if self.curr_log_filename is None:
            print "The actual log file is missing."
            return 0

        logrotated, offset = self._restore_state(self.curr_log_filename)
        # if logrotated is returned as True, it's very likely that a log rotation has happened.

        if self.rotation_pattern is not None:
            if logrotated is True:
                # read in the previously rotated log first.
                rotated_log_filename = self._get_logrotated_log()
                if rotated_log_filename is not None:
                    self._monitor(offset, rotated_log_filename)

                # reset the offset to zero and read in the current log file.
                self._monitor(0, self.curr_log_filename)
            else:
                self._monitor(offset, self.curr_log_filename)
        else:
            # assume that no log rotate, but somehow the file has changed.
            # Read from the beginning.
            self._monitor(0, self.curr_log_filename)

        status_code = self._tally_results()
        return status_code


    def run(self):
        status_code = self._run_impl()
        sys.exit(status_code)



if __name__ == "__main__":
    """
    Description:
    This module stores previous error and warning conditions on disk in between runs. The first thing it does upon invocation is to restore those saved states.
    If no new log entires match the --ok_pattern, The previous error and warning conditions will get alerted again.

    Example: ./log_monitoring.py --log /tmp/test.log --warning_pattern "^WARN*"  --critical_pattern "^FATAL*" --ok_pattern "^SUCCESS*" --rotation_pattern "test.log*"

    log_monitoring.py --log_prefix=/opt/data/stage02/data_ingestion/log/err/cmp* --critical_pattern "error|err|Err|Error|ERROR|FAIL|fail|Fail|Failure|FAILURE|failure" --cached_path /home/lc024q/local/tmp --rotation_pattern cmp[0-9]{8}.log

    log_monitoring.py --log_prefix=/opt/data/stage02/data_ingestion/log/err/wifi_phone* --critical_pattern "error|err|Err|Error|ERROR|FAIL|fail|Fail|Failure|FAILURE|failure" --cached_path /home/lc024q/local/tmp --rotation_pattern wifi_phone[0-9]{8}.log

    If --log is not present but --rotation_pattern is supplied, it assumes that the current log's name doesn't stay constant. For instance, foo-[timestamp].log.
    If --log is present and --rotation_pattern is supplied, it assumes that the current log is constant, while the log rotated logs are described by --rotation_pattern.

    """
    parser = optparse.OptionParser(description='Log monitoring intended to be used by nagios, ie. it does not run as a daemon')
    parser.add_option('--log', dest='log_file', type=str, help="The name of the log file you wish to monitor")
    parser.add_option('--cached_path', dest='cached_path', type=str, default="/tmp", help="The location where the log monitor stores its states.")
    parser.add_option('--warning_pattern', dest='warning_pattern', type=str, help="A regular expression that will trigger a critical error. To filter more than one expression use or")
    parser.add_option('--critical_pattern', dest='critical_pattern', type=str, help="A regular expression that will trigger a warning. To filter more than one expression use or")
    parser.add_option('--ok_pattern', dest='ok_pattern', type=str, help="A regular expression that resets all the warnings and errors. If ok_pattern is ommitted, it will not fire off old errors.")
    parser.add_option('--rotation_pattern', dest='rotation_pattern', type=str, help="A regular expression that describes the commonality among the current log file and the rotated log files.")
    parser.add_option('--log_prefix', dest='log_prefix', type=str, help="If there isn't a constant current log file, ie. no --log but with --rotation_pattern. Think ls")

    options, args = parser.parse_args()

    if options.log_file is None and options.rotation_pattern is None:
        print "must supply the --log argument or the --rotation_pattern argument"
        sys.exit(2)

    if options.log_file is None and options.rotation_pattern is not None and options.log_prefix is None:
        print "with --rotation_pattern and no --log argument, you must also supply --log_prefix"
        sys.exit(2)

    if options.warning_pattern is None and options.critical_pattern is None:
        print "must supply ethier the --warning_pattern argument or the critical_pattern argument."
        sys.exit(2)

    try:
        lm = LogMonitor(
            options.log_file, options.cached_path, options.warning_pattern,
            options.critical_pattern, options.ok_pattern, options.rotation_pattern, options.log_prefix)
        lm.run()
    except Exception, e:
        print "FAILURE - %s" % e
        sys.exit(2)
