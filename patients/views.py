from django.shortcuts import render, get_object_or_404, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.core.paginator import Paginator
from django.db.models import Q
from .forms import DiabetesForm
from mlmodule.diabetes_predictor import predict_diabetes

from .serializers import (
    PatientProfileSerializer,
    SaveDoctorSerializer,
    MedicalRecordUploadSerializer
)
from .services import (
    ensure_profile_for_user,
    add_favorite_doctor,
    delete_favorite_doctor,
    upload_medical_record,
    get_records
)

from reports.models import Report
from prescriptions.models import Prescription
from appointments.models import Appointment
from doctors.models import DoctorProfile
from doctors.services import get_available_slots
from patients.models import PatientProfile

# ✅ NEW imports for urgency predictor
from .forms import UrgencyForm
from mlmodule.predictor import predict_urgency
from django.contrib.auth.decorators import login_required

# -------------------------------
# Dashboard View
# -------------------------------
@login_required
def dashboard_view(request):
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    try:
        patient = PatientProfile.objects.get(user=request.user)
    except PatientProfile.DoesNotExist:
        return render(request, 'patients/dashboard.html', {
            'reports': Report.objects.none(),
            'prescriptions': Prescription.objects.none(),
            'appointments': Appointment.objects.none(),
        })

    reports = Report.objects.filter(patient=patient).order_by('-generated_at')[:5]
    prescriptions = Prescription.objects.filter(appointment__patient=patient).order_by('-created_at')[:5]
    appointments = Appointment.objects.filter(patient=patient).order_by('-scheduled_time')[:5]

    context = {
        'patient': patient,
        'reports': reports,
        'prescriptions': prescriptions,
        'appointments': appointments,
    }
    return render(request, 'patients/dashboard.html', context)


# -------------------------------
# Doctor List View (Patient-facing)
# -------------------------------
def doctor_list_view(request):
    query = request.GET.get("q", "")
    city = request.GET.get("city", "")
    specialty = request.GET.get("specialty", "")

    doctors = DoctorProfile.objects.select_related("user").all()

    if query:
        doctors = doctors.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(qualification__icontains=query) |
            Q(bio__icontains=query)
        )

    if city:
        doctors = doctors.filter(city__iexact=city)

    if specialty:
        doctors = doctors.filter(specialization=specialty)

    paginator = Paginator(doctors, 10)
    page = request.GET.get("page")
    page_obj = paginator.get_page(page)

    crumbs = [
        {"label": "Home", "url": "/"},
        {"label": "Find a Doctor", "url": None},
    ]

    return render(request, "patients/doctor_list.html", {
        "doctors": page_obj,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "crumbs": crumbs,
    })


# -------------------------------
# Doctor Detail View (Patient-facing)
# -------------------------------
def doctor_detail_view(request, doctor_id):
    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    selected_date = request.GET.get("date")

    slots = []
    if selected_date:
        slots = get_available_slots(doctor, selected_date)

    crumbs = [
        {"label": "Home", "url": "/"},
        {"label": "Find a Doctor", "url": "/patients/doctors/"},
        {"label": doctor.user.get_full_name(), "url": None},
    ]

    return render(request, "patients/doctor_detail.html", {
        "doctor": doctor,
        "slots": slots,
        "selected_date": selected_date,
        "crumbs": crumbs,
    })


# -------------------------------
#  Urgency Predictor View
# -------------------------------
def urgency_predict_view(request):
    """
    Patient-facing view for urgency prediction.
    - Renders a form for vitals input.
    - On POST, calls mlmodule.predictor.predict_urgency().
    - Displays prediction label + probabilities.
    """
    result = None

    if request.method == "POST":
        form = UrgencyForm(request.POST)
        if form.is_valid():
            vitals = form.cleaned_data
            result = predict_urgency(vitals)
    else:
        form = UrgencyForm()

    crumbs = [
        {"label": "Home", "url": "/"},
        {"label": "Urgency Predictor", "url": None},
    ]

    return render(request, "patients/urgency.html", {
        "form": form,
        "result": result,
        "crumbs": crumbs,
    })

# -------------------------------
# Diabetes Predictor View
# -------------------------------
def diabetes_predict_view(request):
    result = None

    if request.method == "POST":
        form = DiabetesForm(request.POST)
        if form.is_valid():
            features = form.cleaned_data
            result = predict_diabetes(features)
    else:
        form = DiabetesForm()

    crumbs = [
        {"label": "Home", "url": "/"},
        {"label": "Diabetes Predictor", "url": None},
    ]

    return render(request, "patients/diabetes.html", {
        "form": form,
        "result": result,
        "crumbs": crumbs,
    })

# -------------------------------
# API Views
# -------------------------------
class PatientProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = ensure_profile_for_user(request.user)
        serializer = PatientProfileSerializer(profile)
        return Response(serializer.data)


class SaveDoctorView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SaveDoctorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doctor_id = serializer.validated_data['doctor_id']
        obj, created = add_favorite_doctor(request.user, doctor_id)
        return Response({'saved': created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        serializer = SaveDoctorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        delete_favorite_doctor(request.user, serializer.validated_data['doctor_id'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MedicalRecordUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MedicalRecordUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = upload_medical_record(
            request.user,
            serializer.validated_data['title'],
            request.FILES['file'],
            serializer.validated_data.get('notes', '')
        )
        return Response(MedicalRecordUploadSerializer(record).data, status=status.HTTP_201_CREATED)

    def get(self, request):
        records = get_records(request.user)
        serializer = MedicalRecordUploadSerializer(records, many=True)
        return Response(serializer.data)


# -------------------------------
# Static Page Views
# -------------------------------
def patient_list_view(request):
    return render(request, 'patients/list.html')

def staging_view(request):
    return render(request, 'pages/staging.html')

def profile_page_view(request):
    return render(request, 'patients/profile.html')

def history_view(request):
    return render(request, 'patients/history.html')
