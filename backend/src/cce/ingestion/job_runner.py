"""Durable leased job worker. Threads are executors, not the source of job truth."""

import logging
from threading import Event, Thread

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, repository, workflow, poll_seconds=2):
        self.repository = repository
        self.workflow = workflow
        self.poll_seconds = poll_seconds
        self.stop_event = Event()
        self.thread = None

    def start(self):
        self.thread = Thread(target=self._run, name="cce-job-worker", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.repository.lease_seconds + 1)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                if self.run_once():
                    continue
            except Exception:
                logger.exception("CCE job claim failed")
            self.stop_event.wait(self.poll_seconds)

    def run_once(self):
        request = self.repository.claim()
        if request is None:
            return False
        done = Event()

        def heartbeat():
            while not done.wait(max(1, self.repository.lease_seconds / 3)):
                try:
                    if not self.repository.renew(request):
                        return
                except Exception:
                    logger.exception(
                        "Lease renewal failed: ingestion_run_id=%s",
                        request.ingestion_run_id,
                    )

        thread = Thread(target=heartbeat, daemon=True)
        thread.start()
        error = None
        try:
            self.workflow.run(request)
        except Exception as exc:
            error = str(exc)
            logger.exception(
                "Ingestion job failed: ingestion_run_id=%s source_id=%s",
                request.ingestion_run_id,
                request.source_id,
            )
        finally:
            done.set()
            thread.join()
            self.repository.finish(request, error)
        return True
