import multiprocessing

from prometheus_client import multiprocess

from app.core.config import settings

bind = "0.0.0.0:8000"

workers = multiprocessing.cpu_count() * 2 + 1

worker_class = "uvicorn_worker.UvicornWorker"

# Fail closed: forwarded headers are ignored unless deployment explicitly lists
# the socket peers (reverse proxies) that are allowed to supply them.
forwarded_allow_ips = settings.FORWARDED_ALLOW_IPS

timeout = 120

accesslog = "-"

errorlog = "-"

loglevel = "info"


def child_exit(server, worker):
    multiprocess.mark_process_dead(worker.pid)
