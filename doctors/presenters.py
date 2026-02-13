# doctors/presenters.py
"""
Presenters module (Factory + Adapter)
- Responsibility: convert model instances or raw values into template-ready dicts.
- Purpose: automate mapping so templates only render and never inspect model internals.
- SOLID:
  - SRP: each function adapts one thing.
  - DIP: views depend on these adapters/factories, not model guts.
- Patterns:
  - Factory: build_action centralizes quick-action dict creation and resolves URLs.
  - Adapter: appointment_adapter, shift_adapter, patient_adapter, report_adapter normalize shapes.
- Safety: best-effort URL resolution; if reverse fails, href=None so templates render disabled UI gracefully.
"""

from django.urls import reverse, NoReverseMatch
from django.utils import timezone


def _try_resolve_url(candidates, arg=None):
    """
    Try to reverse a list of candidate URL names. Return first successful href or None.
    candidates: iterable of url name strings (may include namespace).
    arg: optional single positional arg for reverse.
    """
    for name in candidates:
        try:
            return reverse(name, args=[arg]) if arg is not None else reverse(name)
        except NoReverseMatch:
            continue
    return None


def build_action(label, icon=None, url_name=None, url_arg=None, variant=None, aria_label=None, href=None):
    """
    Build a robust quick action dict for templates.
    - Resolve url_name to href here (templates shouldn't call {% url %}).
    - If reverse fails, href will be None; templates should render a disabled button.
    """
    if href is None and url_name:
        try:
            href = reverse(url_name, args=[url_arg]) if url_arg is not None else reverse(url_name)
        except NoReverseMatch:
            href = None
    return {
        "label": label,
        "icon": icon,
        "variant": variant,
        "aria_label": aria_label or label,
        "href": href,
        # Explicitly null out url_name/url_arg so templates prefer href and stay resilient
        "url_name": None,
        "url_arg": None,
    }


def appointment_adapter(appt):
    """
    Convert an appointments.Appointment instance into the mini_card shape.
    Expected keys: title, subtitle, image_url, badges, kpis, href, aria_label
    """
    # Patient display name (defensive)
    title = None
    try:
        patient = getattr(appt, "patient", None)
        if patient is not None:
            if hasattr(patient, "get_full_name_or_username"):
                title = patient.get_full_name_or_username()
            else:
                user = getattr(patient, "user", None)
                title = (user.get_full_name() if hasattr(user, "get_full_name") else getattr(user, "username", None))
    except Exception:
        pass
    title = title or getattr(appt, "title", None) or str(appt)

    # Subtitle: formatted scheduled time or reason
    scheduled = getattr(appt, "scheduled_time", None)
    if scheduled:
        try:
            subtitle = timezone.localtime(scheduled).strftime("%b %d, %Y %I:%M %p")
        except Exception:
            subtitle = str(scheduled)
    else:
        subtitle = getattr(appt, "reason", "") or ""

    # Status badge
    status = getattr(appt, "status", None)
    badges = [{"label": str(status), "variant": "warning"}] if status else []

    # KPIs
    kpis = []
    if scheduled:
        kpis.append({"label": "When", "value": subtitle})

    # Resolve appointment detail URL
    href = _try_resolve_url(
        [
            "appointments:detail",            # matches your appointments/urls.py
            "appointments:appointment-list",  # fallback to list
            "appointments:appointment-api-detail",
        ],
        arg=getattr(appt, "id", None)
    )

    return {
        "title": title,
        "subtitle": subtitle,
        "image_url": None,
        "badges": badges,
        "kpis": kpis,
        "href": href,
        "aria_label": f"Appointment with {title}",
    }


def shift_adapter(shift):
    """
    Convert a schedules.Shift into mini_card shape.
    """
    # Title: duty type or fallback
    duty = getattr(shift, "duty", None)
    duty_type = getattr(duty, "duty_type", None)
    title = duty_type or f"Shift {getattr(shift, 'id', '')}"

    # Subtitle: day of week + start/end time
    dow = ""
    try:
        dow = shift.get_day_of_week_display()
    except Exception:
        dow = f"Day {getattr(shift, 'day_of_week', '')}"

    start = getattr(shift, "start_time", None)
    end = getattr(shift, "end_time", None)
    subtitle = f"{dow} {start}–{end}".strip()

    # Active badge
    state = getattr(shift, "is_active", None)
    badges = [{"label": "Active" if state else "Inactive", "variant": "info"}] if state is not None else []

    # KPI: duration if callable
    kpis = []
    try:
        duration_fn = getattr(shift, "duration_minutes", None)
        if callable(duration_fn):
            mins = duration_fn()
            kpis.append({"label": "Duration", "value": f"{mins}m"})
    except Exception:
        pass

    # Link to schedules dashboard/calendar
    href = _try_resolve_url(["schedules:schedule-dashboard", "schedules:doctor-schedules", "schedules:schedule-calendar", "schedules:schedules"])

    return {
        "title": title,
        "subtitle": subtitle,
        "image_url": None,
        "badges": badges,
        "kpis": kpis,
        "href": href,
        "aria_label": f"Shift {title}",
    }


def patient_adapter(patient):
    """
    Convert a PatientProfile (or user-like object) into mini_card shape.
    """
    # Title
    title = None
    try:
        if hasattr(patient, "get_full_name_or_username"):
            title = patient.get_full_name_or_username()
        elif hasattr(patient, "user") and hasattr(patient.user, "get_full_name"):
            title = patient.user.get_full_name() or patient.user.username
        else:
            title = str(patient)
    except Exception:
        title = str(patient)

    subtitle = getattr(patient, "phone", "") or ""
    image_url = getattr(patient, "avatar_url", None) or None

    # Patient profile/detail URL: patients:detail (profile/<int:pk>/), patients:profile, patients:dashboard
    pk = getattr(patient, "pk", None)
    href = _try_resolve_url(["patients:detail", "patients:profile", "patients:dashboard"], arg=pk)

    return {
        "title": title,
        "subtitle": subtitle,
        "image_url": image_url,
        "badges": [],
        "kpis": [],
        "href": href,
        "aria_label": f"Patient {title}",
    }


def report_adapter(report):
    """
    Convert a reports.Report into mini_card shape.
    """
    title = getattr(report, "title", None) or str(report)
    subtitle = getattr(report, "description", "") or ""
    # Your reports app exposes a dashboard; no explicit report detail path in the URLs provided.
    href = _try_resolve_url(["reports:dashboard"])
    return {
        "title": title,
        "subtitle": subtitle,
        "image_url": None,
        "badges": [],
        "kpis": [],
        "href": href,
        "aria_label": f"Report {title}",
    }
