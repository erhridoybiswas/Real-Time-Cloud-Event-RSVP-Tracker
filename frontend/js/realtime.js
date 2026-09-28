/* ------------------------------------------------------------------
 * realtime.js — SSE client with automatic reconnect + polling fallback
 * ------------------------------------------------------------------ */

class RealtimeClient {
  constructor(eventId) {
    this.eventId = eventId;
    this.source = null;
    this.handlers = [];
    this.statusHandlers = [];
    this.retryDelay = 1000;
    this.closed = false;
    this.pollTimer = null;
  }

  onMessage(handler) { this.handlers.push(handler); return this; }
  onStatus(handler) { this.statusHandlers.push(handler); return this; }

  _emitStatus(connected) {
    this.statusHandlers.forEach((h) => h(connected));
  }

  _emit(payload) { this.handlers.forEach((h) => h(payload)); }

  connect() {
    if (this.closed) return;
    if (typeof EventSource === "undefined") return this._startPolling();

    const token = encodeURIComponent(Token.get() || "");
    const url = `/api/events/${this.eventId}/stream?token=${token}`;
    this.source = new EventSource(url);

    this.source.onopen = () => {
      this.retryDelay = 1000;
      this._emitStatus(true);
      this._stopPolling();
    };

    this.source.onmessage = (event) => {
      try { this._emit(JSON.parse(event.data)); }
      catch { /* ignore malformed frame */ }
    };

    this.source.onerror = () => {
      this._emitStatus(false);
      if (this.source) this.source.close();
      this.source = null;
      if (this.closed) return;

      // After repeated failures fall back to polling so the UI stays fresh.
      if (this.retryDelay > 8000) this._startPolling();

      setTimeout(() => this.connect(), this.retryDelay);
      this.retryDelay = Math.min(this.retryDelay * 2, 15000);
    };
  }

  _startPolling() {
    if (this.pollTimer) return;
    const poll = async () => {
      try {
        const { counts } = await Api.eventCounts(this.eventId);
        this._emit({ type: "RSVP_UPDATED", reason: "POLL", counts });
      } catch { /* offline — keep trying */ }
    };
    poll();
    this.pollTimer = setInterval(poll, 5000);
  }

  _stopPolling() {
    if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
  }

  close() {
    this.closed = true;
    this._stopPolling();
    if (this.source) { this.source.close(); this.source = null; }
  }
}

let _activeRealtime = null;

function openRealtime(eventId, onMessage, onStatus) {
  if (_activeRealtime) _activeRealtime.close();
  _activeRealtime = new RealtimeClient(eventId);
  if (onMessage) _activeRealtime.onMessage(onMessage);
  _activeRealtime.onStatus(onStatus || (() => {}));
  _activeRealtime.connect();
  return _activeRealtime;
}

function closeRealtime() {
  if (_activeRealtime) { _activeRealtime.close(); _activeRealtime = null; }
}