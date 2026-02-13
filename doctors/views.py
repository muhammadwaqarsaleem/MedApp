# doctors/views.py
"""
Views for the doctors app.

This file preserves the original API and HTML views and provides a robust,
well-commented DoctorDashboardView that:
- Resolves named routes to concrete hrefs in the view to avoid template
  NoReverseMatch errors when a namespace is missing.
- Calls dashboard services for KPIs and summaries and maps results through
  presenters.
- Provides a defensive, multi-tier fallback for loading "shifts" from the
  schedules app (tries dashboard_services first, then common schedules service
  function names), logging failures but never raising to the template.
- Keeps all service calls isolated in try/except blocks so a single failing
  integration does not break the entire dashboard page.
"""

from django.views.generic import ListView, TemplateView
from django.db.models import Q
from django.views import View
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from datetime import timedelta, datetime
import logging

from .models import DoctorProfile, SPECIALIZATION_CHOICES
from .serializers import DoctorProfileSerializer, TimetableSerializer, PrescriptionSerializer
from appointments.models import Appointment, AppointmentStatus
from prescriptions.models import Prescription
from .services import (
    ensure_doctor_profile, manage_timetable, get_timetable,
    cancel_patient_appointment
)

# Local presenters and dashboard services
from . import presenters
from . import services as dashboard_services



# ---------------------------
# Section A: API Views
# ---------------------------

class DoctorProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = ensure_doctor_profile(request.user)
        return Response(DoctorProfileSerializer(profile).data)


class TimetableView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file_obj = request.FILES["file"]
        timetable = manage_timetable(request.user, file_obj)
        return Response(TimetableSerializer(timetable).data, status=status.HTTP_201_CREATED)

    def get(self, request):
        tt = get_timetable(request.user)
        return Response(TimetableSerializer(tt).data if tt else {}, status=status.HTTP_200_OK)


class CancelAppointmentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        appointment_id = request.data.get("appointment_id")
        reason = request.data.get("reason", "")
        cancel_patient_appointment(request.user, appointment_id, reason)
        return Response({"status": "Appointment cancelled"}, status=status.HTTP_200_OK)


class PrescriptionView(APIView):
    """
    API for creating and listing prescriptions tied to appointments.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data

        appointment_id = data.get("appointment_id")
        # Appointment.doctor is DoctorProfile; filter via doctor__user
        appointment = get_object_or_404(Appointment, id=appointment_id, doctor__user=request.user)

        pres = Prescription.objects.create(
            appointment=appointment,
            notes=data.get("text", "")
        )

        return Response(PrescriptionSerializer(pres).data, status=status.HTTP_201_CREATED)

    def get(self, request):
        prescriptions = Prescription.objects.filter(appointment__doctor__user=request.user)
        return Response(PrescriptionSerializer(prescriptions, many=True).data)


# ---------------------------
# Section B: Frontend HTML Views
# ---------------------------

class DoctorListView(ListView):
    """
    HTML page: Doctors list with filters and pagination.
    """
    model = DoctorProfile
    context_object_name = "doctors"
    template_name = "doctors/doctor_list.html"
    paginate_by = 10

    def get_queryset(self):
        qs = DoctorProfile.objects.select_related("user").all()
        params = self.request.GET

        # Text search: name, bio, qualification
        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(bio__icontains=q) |
                Q(qualification__icontains=q)
            )

        # Specialization filter
        specialization = (params.get("specialization") or "").strip()
        if specialization:
            qs = qs.filter(specialization=specialization)

        # Minimum experience filter
        min_exp_raw = (params.get("min_exp") or "").strip()
        if min_exp_raw.isdigit():
            qs = qs.filter(experience_years__gte=int(min_exp_raw))

        # Minimum rating filter
        min_rating_raw = (params.get("min_rating") or "").strip()
        try:
            if min_rating_raw:
                qs = qs.filter(rating__gte=float(min_rating_raw))
        except ValueError:
            pass

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()

        ctx["filters"] = {
            "q": params.get("q", ""),
            "specialization": params.get("specialization", ""),
            "min_exp": params.get("min_exp", ""),
            "min_rating": params.get("min_rating", ""),
        }
        ctx["specializations"] = SPECIALIZATION_CHOICES
        ctx["crumbs"] = [
            {"label": "Home", "url": "/"},
            {"label": "Doctors", "url": None},
        ]
        return ctx


User = get_user_model()

class DoctorDetailView(View):
    """
    HTML page: Doctor detail with available slots for booking.
    """
    def get(self, request, id):
        # We show the doctor's User info, but Appointment.doctor expects DoctorProfile
        doctor_user = get_object_or_404(User, id=id)
        profile = getattr(doctor_user, "doctors_doctor_profile", None)

        today = timezone.now()
        next_week = today + timedelta(days=7)

        # Filter appointments by DoctorProfile (not User)
        booked_slots = Appointment.objects.filter(
            doctor=profile,
            scheduled_time__range=(today, next_week),
            status__in=[AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]
        ).values_list("scheduled_time", flat=True)

        slots = []
        for day in range(7):
            date = today + timedelta(days=day)
            for hour in range(9, 17):
                slot_time = timezone.make_aware(
                    datetime(date.year, date.month, date.day, hour),
                    timezone.get_current_timezone()
                )
                if slot_time not in booked_slots:
                    slots.append(slot_time)

        context = {
            "doctor": doctor_user,
            "profile": profile,
            "available_slots": slots,
            "crumbs": [
                {"label": "Home", "url": "/"},
                {"label": "Doctors", "url": "/doctors/"},
                {"label": f"Dr. {doctor_user.get_full_name()}", "url": None},
            ],
        }
        return render(request, "doctors/doctor_detail.html", context)


# ---------------------------
# Section C: New - Doctor Dashboard (additive, robust)
# ---------------------------

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.urls import reverse, NoReverseMatch
import logging
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.shortcuts import redirect
from django.contrib import messages
logger = logging.getLogger(__name__)

class DoctorDashboardView(LoginRequiredMixin, TemplateView):
    """
    Doctor user account dashboard (robust).

    Key improvements:
    - Resolves named routes to concrete hrefs in the view to avoid template NoReverseMatch.
    - Recursively converts any dict in the context that contains 'url_name' (and optional 'url_arg')
      into an 'href' key using django.urls.reverse, with safe fallbacks.
    - Defensive: logs failures and never raises to the template; missing routes simply result in
      omitted or disabled actions.
    - Keeps service calls isolated so one failing integration doesn't break the page.
    """
    template_name = "doctors/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        # Only allow doctors
        if not request.user.is_authenticated or not request.user.is_doctor():
            messages.error(request, "You are not authorized to access the doctor dashboard.")
            return redirect("accounts:login")  # or redirect to patient dashboard
        return super().dispatch(request, *args, **kwargs)

    def _resolve_named_url(self, url_name: str, url_arg=None):
        """
        Try to reverse a named URL safely. Returns href string or None.
        - If reversing fails and namespace is 'shifts', try 'schedules' as a fallback.
        - Any exception is logged and None is returned.
        """
        try:
            if url_arg:
                return reverse(url_name, args=[url_arg])
            return reverse(url_name)
        except NoReverseMatch as e:
            # Try a small, sensible fallback if namespace is 'shifts'
            try:
                if ":" in url_name:
                    ns, name = url_name.split(":", 1)
                    if ns == "shifts":
                        fallback = f"schedules:{name}"
                        try:
                            if url_arg:
                                return reverse(fallback, args=[url_arg])
                            return reverse(fallback)
                        except NoReverseMatch:
                            return None
            except Exception:
                # swallow and return None
                logger.debug("Fallback attempt failed for url_name=%s: %s", url_name, e, exc_info=True)
            logger.debug("NoReverseMatch for url_name=%s: %s", url_name, e, exc_info=True)
            return None
        except Exception as e:
            logger.exception("Unexpected error reversing url_name=%s: %s", url_name, e)
            return None

    def _resolve_context_urls(self, obj):
        """
        Recursively walk `obj` (which may be a dict, list, tuple, or other) and:
        - If a dict contains 'url_name', attempt to resolve it to 'href' and remove 'url_name'/'url_arg'.
        - Returns a new object (does not mutate original) with resolved hrefs where possible.
        This ensures templates that expect 'href' will not call {% url %} on missing namespaces.
        """
        if isinstance(obj, dict):
            new = {}
            # If this dict itself contains url_name, resolve it first
            if "url_name" in obj:
                url_name = obj.get("url_name")
                url_arg = obj.get("url_arg")
                href = self._resolve_named_url(url_name, url_arg)
                # Copy all keys except url_name/url_arg; prefer explicit href if present
                for k, v in obj.items():
                    if k in ("url_name", "url_arg"):
                        continue
                    new[k] = self._resolve_context_urls(v)
                # If explicit href already present, keep it; else set resolved href if available
                if obj.get("href"):
                    new["href"] = obj["href"]
                elif href:
                    new["href"] = href
                else:
                    # No href resolved; keep url_name removed to avoid template reversing
                    new["href"] = None
                return new
            # Otherwise, recursively process keys
            for k, v in obj.items():
                new[k] = self._resolve_context_urls(v)
            return new

        elif isinstance(obj, (list, tuple)):
            new_list = []
            for item in obj:
                new_list.append(self._resolve_context_urls(item))
            return new_list if isinstance(obj, list) else tuple(new_list)

        else:
            # primitive type
            return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Breadcrumbs (root components expect 'href' keys)
        ctx["crumbs"] = [
            {"label": "Home", "href": "/"},
            {"label": "Doctors", "href": "/doctors/"},
            {"label": "Dashboard", "href": None},
        ]

        # Raw action definitions: prefer named routes but resolve them to hrefs here.
        raw_actions = [
            {"label": "My Appointments", "icon": "📅", "url_name": "appointments:appointment-list", "variant": "primary"},
            {"label": "My Patients",     "icon": "🧑‍⚕️", "url_name": "patients:dashboard",             "variant": "success"},
            {"label": "My Schedules",    "icon": "🕒", "url_name": "schedules:schedule-dashboard",   "variant": "info"},
            {"label": "My Reports",      "icon": "📊", "url_name": "reports:dashboard",              "variant": "secondary"},
        ]

        # Resolve actions to hrefs immediately
        resolved_actions = []
        for a in raw_actions:
            # If presenter.build_action returns a dict with url_name, we still resolve here
            href = a.get("href")
            if not href and a.get("url_name"):
                href = self._resolve_named_url(a["url_name"], a.get("url_arg"))
            if href:
                resolved_actions.append({
                    "label": a["label"],
                    "icon": a.get("icon"),
                    "href": href,
                    "variant": a.get("variant", "primary"),
                })
            else:
                # If no href resolved, we intentionally omit the action to avoid template reversing
                logger.debug("Omitting dashboard action '%s' because no href could be resolved.", a["label"])

        ctx["actions"] = resolved_actions

        # KPIs (defensive)
        try:
            ctx["kpis"] = [
                {"label": "Today Appointments", "value": dashboard_services.count_todays_appointments(self.request.user), "icon": "📅"},
                {"label": "On-Call Now",        "value": dashboard_services.count_current_oncall(self.request.user),       "icon": "🕒"},
                {"label": "Active Patients",    "value": dashboard_services.count_active_patients(self.request.user),    "icon": "🧑‍⚕️"},
            ]
        except Exception as e:
            logger.debug("Failed to compute KPIs for doctor %s: %s", getattr(self.request.user, "pk", None), e, exc_info=True)
            ctx["kpis"] = [
                {"label": "Today Appointments", "value": 0, "icon": "📅"},
                {"label": "On-Call Now",        "value": 0, "icon": "🕒"},
                {"label": "Active Patients",    "value": 0, "icon": "🧑‍⚕️"},
            ]

        # Appointments
        try:
            appts = dashboard_services.get_upcoming_appointments_for_doctor(self.request.user)
            ctx["appointments"] = [presenters.appointment_adapter(a) for a in appts] if appts else []
        except Exception as e:
            logger.debug("Failed to load appointments for doctor %s: %s", getattr(self.request.user, "pk", None), e, exc_info=True)
            ctx["appointments"] = []

        # Shifts: robust loading with fallbacks
        try:
            shifts = dashboard_services.get_upcoming_shifts_for_doctor(self.request.user)
            ctx["shifts"] = [presenters.shift_adapter(s) for s in shifts] if shifts else []
        except Exception as primary_exc:
            logger.debug("Primary shifts loader failed for doctor %s: %s", getattr(self.request.user, "pk", None), primary_exc, exc_info=True)
            # Attempt fallbacks against schedules app
            try:
                from schedules import services as schedules_services  # may raise ImportError

                fallback_names = [
                    "get_upcoming_shifts_for_doctor",
                    "get_shifts_for_doctor",
                    "get_upcoming_shifts",
                    "schedules_dashboard",
                ]

                fallback_shifts = None
                for fn in fallback_names:
                    fn_obj = getattr(schedules_services, fn, None)
                    if callable(fn_obj):
                        try:
                            fallback_shifts = fn_obj(self.request.user)
                            if fallback_shifts:
                                break
                        except Exception as e:
                            logger.debug("schedules.services.%s raised for doctor %s: %s", fn, getattr(self.request.user, "pk", None), e, exc_info=True)
                            fallback_shifts = None

                if fallback_shifts:
                    ctx["shifts"] = [presenters.shift_adapter(s) for s in fallback_shifts]
                else:
                    ctx["shifts"] = []

            except Exception as fallback_exc:
                logger.warning(
                    "Unable to load shifts for doctor %s. primary_exc=%s fallback_exc=%s",
                    getattr(self.request.user, "pk", None),
                    primary_exc,
                    fallback_exc,
                    exc_info=True
                )
                ctx["shifts"] = []

        # Patients
        try:
            patients = dashboard_services.get_active_patients_for_doctor(self.request.user)
            ctx["patients"] = [presenters.patient_adapter(p) for p in patients] if patients else []
        except Exception as e:
            logger.debug("Failed to load patients for doctor %s: %s", getattr(self.request.user, "pk", None), e, exc_info=True)
            ctx["patients"] = []

        # Reports
        try:
            reports = dashboard_services.get_recent_reports_for_doctor(self.request.user)
            ctx["reports"] = [presenters.report_adapter(r) for r in reports] if reports else []
        except Exception as e:
            logger.debug("Failed to load reports for doctor %s: %s", getattr(self.request.user, "pk", None), e, exc_info=True)
            ctx["reports"] = []

        # FINAL STEP: recursively resolve any remaining url_name/url_arg pairs anywhere in the context
        # This ensures components like `empty_state.html` never receive a url_name to reverse.
        try:
            ctx = self._resolve_context_urls(ctx)
        except Exception as e:
            # If the resolver itself fails for any reason, log and continue with the original ctx
            logger.exception("Error while resolving context URLs for doctor dashboard: %s", e)

        return ctx
