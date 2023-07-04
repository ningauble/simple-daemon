#!/usr/bin/python3
from common import server
from common import clitools

cli = clitools.Commands()

srv = server.SimpleDaemon()

@srv.worker(max_iterations=0, loop_delay=1)
def simple_worker(obj):
    print("Haddo, idzme! %s!" % type(obj).__name__)

cli.serve(srv)
