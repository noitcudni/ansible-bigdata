try:
    import json
except ImportError:
    import simplejson as json

from log_monitoring import (
    LogMonitor,
    LogMissingException,
)
import os
import time
import gzip
import bz2

class TestLogMonitoring(object):
    """
    cd into this directory and run

    To Test everything:
    nosetests -s test_log_monitoring.py

    To run a single test:
    nosetests -s test_log_monitoring:TestLogMonitoring.<method_name>
    Example:
    nosetests -s test_log_monitoring:TestLogMonitoring.test_log__empty_log_no_cached
    """

    LOG_FILE = "test_monitor.log"
    CACHED_PATH = "."
    WARNING_PATTERN = "^WARN.*$"
    CRITICAL_PATTERN = "^FATAL.*$"
    OK_PATTERN = "^SUCCESS.*$"
    ROTATION_PATTERN = "test_monitor*"


    def _setup_log(self):
        if os.path.isfile("test_monitor.log"):
            fh = open("test_monitor.log", "a")
        else:
            fh = open("test_monitor.log", "w")
        return fh


    def _inject_innocuous_line(self, fh):
        fh.write("foo bar baz..\n")

    def _inject_error(self, fh):
        fh.write("FATAL - %s" % "this is a fatal error message.\n")


    def _inject_warn(self, fh):
        fh.write("WARN - %s" % "this is a warning message.\n")


    def _inject_ok(self, fh):
        fh.write("SUCCESS - %s" % "yay\n")


    def setup(self):
        self.lm = LogMonitor(
            self.LOG_FILE, self.CACHED_PATH,
            self.WARNING_PATTERN, self.CRITICAL_PATTERN,
            self.OK_PATTERN, self.ROTATION_PATTERN,
        )
        self.lm_no_ok_pattern = LogMonitor(
            self.LOG_FILE, self.CACHED_PATH,
            self.WARNING_PATTERN, self.CRITICAL_PATTERN,
            None, self.ROTATION_PATTERN,
        )


    def teardown(self):
        log_file_lst = self._gen_log_file_lst('all')
        for f in log_file_lst:
            if os.path.isfile(f):
                os.remove(f)
        if os.path.isfile(self.lm.cached_filename):
            os.remove(self.lm.cached_filename)


    def test_log__empty_log_no_cached(self):
        log_fh = self._setup_log()
        log_fh.close()
        status_code = self.lm._run_impl()

        # no cached file should be created
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file shouldn't have been created."
        assert status_code == 0, "Encountered an empty log file. Status code should be 0."


    def test_log__error_no_cached(self):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()

        # a cached file should be created
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "Encountered an error in the log file. Status code should be 3."


    def test_log__warn_no_cached(self):
        log_fh = self._setup_log()
        self._inject_warn(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()

        # a cached file should be created
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 2, "Encountered a warning in the log file. Status code should be 2."


    def test_log__error_with_cached(self):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()

        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "Encountered an error in the log file. Status code should be 3."

        # run monitoring again.
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "Status code should remain as 3."


    def test_log__warning_with_cached(self):
        log_fh = self._setup_log()
        self._inject_warn(log_fh)
        log_fh.close()

        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 2, "Encountered a warning in the log file. Status code should be 2."

        # run monitoring again.
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 2, "Status code should remain as 2."


    def test_log__error_with_cached_with_ok(self):
        # intermitten checks
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()

        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "Encountered an error in the log file. Status code should be 3."

        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()

        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."


    def test_log__error_with_cached_with_ok2(self):
        # check all in one go.
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        self._inject_error(log_fh)
        self._inject_ok(log_fh)
        log_fh.close()

        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."


    def test_log_without_ok_pattern(self):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm_no_ok_pattern._run_impl()

        assert status_code == 3, "Encounterd an error in the log file. Status code should be 3."
        assert os.path.isfile(self.lm_no_ok_pattern.cached_filename) == True, "cached file should've been created."

        log_fh = self._setup_log()
        self._inject_innocuous_line(log_fh)
        self._inject_innocuous_line(log_fh)
        log_fh.close()
        status_code = self.lm_no_ok_pattern._run_impl()

        assert status_code == 0, "OK_pattern is omitted. Shouldn't fire off old errors."
        assert os.path.isfile(self.lm_no_ok_pattern.cached_filename) == True, "cached file should've been created."


    def test_missing_log_file(self):
        cached_fh = open(self.lm.cached_filename, "w+")
        json_dict = {
            "offset" : 0,
            "checksum" : "DEADBEEF",
        }
        cached_fh.write(json.dumps(json_dict)) #dummy json
        cached_fh.close()

        try:
            self.lm._run_impl()
        except LogMissingException:
            assert True, "should be throw a LogMissingException."
        except Exception, e:
            assert False, "should be throw a LogMissingException, but got: %s" % e


    def _rotate_log(self, compress_type=None):
        """
        mv test.log to test.log.0
        recreate test.log
        """
        r = None
        if compress_type == None:
            r = "%s.0"%self.lm.log_filename
            os.rename(self.lm.log_filename, r)

        elif compress_type in set(['gz', 'bz2', 'zip']):
            with open(self.lm.log_filename, "r") as orig_f:
                content = orig_f.read()

            if compress_type == 'gz':
                r = '%s.0.gz'%self.lm.log_filename
                with gzip.open(r, 'wb') as gf:
                    gf.write(content)

            elif compress_type == 'bz2':
                r = '%s.0.bz2'%self.lm.log_filename
                with bz2.BZ2File(r, 'wb') as bz2f:
                    bz2f.write(content)

        new_log_fh = open(self.lm.log_filename, "w+")
        new_log_fh.close()
        return r


    def _gen_log_file_lst(self, ext=None):
        file_lst_tmpl = ["%s.1", "%s.0", "%s"]

        file_lst = [x % self.lm.log_filename for x in file_lst_tmpl]

        ext_lst = ["gz", "bz2", "zip"]
        if ext == 'all':
            file_lst += [x % self.lm.log_filename + ".%s" % y for x in file_lst_tmpl for y in ext_lst]
        elif ext in set(ext_lst):
            file_lst += [x % self.lm.log_filename + ".%s" % ext for x in file_lst_tmpl]

        return file_lst


    def test__get_logrotated_log(self):
        file_lst = self._gen_log_file_lst()
        for f in file_lst:
            fh = open(f, "w+")
            fh.close()
            time.sleep(1)

        log_filename = self.lm._get_logrotated_log()
        assert log_filename == "%s.0" % self.lm.log_filename, "Should be returning [log_filename].0"



    def _detect_log_rotate_helper(self, compression_type):
        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."

        self._rotate_log(compression_type)
        logrotated, offset = self.lm._restore_state(self.lm.log_filename)
        assert logrotated == True, "Should've detected log rotate."

    def test_detect_log_rotate(self):
        self._detect_log_rotate_helper(None)
    def test_detect_log_rotate_gz(self):
        self._detect_log_rotate_helper('gz')
    def test_detect_log_rotate_bz2(self):
        self._detect_log_rotate_helper('bz2')

    def get_cached_info_helper(self):
        fh = open(self.lm.cached_filename, "r")
        return json.loads(fh.read())


    def _handle_log_rotate_no_error_helper(self, compression_type):
        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."
        old_cached_info = self.get_cached_info_helper()
        assert old_cached_info['offset'] > 0, "The old offset should be > 0."


        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        self._rotate_log(compression_type)
        status_code = self.lm._run_impl()
        curr_cached_info = self.get_cached_info_helper()

        assert curr_cached_info['offset'] == 0, "Just started a new empty log file, so the new offset should be zero."

        assert curr_cached_info['checksum'] != old_cached_info['checksum']
        assert status_code == 0, "The OK statement should've cleared the error status code."


    def test_log_rotate_no_error_helper(self):
        self._handle_log_rotate_no_error_helper(None)
    def test_log_rotate_no_error_helper_gz(self):
        self._handle_log_rotate_no_error_helper('gz')
    def test_log_rotate_no_error_helper_bz2(self):
        self._handle_log_rotate_no_error_helper('bz2')


    def _handle_log_rotate_ok_old_error_new_helper(self, compression_type):
        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."
        old_cached_info = self.get_cached_info_helper()
        assert old_cached_info['offset'] > 0, "The old offset should be > 0."

        self._rotate_log(compression_type)
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert status_code == 3, "Encountered an error in the log file. Status code should be 3."

    def test_handle_log_rotate_ok_old_error_new(self):
        self._handle_log_rotate_ok_old_error_new_helper(None)
    def test_handle_log_rotate_ok_old_error_new_gz(self):
        self._handle_log_rotate_ok_old_error_new_helper('gz')
    def test_handle_log_rotate_ok_old_error_new_bz2(self):
        self._handle_log_rotate_ok_old_error_new_helper('bz2')

    def test_handle_log_rotate_error_old_ok_new(self):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "Should've encountered an error."

        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."


    def _test_get_file_type(self, compression_type):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        self._inject_ok(log_fh)
        log_fh.close()

        rotated_log_filename = self._rotate_log(compress_type=compression_type)
        assert LogMonitor.get_file_type(rotated_log_filename) == compression_type


    def test_get_file_type_gz(self):
        self._test_get_file_type('gz')
    def test_get_file_type_bz2(self):
        self._test_get_file_type('bz2')


    def test_handle_no_log_rotate(self):
        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        self._inject_error(log_fh)
        log_fh.close()

        status_code = self.lm._run_impl()
        assert status_code == 3, "Should've encountered an error."

        # force overwrite the current log file. No log rotation.
        log_fh = open(self.lm.log_filename, "w")
        self._inject_innocuous_line(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert status_code == 3, "Should've encountered an error."

        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert status_code == 0, "The OK statement should've cleared the error status code."



    def test_log__warn(self):
        # TODO check out test_log__error and do the warn version
        pass
