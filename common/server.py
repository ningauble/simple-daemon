import atexit
import os
import sys
import time
import signal
import logging

class SimpleDaemon(object):
    """
    Very simple init.
    We can do much more things like external logger setter, config file and so on
    For nothing: 85611bf8566a9dcc0dc1e61bdf369c38
    """
    def __init__(self, pidfile='/tmp/simple_daemon.pid', logfile='/tmp/simple_daemon.log'):
        
        self.pidfile = pidfile
        self.logfile = logfile
        
        self.loop_delay = 1
        
        self.stay_alive=True
        
        self.worker_func = {
            'fn': False,
            'args': False
        }
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        log_handler = logging.FileHandler(self.logfile, mode='a')
        log_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        log_handler.setFormatter(log_formatter)
        self.logger.addHandler(log_handler)

    def daemonize(self):
        """
        Using double-fork technique.
        It will be possible to change uid and gid in the future if run under root
        """
        try:
            pid=os.fork()
            if pid>0:
                sys.exit(0)
        except os.error as e:
            self.logger.error("fork #1 failed:%d (%s)" % (e.errno, e.strerror))
            sys.exit(1)

        os.setsid()

        try:
            pid=os.fork()
            if pid>0:
                sys.exit(0)
        except os.error as e:
            self.logger.error("fork #2 failed:%d (%s)" % (e.errno, e.strerror))
            sys.exit(1)

    def store_to_pidfile(self, pid):
        """
        Here is no try/catch.
        Just because.
        """
        with open(self.pidfile, 'w') as f:
                f.write(str(pid))
    
    def has_pidfile(self) -> bool :
        return os.path.exists(self.pidfile)
    
    def drop_pidfile(self):
        if self.has_pidfile():
            try:
                os.remove(self.pidfile)
            except os.error as e:
                msg = "Can't drop pid file %s:%d (%s)" % (self.pidfile, e.errno, e.strerror)
                self.logger.error(msg)
                sys.stderr.write(msg+"\n")

    def get_pid(self) -> int :
        """
        PID of main process.
        Evil forces can drop pid-file I know.
        """
        pid = 0

        if self.has_pidfile():
            with open(self.pidfile, 'r') as f:
                pid = int( f.read().strip() )
                
        return pid

    def clear_on_exit(self):
        self.logger.info("Clear all")
        self.drop_pidfile()

    def start(self):
        
        self.logger.info("Start daemon")
        
        pid = self.get_pid()
        
        if pid>0:
            msg = "Pidfile %s exists. Still running?" % self.pidfile
            self.logger.error(msg)
            sys.stderr.write(msg+"\n")
            sys.exit(1)
        
        self.daemonize()
        
        pid = os.getpid()
        
        self.store_to_pidfile(pid)
        
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)
        
        atexit.register(self.clear_on_exit)
        
        self.worker_loop()
    
    def stop(self):
        """
        Stop from external processes.
        What will you do if pid has been eaten by a black hole and process still active?
        """
        
        pid = self.get_pid()
        
        if pid==0:
            msg = "Pidfile %s does not exist. Not running?" % self.pidfile
            self.logger.error(msg)
            sys.stderr.write(msg+"\n")
        else:
            os.kill(pid, signal.SIGTERM)
    
    def shutdown(self, signum=0, frame=False):
        """
        Stop at the same process
        """
        
        self.logger.info("Shutdown daemon with signum %s" % signum )
        self.stay_alive=False

    def restart(self):
        """
        Sugar
        """
        self.stop()
        self.start()

    def worker(self, *args, **kwargs):
        """
        Decorator magic here
        """
        def inner(callback):
            self.logger.info("New worked added: %s" % callback.__name__)
            self.worker_func['fn'] = callback
            self.worker_func['args'] = args
            self.worker_func['kwargs'] = kwargs
        return inner

    def worker_loop(self):
        """
        Main loop to iterate worker.
        Depends on posix signals and iterations counter.
        Default is max_iterations=0 to run infinite loop.
        It is possible to add a bunch of workers in the future.
        """
        
        self.logger.info("Worker loop start")
        
        iterations_counter = 0
        max_iterations = int(self.worker_func['kwargs'].get('max_iterations', 0))
        
        loop_delay = int(self.worker_func['kwargs'].get('loop_delay', self.loop_delay))
        
        while self.stay_alive:
            
            if max_iterations > 0:
                iterations_counter = iterations_counter + 1
                
            if iterations_counter > max_iterations:
                self.logger.info("Shutdown daemon on max_iterations=%s" % max_iterations )
                break
            
            self.worker_func['fn'](self)
            time.sleep(loop_delay)
            
            
        self.logger.info("Worker loop end")
