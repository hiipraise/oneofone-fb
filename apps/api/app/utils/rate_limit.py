# app/utils/rate_limit.py
"""
Shared slowapi limiter for quota-sensitive endpoints.

Applied to prediction generation, web search, and scheduler trigger/admin
actions so they cannot be hammered (Sprint 5.2). Limits are keyed on
``request.client.host`` via get_remote_address.

Note: on Render the app sits behind a reverse proxy, so ``client.host`` is the
proxy IP and all clients share one rate-limit bucket. That is acceptable as
abuse protection (an attacker still can't burn Serper quota), but it is not
per-user isolation. Do NOT trust ``X-Forwarded-For`` for per-client limiting
here — it is client-spoofable behind this proxy setup.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
