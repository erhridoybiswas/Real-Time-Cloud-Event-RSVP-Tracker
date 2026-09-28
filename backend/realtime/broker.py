"""
In-process realtime broker (Server-Sent Events).

Local/single-process: an in-memory dict of subscriber queues.
Cloud/multi-worker : swap `Broker` for a Redis Pub/Sub adapter with the same
                     publish()/subscribe() API — no route changes required.
"""
import json
import queue
import threading

# SSE keep-alive interval (seconds)
KEEPALIVE_SECONDS = 15
# Maximum queued messages per subscriber before we drop (slow consumer guard)
MAX_QUEUE = 200


class Broker:
    def __init__(self) -> None:
        self._channels: dict[str, set[queue.Queue]] = {}
        self._lock = threading.Lock()

    # -- subscription management ------------------------------------------
    def subscribe(self, channel: str) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=MAX_QUEUE)
        with self._lock:
            self._channels.setdefault(channel, set()).add(q)
        return q

    def unsubscribe(self, channel: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._channels.get(channel)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                self._channels.pop(channel, None)

    # -- publishing --------------------------------------------------------
    def publish(self, channel: str, payload: dict) -> int:
        """Fan a payload out to every subscriber of `channel` (and to '*')."""
        message = json.dumps(payload, default=str)
        with self._lock:
            targets = list(self._channels.get(channel, ()))
            if channel != "*":
                targets += list(self._channels.get("*", ()))

        delivered = 0
        for q in targets:
            try:
                q.put_nowait(message)
                delivered += 1
            except queue.Full:
                # Slow client: drop the message rather than block the writer.
                pass
        return delivered

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._channels.get(channel, ()))


broker = Broker()


def sse_format(data: str) -> str:
    """Format a single SSE frame. `data` must already be JSON text."""
    return f"data: {data}\n\n"