# Vertex HR & Payroll — Backend

FastAPI + PostgreSQL + SQLAlchemy 2 + Pydantic 2, built to plug into the existing Vertex Next.js frontend.
Full endpoint list with request/response examples: **[API_CONTRACT.md](API_CONTRACT.md)**.

## What's in the box

```
Payroll-system/
├── backend/
│   ├── main.py            app, CORS, error shapes, /health
│   ├── config.py          all settings from .env
│   ├── database.py        engine + session
│   ├── models.py          every table (users, employees, salary, bank, attendance, leave, payroll, payslips, audit)
│   ├── schemas.py         Pydantic request/response models + validation
│   ├── auth.py            JWT, bcrypt, roles, /auth and /users
│   ├── employees.py       employees, departments, salary, bank (masked + audited)
│   ├── attendance.py      clock in/out, daily log, monthly summary
│   ├── leave.py           requests, approvals, balances
│   ├── payroll_engine.py  pure Decimal maths (no DB) — the part that must be right
│   ├── payroll.py         runs: create → review → finalize → paid, reopen workflow, exceptions
│   ├── payslips.py        list, publish, PDF download
│   ├── payslip_pdf.py     PDF renderer (₹-safe fonts, Indian digit grouping)
│   ├── reports.py         dashboard + 5 reports
│   ├── exports.py         Excel / CSV writers
│   ├── settings.py        payroll rules, tax slabs, holidays, audit-log viewer
│   ├── bootstrap.py       first-run defaults (leave types, sample slabs, config)
│   ├── tests/             engine unit tests + end-to-end API tests
│   ├── requirements.txt · .env.example · pytest.ini
└── database/seed.py       realistic demo data
```

### How it maps to the frontend

| Frontend page | Endpoints |
|---|---|
| Login / Settings → Profile & Security | `POST /auth/login`, `GET/PATCH /auth/me`, `POST /auth/change-password` |
| Dashboard | `GET /dashboard`, `GET /payroll/runs/{id}/items`, `/exceptions`, `GET /reports/payroll-register/export?format=csv` |
| Employees / Directory | `GET/POST /employees`, `GET/PATCH/DELETE /employees/{id}`, `PUT /employees/{id}/salary`, `/bank` |
| Time & Attendance | `GET /attendance?date=&department=`, `POST /attendance`, `GET /reports/attendance-summary/export` |
| Leave | `GET /leave/requests?tab=`, `POST /leave/requests`, `POST …/approve`, `…/deny` |
| Payroll (stepper) | `GET /payroll/runs/current`, `POST /payroll/runs`, `…/review`, `…/finalize`, `…/mark-paid` |
| Payslips | `GET /payslips/periods`, `GET /payslips?period=`, `POST /payslips/publish`, `GET /payslips/{id}/download` |
| Reports | `GET /reports`, `GET /reports/{name}/export`, `GET /reports/recent` |
| Settings → Company | `GET/PUT /settings/company`, `/settings/payroll`, `/settings/tax-slabs`, `/settings/holidays` |

Field names follow the frontend where they exist (`emp_code` = `EMP-001`, `designation` = the frontend's "role", `employment_type` = "type", `dates`, `days`, `status`, `Present/Late/Absent`). Each leave and attendance row also carries a ready-to-display string (`dates: "Oct 12 - Oct 16"`, `clock_in_display: "08:45 AM"`).

## Key design decisions

* **Money**: `Decimal` end to end, `NUMERIC(12,2)` in PostgreSQL, rounded half-up once per figure. JSON output is a number.
* **Configurable, never hardcoded**: PF %, PF ceiling, standard deduction, cess, rebate limit, tax slabs, professional tax, overtime multiplier, shift/grace, weekly offs and holidays all live in the database and are edited via `/settings/*`. **The shipped numbers are SAMPLES** so the demo runs — verify them against current Indian rules and your state's professional tax before real use.
* **Payroll snapshot**: every run stores the exact amounts used, so changing a salary later never alters a finalized payslip.
* **No duplicate runs**: unique `(year, month)` constraint + friendly 409.
* **Finalized = locked**: no recalculation, no item edits, no attendance/leave/holiday changes in that month. The only way back is `POST /payroll/runs/{id}/reopen` (admin, written reason, audited), and only while no payslip is published. A paid run is never reopened — correct it next month with a bonus / manual-deduction adjustment.
* **Safety nets in the run**: *Exceptions* (missing salary structure or negative net **block** review; missing bank, unrecorded attendance, proration are warnings). Review/finalize re-check that source data hasn't changed since calculation.
* **Unrecorded days are never guessed as absent.** Loss of pay comes only from recorded `Absent`, `Half Day` and approved *unpaid* leave; approved paid leave cancels it.
* **Separation of duties**: HR prepares and reviews; only admin finalizes, marks paid, reopens, deletes employees, changes rules.
* **Salary / bank security**: employees see only their own data; bank numbers are masked everywhere except an audited staff-only `/bank/reveal`; PAN is masked on payslips; payslips of others return 404; role is read from the database on each request (disabling a user takes effect immediately); bcrypt hashing; login timing doesn't reveal which emails exist; Excel/CSV cells are protected against formula injection.

## Setup

### 1. PostgreSQL
```sql
-- psql -U postgres
CREATE USER vertex_user WITH PASSWORD 'change_me';
CREATE DATABASE vertex OWNER vertex_user;
```

### 2. Python environment
```bash
cd backend
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # Windows: copy .env.example .env
```
Edit `.env`: set `DATABASE_URL` to match step 1, and a real `JWT_SECRET`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3. Create tables + demo data
```bash
python ../database/seed.py --reset      # creates tables and seeds 19 employees, 2 payroll months, leave, attendance
```
Demo logins (password `Vertex@2026`, override with `SEED_PASSWORD`): `admin@vertex.com` · `hr@vertex.com` · `arjun.desai@vertex.com` (employee).
Skip seeding if you want an empty system: tables are created automatically on start (`AUTO_CREATE_TABLES=true`); the first account you register becomes admin.

### 4. Run
```bash
uvicorn main:app --reload --port 8000
```
Open http://localhost:8000/docs → **Authorize** with the token from `POST /auth/login`.

### 5. Tests
```bash
cd backend && pytest -v
```
They use an in-memory SQLite database, never your PostgreSQL data.

## Connect the Next.js frontend

1. `frontend/.env.local`
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
   ```
2. The API client should send the token on every request and bounce to login on 401 (your frontend doc's `lib/api.ts` already follows this pattern — just make sure the base URL and token key match):
   ```ts
   import axios from 'axios';
   export const api = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL });
   api.interceptors.request.use((cfg) => {
     const token = localStorage.getItem('vertex_token');
     if (token) cfg.headers.Authorization = `Bearer ${token}`;
     return cfg;
   });
   api.interceptors.response.use((r) => r, (err) => {
     if (err.response?.status === 401) { localStorage.removeItem('vertex_token'); window.location.href = '/login'; }
     return Promise.reject(err);
   });
   ```
3. Login page: replace the simulated login with
   ```ts
   const { data } = await api.post('/auth/login', { email, password });
   localStorage.setItem('vertex_token', data.access_token);   // data.user has role + name
   ```
4. Replace each page's hardcoded array with a call, e.g. dashboard `const { data } = await api.get('/dashboard')`, leave `api.get('/leave/requests', { params: { tab: 'pending' } })`, approve `api.post(`/leave/requests/${id}/approve`)`.
5. **PDF / Excel downloads** need the auth header, so a plain `<a href>` won't work:
   ```ts
   const res = await api.get(`/payslips/${id}/download`, { responseType: 'blob' });
   const url = URL.createObjectURL(res.data);
   Object.assign(document.createElement('a'), { href: url, download: `payslip-${id}.pdf` }).click();
   URL.revokeObjectURL(url);
   ```
   The same pattern works for `/reports/{name}/export?format=xlsx`.
6. **Currency**: the frontend formats amounts as dollars; for ₹ change `formatCurrency` to
   `new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })`. (Only the number formatting — no design change.)
7. Attendance rows can also come back as `Not Marked` or `Day Off`; give those badges a neutral style (the frontend styles only On Time / Late / Absent).
8. CORS: `CORS_ORIGINS` in `.env` must include the exact frontend origin (`http://localhost:3000`).

Not covered by the backend: the **AI chatbot widget** (it is simulated in the frontend doc and there's no data for it here) and the payslip **"Send" email** button (needs SMTP). Everything else on the pages above has a real endpoint.

## Verification checklist (do this once, in order)

- [ ] `pytest -v` passes
- [ ] `GET /health` → `{"status":"ok","database":"up"}`
- [ ] Login as admin → open `/docs`, Authorize
- [ ] `GET /dashboard` shows gross / net / headcount; `current_run` is last month, status `FINALIZED`
- [ ] `GET /payslips?period=<last month>` → 19 rows, 3 `Published`; `POST /payslips/publish` publishes the rest
- [ ] Download a payslip PDF; the ₹ sign renders and net-pay-in-words matches
- [ ] `POST /payroll/runs` for the same month again → **409**
- [ ] `POST /attendance` for a day in a finalized month → **409**
- [ ] `POST /payroll/runs/{id}/reopen` on a run with published payslips → **409**
- [ ] Log in as `arjun.desai@vertex.com`: `GET /employees` → 403, `GET /employees/me` → own record with masked bank, `GET /payslips?period=…` → only his own published slip
- [ ] Log in as HR: `POST …/finalize` → 403
- [ ] `GET /reports/payroll-register/export?period=…&format=xlsx` opens in Excel with a Total row
- [ ] Create this month's run, add a bonus with `PATCH …/items/{id}`, review, finalize, mark paid, publish — the full cycle

## Honest limitations

* **Verified in my build environment** (no internet, so FastAPI/SQLAlchemy couldn't be installed there): the payroll maths against hand-calculated figures (11 engine tests), PDF rendering (visually checked), Excel/CSV export, and that every file compiles. **The API layer and the API tests were written carefully but not executed** — run `pytest -v` first; if anything fails, paste the output and it's a quick fix.
* TDS is a simple projection (annualised fixed pay + marginal tax on that month's bonus/overtime, no marginal relief, no investment declarations, no regime choice). Good for a college project, not a statutory filing.
* Bank account numbers are access-controlled and masked but stored as plain text in the DB; encrypt at rest for production.
* No login rate-limiting/lockout, no refresh tokens (8-hour access token), token kept in `localStorage` like the frontend doc does.
* Tables are created with `create_all`, not migrations. Add Alembic when the schema starts changing.
* Overtime is paid from recorded hours beyond the standard day without a separate approval step.