## 1. Architecture sketch

```
Browser                                 Server (Django 5.1, gunicorn, SQLite)
  │  HTTP request                         │
  ▼                                       ▼
request ─────────────────────────▶  swapshelf/urls.py ─▶ market/urls.py
  │                                   middleware: Session, CSRF, Auth, Messages
  │  Cookie: sessionid=<id>           views (market/views.py):
  │ ───────────────────────────▶        GET  /                 home          (public board)
  │                                      GET  /listings/<pk>/   listing_detail(public)
  │                                      GET/POST /listings/new listing_new   (login req.)
  │                                      GET/POST /listings/<pk>/edit         (login req.)
  │                                      POST /listings/<pk>/sold|delete      (login req.)
  │                                      GET  /listings/<pk>/message start_thread(login req.)
  │                                      GET/POST /threads/<pk> thread_detail (login req.)
  │                                      GET  /me/              mine          (login req.)
  │                                      GET/POST /register     register
  │                                      GET/POST /login        sign_in
  │                                      GET/POST /profile      profile       (login req.)
  │                                      GET  /desk/            desk          (login req.)
  │                                      /admin/                Django admin  (is_staff)
  │  Set-Cookie: sessionid=…          │
  │ ◀───────────────────────────  rendered templates (market/templates/, auto-escaped)
  ▼                                     ▼
                                    market/models.py  → data/swapshelf.db
                                    (tables: auth_user, market_listing,
                                             market_thread, market_message)
```

**What runs where.** Standard server-rendered Django. `swapshelf/urls.py`
mounts the admin, the auth logout view, and `market/urls.py`. Each request
passes the session + CSRF + auth middleware, a view runs the ORM, and a
template renders. Templates auto-escape every interpolated value, so there is
no HTML-injection surface and no JSON API.

**How a listing id becomes a row.** The board links each card to
`/listings/<int:pk>/`. The `<int:pk>` path converter hands `pk` to
`listing_detail`, which calls `get_object_or_404(Listing, pk=pk)` — a primary-key
lookup against `market_listing` that renders the row or returns 404. The edit,
sold, delete, and message routes resolve their `pk` the same way.

**Which pages a logged-out visitor can open.** Only the public board (`/`,
including the `?category=` filter), an individual listing (`/listings/<pk>/`),
and the `register` / `login` screens. Everything else is wrapped in
`@login_required` and redirects to the sign-in page. The listing detail page
hides the "Message / Edit / Mark sold" controls from anonymous visitors.

**What the profile form writes back to the user.** `GET/POST /profile`
binds `ProfileForm` to `request.user` and `form.save()` writes the submitted
fields straight onto that `auth_user` row. This is the planted defect — see §2.

**What the department desk is for, and who can open it.** `/desk/` is a
staff-only page that reveals a physical pickup location and a reimbursement
code (`DESK-2290`) for department "board" accounts — explicitly *"Not for the
public board."* The view gates on `request.user.is_staff`: staff see the note,
everyone else sees a generic "this page is for department board accounts"
message. `is_staff` is also Django's flag for logging into `/admin/`. In the
shipped seed **no ordinary account is staff**, so the desk is meant to be
reachable only by an operator-provisioned board account — which is exactly what
§2 breaks.

## 2. The defect: self-service privilege escalation via the profile form (mass assignment)

**Location:** `ProfileForm` in `market/forms.py`, saved by the `profile` view in
`market/views.py`.
**Class:** CWE-269 (improper privilege management) via CWE-915 (mass assignment
of a sensitive attribute). Exploitable by any logged-in user against their own
account — no other victim, token, or secret required.

`ProfileForm` was a `ModelForm` over the `User` model whose field list included
Django's authorization flag `is_staff`, dressed up with a friendly label:

```python
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_staff"]
        labels = {
            "is_staff": "Show my name on the department board",
        }
```

The label frames `is_staff` as a harmless "show my name on the board"
preference, but `is_staff` is not cosmetic. It is the flag the `desk` view
checks (`if not request.user.is_staff`) and the flag Django's admin login
requires. Because the field is bound to the form and the `profile` view calls
`form.save()` with no further checks, **any account can tick that checkbox and
promote itself to staff** — opening the department desk (and the `/admin/`
login gate) that it was never meant to reach.

### Verified trigger (local instance, 2026-10-25)

Against the original code on `127.0.0.1:3100`, as a brand-new self-registered
account `mallory` (no privileges):

1. Before escalation, `GET /desk/` shows only the generic *"This page is for
   department board accounts."* — the reimbursement code is **not** present.
2. `GET /profile/` renders an `is_staff` checkbox. POST the profile form with
   `is_staff=on` (plus the normal name/email fields and the CSRF token):

   ```
   POST /profile/   first_name=M&last_name=X&email=m@x.com&is_staff=on
   ```
3. `GET /desk/` now returns the restricted note in full:

   ```
   Department hold closet, Hullihen basement cage B.
   Reimbursement code DESK-2290. Not for the public board.
   ```
4. `GET /admin/` no longer bounces to the admin login — the self-promoted
   account is past the `is_staff` gate (it lacks row permissions, but it is
   inside the admin boundary any real staff member sits behind).

**Impact.** Full self-service privilege escalation from an ordinary account to
a department-board / staff account. The attacker reads the restricted desk
information (physical hold-closet location and the `DESK-2290` reimbursement
code marked *not for the public board*) and clears the `is_staff` gate on the
Django admin site — all by checking a box mislabeled as a display preference.

## 3. Fix

Two changes, both small; the `profile` view, templates, and the whole posting /
messaging path are untouched.

**(a) Drop the privilege flag from the self-service form.** `ProfileForm`
(`market/forms.py`) now binds only the three genuinely user-owned fields, so
`is_staff` can never be set from the profile page:

```python
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
```

A `ModelForm` only writes the fields it declares, so even a hand-crafted POST
that includes `is_staff=on` is ignored — the attribute is no longer bound.

**(b) Give the desk a legitimate, operator-provisioned owner.** Staff / board
membership is now assigned where it belongs — by the operator — instead of being
self-selected. `market/seed.py` provisions one real department-board account:

```python
User.objects.create_user(
    "desk", "desk@campus.edu", "deskpass1",
    first_name="Dana", last_name="Desk", is_staff=True,
)
```

So the desk feature still has a working owner (and is demonstrable), while every
ordinary account is locked out. In production, board accounts would be granted
`is_staff` by an administrator (`createsuperuser` or the admin site), never by
the end user.

**Why normal use still works.** Posting, editing, marking sold, messaging,
registration, and sign-in never touched `is_staff`, so they are unaffected. The
profile page still saves name and email exactly as before — only the privilege
checkbox is gone. The department desk still opens for the real board account.

## 4. Patch verification (2026-10-25, local instance)

Re-seeded a fresh database and re-ran the full matrix:

- [x] **Old attack is dead.** The profile form no longer renders an `is_staff`
      field; a POST that still smuggles `is_staff=on` is ignored. After it, the
      attacker's `GET /desk/` does **not** contain `DESK-2290`, and `GET /admin/`
      stays behind the admin login gate.
- [x] **Legitimate desk access intact.** Signing in as the seeded `desk` /
      `deskpass1` board account and opening `/desk/` shows the `DESK-2290` note.
- [x] **Normal posting intact.** `alex` / `campus123` posts a new listing
      ("Mini fridge") successfully.
- [x] **Profile save intact.** `alex` saves name/email through the profile form
      with no error (no 403, no field errors).

## 5. Submission fields

- **Hosted URL:** `https://swapshelf-ryanhenderson.fly.dev/` (Fly.io, region iad)
- **Date/time PoC verified:** locally on 2026-10-25
- **Commit hash of the patch:** _<fill in after committing>_ (repo: `https://github.com/ryanhson/swapshelf`)

### Optional hardening (beyond the required fix)

- **Object-level ownership checks.** `listing_edit`, `listing_sold`, and
  `listing_delete` resolve the listing by `pk` with no owner check, so any
  logged-in user can edit, mark sold, or remove *another* member's listing
  (IDOR, CWE-639). Likewise `thread_detail` lets any logged-in user open any
  thread by id and read its private messages. Scope each of these to
  `owner=request.user` (or thread participants) — e.g.
  `get_object_or_404(Listing, pk=pk, owner=request.user)`.
- **Set a real `SECRET_KEY` in production.** `settings.py` falls back to a
  hard-coded `"swapshelf-dev-secret"`; provide a random value via the
  environment (done on Fly via `flyctl secrets set SECRET_KEY=…`).
- **Cookie hardening behind HTTPS.** With `force_https` on Fly, set
  `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE = True` and a `SameSite` policy.
