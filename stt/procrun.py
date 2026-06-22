"""Run the pipeline in a child process, streaming events back over a queue.

MLX/Metal GPU work crashes (SIGILL) when it runs on a worker *thread* while a
Qt/Cocoa event loop is live on the main thread. The GUI therefore runs the
pipeline in a separate *process* (which has no Qt loop) and forwards
progress/segment/log events back over a multiprocessing queue. The Qt side lives
in `stt/gui/worker.py`; this module is intentionally Qt-free so the child process
never imports PySide6.

Queue protocol — each item is a ``(kind, payload)`` tuple:
``("progress", ProgressEvent)``, ``("segment", SegmentEvent)``, ``("log", str)``,
``("error", str)``, ``("done", None)``. Exactly one ``("done", None)`` is sent last.
"""

import logging

from stt import log, pipeline


class _QueueLogHandler(logging.Handler):
    """Forward log records to the parent process as ``("log", text)`` items."""

    def __init__(self, queue) -> None:
        super().__init__()
        self._queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put(("log", self.format(record)))
        except Exception:
            pass


def _attach_log_forwarding(queue) -> None:
    log.setup()  # fresh process: set level + console handler
    handler = _QueueLogHandler(queue)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", "%H:%M:%S")
    )
    log.get().addHandler(handler)


def run_pipeline(queue, stop_event, kwargs) -> None:
    _attach_log_forwarding(queue)
    try:
        pipeline.run(
            stop_event=stop_event,
            on_progress=lambda e: queue.put(("progress", e)),
            on_segment=lambda e: queue.put(("segment", e)),
            **kwargs,
        )
    except Exception as e:  # surfaced to the GUI as an error dialog
        queue.put(("error", str(e)))
    finally:
        queue.put(("done", None))


def run_reprocess(queue, stop_event, kwargs) -> None:
    _attach_log_forwarding(queue)
    try:
        pipeline.reprocess(
            stop_event=stop_event,
            on_progress=lambda e: queue.put(("progress", e)),
            **kwargs,
        )
    except Exception as e:
        queue.put(("error", str(e)))
    finally:
        queue.put(("done", None))
