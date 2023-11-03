#!/usr/bin/python3
from common import server
from common import clitools
import time

cli = clitools.Commands()

srv = server.SimpleDaemon()

@srv.worker()
def simple_worker_1(context):
    while context.stay_alive:
        print("Haddo, idzme! %s!" % (1))
        time.sleep(0.2)

@srv.worker()
def simple_worker_2(context):
    print("Haddo, idzme! %s!" % (2))
    time.sleep(10)

cli.serve(srv)
