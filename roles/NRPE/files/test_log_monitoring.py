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


    def teardown(self):
        log_file_lst = self._gen_log_file_lst()
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


    def _rotate_log(self):
        """
        mv test.log to test.log.0
        recreate test.log
        """
        os.rename(self.lm.log_filename, "%s.0"%self.lm.log_filename)
        new_log_fh = open(self.lm.log_filename, "w+")
        new_log_fh.close()


    def _gen_log_file_lst(self):
        file_lst_tmpl = ["%s.1", "%s.0", "%s"]
        file_lst = [x % self.lm.log_filename for x in file_lst_tmpl]
        return file_lst


    def test__get_logrotated_log(self):
        file_lst = self._gen_log_file_lst()
        for f in file_lst:
            fh = open(f, "w+")
            fh.close()
            time.sleep(1)

        log_filename = self.lm._get_logrotated_log()
        assert log_filename == "%s.0" % self.lm.log_filename, "Should be returning [log_filename].0"


    def test_detect_log_rotate(self):
        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."

        self._rotate_log()
        logrotated, offset = self.lm._restore_state(self.lm.log_filename)
        assert logrotated == True, "Should've detected log rotate."


    def get_cached_info_helper(self):
        fh = open(self.lm.cached_filename, "r")
        return json.loads(fh.read())


    def test_handle_log_rotate_no_error(self):
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
        self._rotate_log()
        status_code = self.lm._run_impl()
        curr_cached_info = self.get_cached_info_helper()

        assert curr_cached_info['offset'] == 0, "Just started a new empty log file, so the new offset should be zero."

        assert curr_cached_info['checksum'] != old_cached_info['checksum']
        assert status_code == 0, "The OK statement should've cleared the error status code."


    def test_handle_log_rotate_ok_old_error_new(self):
        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."
        old_cached_info = self.get_cached_info_helper()
        assert old_cached_info['offset'] > 0, "The old offset should be > 0."

        self._rotate_log()
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert status_code == 3, "Encountered an error in the log file. Status code should be 3."

    def test_handle_log_rotate_error_old_ok_new(self):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "The OK statement should've cleared the error status code."

        log_fh = self._setup_log()
        self._inject_ok(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()
        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 0, "The OK statement should've cleared the error status code."
