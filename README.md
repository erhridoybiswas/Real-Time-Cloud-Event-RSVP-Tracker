# Real-Time Cloud-Based Event Planning & RSVP Tracker

[![CI](https://github.com/<you>/Real-Time-Cloud-Event-RSVP-Tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/<you>/Real-Time-Cloud-Event-RSVP-Tracker/actions)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A cloud-native event planning platform with **live RSVP tracking**, capacity-safe
seat allocation, FIFO waitlists, in-app notifications and organizer analytics —
built to demonstrate core cloud computing concepts.

## Overview
Organizers publish events; attendees RSVP with **Going / Maybe / Not Going**.
Every response is pushed to all connected dashboards in real time over
Server-Sent Events — no refresh required.

## Problem Statement
Manual RSVP coordination (spreadsheets, group chats, forms) does not scale:
counts go stale, capacity is oversold, and organizers have no live visibility.
This project centralises event state in a cloud database and pushes changes to
every client instantly.

## Objectives
- Demonstrate a cloud-hosted, stateless, horizontally scalable application
- Implement cloud authentication and role-based authorization
- Provide a real-time RSVP channel
- Guarantee capacity correctness under concurrency
- Deliver analytics and notifications
- Ship with automated tests, CI and documentation

## Features
- 🔐 JWT auth with ATTENDEE / ORGANIZER / ADMIN roles
- 📅 Full event CRUD with validation and lifecycle states
- ⚡ **Live RSVP counters over SSE** (polling fallback)
- 🎟️ Atomic, race-condition-safe capacity enforcement
- ⏳ FIFO waitlist with automatic promotion
- 📢 Announcements fanned out to attendees
- 🔔 In-app notification centre with unread badge
- 📊 Organizer analytics: response rate, utilisation, conversion, growth
- 🧪 38 automated tests including a 25-thread concurrency test
- 🐳 Docker + GitHub Actions CI

## Industry Relevance
The same architecture powers Eventbrite, Meetup, corporate webinar platforms
and college fest portals: centralised event state, live attendance counters,
capacity control and automated notifications.

## Cloud Computing Concepts
Cloud hosting · SaaS/PaaS · managed DB · real-time DB · auth · RBAC · REST ·
SSE/WebSocket · serverless · event-driven design · scalability · elasticity ·
HA · load balancing · API gateway · CDN · caching · env vars · secrets ·
logging · monitoring · backup · CI/CD.

## Real-Time Architecture
```
Client → API → (BEGIN IMMEDIATE) DB → COMMIT → Broker → SSE push → Dashboards
```

## Technology Stack
| Layer | Local (default) | Cloud (optional) |
|---|---|---|
| Frontend | HTML/CSS/Vanilla JS + Chart.js | React + Vite on Vercel |
| Backend | Flask 3 | FastAPI / Lambda |
| Database | SQLite (WAL) | Supabase Postgres / Aurora |
| Realtime | In-process SSE broker | Redis Pub/Sub / API Gateway WS |
| Auth | JWT + PBKDF2 | Firebase / Supabase / Cognito |
| Notifications | In-app | SES + SNS + FCM |

## User Roles
See the permission matrix in `docs/architecture.md`.

## Event Management
`event_id · organizer_id · event_name · description · event_type · event_date ·
start_time · end_time · venue · online_link · maximum_capacity ·
registration_deadline · status · created_at · updated_at`

Statuses: `DRAFT → PUBLISHED → FULL → COMPLETED` / `CANCELLED`

## RSVP System
One row per `(event_id, user_id)` enforced by a UNIQUE constraint.
Statuses: `GOING`, `MAYBE`, `NOT_GOING`, plus waitlist `WAITING` / `PROMOTED`.

## Real-Time Updates
`GET /api/events/{id}/stream` returns `text/event-stream`. The first frame is a
full SNAPSHOT; subsequent frames are RSVP deltas. The client reconnects with
exponential backoff and degrades to polling.

## Capacity Management
```python
with transaction():                    # BEGIN IMMEDIATE
    going = count_going(conn, event_id)
    if going >= capacity: waitlist()
    else:                 upsert_rsvp()
```

## Waitlist
FIFO by `joined_at`. On any GOING cancellation the oldest WAITING user is
promoted, notified and counted — automatically.

## Cloud Database
See `docs/architecture.md` for the ER diagram, keys, indexes and the relational
vs NoSQL trade-off discussion.

## Authentication
`POST /api/register` → `POST /api/login` → `Authorization: Bearer <jwt>`.
`@auth_required` + `@roles_required("ORGANIZER")` + ownership checks.

## Notifications
Types: `RSVP_CONFIRMED`, `EVENT_REMINDER`, `VENUE_CHANGED`, `TIME_CHANGED`,
`EVENT_CANCELLED`, `WAITLIST_PROMOTED`, `ANNOUNCEMENT`, `INVITE`.

## Analytics
Response rate · capacity utilisation · conversion rate · available seats ·
waitlist size · RSVP growth over time.

## REST APIs
Full endpoint table with request/response/status codes in `docs/api.md`.

## Concurrency Handling
`BEGIN IMMEDIATE` serialises writers so the capacity check and the insert are
atomic. Proven by `tests/test_concurrency.py::test_36`.

## Folder Structure
```
backend/{routes,services,realtime,utils}  frontend/{css,js}  tests/  sample_data/  docs/  reports/
```

## Installation
```bash
git clone https://github.com/<you>/Real-Time-Cloud-Event-RSVP-Tracker.git
cd Real-Time-Cloud-Event-RSVP-Tracker
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then edit the secrets
python -m sample_data.seed
python -m backend.app     # → http://localhost:5000
```

## Environment Variables
| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing |
| `JWT_SECRET` | JWT signing key |
| `JWT_EXP_MINUTES` | Token lifetime |
| `DATABASE_PATH` | SQLite file path |
| `CORS_ORIGINS` | Allowed origins |
| `RATE_LIMIT_PER_MINUTE` | Per-IP request cap |
| `BOOTSTRAP_KEY` | Grants the first ADMIN |
| `PORT` | Server port |

## Local Simulation
See §21 — seed data, three browser windows, live counter demo.

## Cloud Deployment
Render + Supabase (free tier) or AWS (CloudFront + API Gateway + Lambda +
Aurora + Cognito + SNS + CloudWatch). Full steps in `docs/deployment.md`.

## Testing
```bash
pytest -v
pytest --cov=backend --cov-report=html
```

## Security
PBKDF2 hashing · JWT · RBAC · parameterised SQL · input validation · XSS
escaping · CORS · rate limiting · security headers · audit logs · no secrets in
code.

## Scalability
Stateless pods behind an ALB, autoscaling, queues for burst absorption, Redis
caching, read replicas, denormalised counters for hot events.

## Failure Handling
Retry · reconnect · idempotency · transactions with rollback · graceful errors ·
structured logging.

## Screenshots
| File | Shows |
|---|---|
| `01-folder-structure.png` | Project layout |
| `02-architecture.png` | Cloud architecture diagram |
| `03-register.png` | Registration page |
| `04-login.png` | Login page |
| `05-organizer-dashboard.png` | KPIs + charts |
| `06-create-event.png` | Event creation form |
| `07-published-event.png` | Published event card |
| `08-attendee-dashboard.png` | Attendee view |
| `09-event-detail.png` | Event detail page |
| `10-rsvp-going.png` | GOING selected |
| `11-rsvp-maybe.png` | MAYBE selected |
| `12-realtime-update.png` | Counter changing live |
| `13-multibrowser-realtime.png` | 3 windows side by side |
| `14-database-record.png` | `rsvps` table rows |
| `15-capacity-utilisation.png` | Capacity bar |
| `16-event-full.png` | FULL status |
| `17-waitlist.png` | Waitlist table |
| `18-announcement.png` | Published announcement |
| `19-notification.png` | Notification centre |
| `20-analytics.png` | Analytics dashboard |
| `21-concurrency-test.png` | 25-thread test output |
| `22-unauthorized-403.png` | Forbidden response |
| `23-pytest-results.png` | Full suite green |
| `24-cloud-deployment.png` | Render dashboard |
| `25-live-app.png` | Production URL |
| `26-github-commits.png` | Commit history |
| `27-github-repo.png` | Repository home |
| `28-readme-preview.png` | Rendered README |

## Results
- 38/38 tests passing
- Exactly 1 winner in a 25-thread race for 1 seat
- Sub-100 ms SSE propagation on localhost
- Zero capacity overshoot under mixed concurrent load

## Limitations
- SQLite has a single writer (fine for coursework; swap to Postgres for scale)
- The in-process broker does not fan out across multiple workers without Redis
- JWTs are stateless, so there is no server-side revocation list yet

## Future Improvements
Redis Pub/Sub fan-out · email/SMS/push notifications · QR check-in ·
calendar (.ics) export · refresh-token rotation · iCal/Google Calendar sync ·
React Native mobile app · Terraform IaC · load testing with k6

## Learning Outcomes
Cloud architecture design · REST API design · real-time transports ·
database transactions and concurrency control · RBAC · cloud deployment ·
CI/CD · automated testing · technical documentation.

## Author
**HRIDOY_BISWAS** — B.Tech CSE · [GitHub](https://github.com/erhridoybiswas) · [LinkedIn](https://linkedin.com/in/erhridoybiswas)

## License
MIT
