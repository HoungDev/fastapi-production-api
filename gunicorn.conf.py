import multiprocessing

from prometheus_client import multiprocess

bind = "0.0.0.0:8000"

workers = multiprocessing.cpu_count() * 2 + 1

worker_class = "uvicorn_worker.UvicornWorker"

timeout = 120

accesslog = "-"

errorlog = "-"

loglevel = "info"


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
