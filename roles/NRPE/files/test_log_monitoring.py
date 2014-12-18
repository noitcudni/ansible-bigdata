from log_monitoring import LogMonitor
import os

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
    ROTATION_PATTERN = ""

    def _setup_empty_log(self):
        pass


    def _setup_log(self):
        fh = open("test_monitor.log", "w")
        return fh


    def _rotate_log(self):
        pass


    def _inject_error(self, fh):
        fh.write("FATAL - %s" % "this is a fatal error message.")


    def _inject_warn(self, fh):
        fh.write("WARN - %s" % "this is a warning message.")


    def _inject_ok(self, fh):
        fh.write("SUCCESS - %s" % "yay")


    def setup(self):
        self.lm = LogMonitor(
            self.LOG_FILE, self.CACHED_PATH,
            self.WARNING_PATTERN, self.CRITICAL_PATTERN,
            self.OK_PATTERN, self.ROTATION_PATTERN,
        )


    def teardown(self):
        if os.path.isfile(self.lm.log_filename):
            os.remove(self.lm.log_filename)
        if os.path.isfile(self.lm.cached_filename):
            os.remove(self.lm.cached_filename)


    def test_log__empty_log_no_cached(self):
        log_fh = self._setup_log()
        log_fh.close()
        status_code = self.lm._run_impl()

        # no cached file should be created
        import pdb; pdb.set_trace() #xxx
        assert os.path.isfile(self.lm.cached_filename) == False, "cached file shouldn't have been created."
        assert status_code == 0, "Encountered an empty log file. Status code should be 0."


    def test_log__error_no_cached(self):
        log_fh = self._setup_log()
        self._inject_error(log_fh)
        log_fh.close()
        status_code = self.lm._run_impl()

        # a cached file should be created

        assert os.path.isfile(self.lm.cached_filename) == True, "cached file should've been created."
        assert status_code == 3, "Encountered an error in the log file. Status code should be 3."

