import atexit
import os
import sys
import time
import signal
import logging

class SimpleDaemonContext(object):
    """
    This context object used just because we can.
    It throws to children to provide some info about parent and 
    avoid different signal handlers for processes by default (yes, you can redefine it in worker)
    """
    def __init__(self):
        
        self.__dict__['stay_alive'] = True
        self.__dict__['main_pid'] = 0
    
    def __setattr__(self, key, value):
        
        if key=='main_pid':
            if self.main_pid == 0:
                self.__dict__[key] = value
        else:
            self.__dict__[key] = value
        
    def __getattr__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            return None
    
    def __delattr__(self, name):
        if name in self.__dict__ and name not in ['stay_alive', 'main_pid']:
            del self.__dict__[name]

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
        
        self.context = SimpleDaemonContext()
        
        self.worker_func = []
        
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
        # clear all from main process only
        if os.getpid() == self.context.main_pid:
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
        
        self.context.main_pid = pid
        
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
        self.logger.info("Shutdown process %s with signum %s" % (os.getpid(), signum))
        self.context.stay_alive=False

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
            self.worker_func.append({
                'name' : callback.__name__,
                'callback' : callback,
                'args' : args,
                'kwargs' : kwargs
            })
        return inner

    """
    Do all hard work here
    """
    def worker_loop(self):
        
        self.logger.info("Workers loop start")
        
        workers = {}

        if len(self.worker_func) == 0:
            self.logger.info("Workers loop stop. Empty workers list")
            sys.exit(0)

        # main loop
        while self.context.stay_alive:
            
            while len(workers)<len(self.worker_func):
                for w in self.worker_func:
                    if w['name'] not in workers:
                        
                        try:
                            pid=os.fork()
                            
                            if pid==0:
                                w['callback'](self.context)
                                sys.exit(0)
                            elif pid>0:
                                workers[w['name']] = w
                                workers[w['name']]['pid'] = pid
                                self.logger.info("Worker %s start" % w['name'])
                            
                        except os.error as e:
                            self.logger.error("fork #1 failed:%d (%s)" % (e.errno, e.strerror))
                            sys.exit(1)
                        
            
            for w in list(workers):
                try:
                    pid, exit_code = os.waitpid(workers[w]['pid'], os.WNOHANG)
                    if pid>0:
                        workers.pop(w)
                except:
                    pass
                
            time.sleep(1)
        
        # stopping children
        self.logger.info("Stopping children")
        for w in workers:
            os.kill(workers[w]['pid'], signal.SIGTERM)
        
        # waiting children to end
        self.logger.info("Waiting children to end")
        while len(workers):
            for w in list(workers):
                try:
                    pid, exit_code = os.waitpid(workers[w]['pid'], os.WNOHANG)
                    if pid>0:
                        self.logger.info("Worker %s end" % workers[w]['name'])
                        workers.pop(w)
                except:
                    pass
            time.sleep(0.2)

        self.logger.info("Workers loop end")
