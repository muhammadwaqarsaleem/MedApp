from django.shortcuts import render, get_object_or_404, redirect
from .models import Prescription
from .forms import PrescriptionForm, MedicationForm
from .services import create_prescription_with_medications
from django.contrib import messages


def prescription_list(request):
    """
    List prescriptions for the logged-in user.
    - If the user is a patient, show prescriptions linked to their appointments.
    - If the user is a doctor, show prescriptions they have authored.
    """
    if hasattr(request.user, "patientprofile"):
        # Logged-in user is a patient
        prescriptions = Prescription.objects.filter(
            appointment__patient__user=request.user
        ).select_related("appointment", "appointment__doctor")
    elif hasattr(request.user, "doctorprofile"):
        # Logged-in user is a doctor
        prescriptions = Prescription.objects.filter(
            appointment__doctor__user=request.user
        ).select_related("appointment", "appointment__patient")
    else:
        prescriptions = Prescription.objects.none()

    return render(request, "prescriptions/list.html", {"prescriptions": prescriptions})


def create_prescription(request):
    if request.method == "POST":
        form = PrescriptionForm(request.POST)
        if form.is_valid():
            prescription, error_message = create_prescription_with_medications(
                form.cleaned_data, request.user
            )
            if error_message:
                # Show a friendly message instead of crashing
                messages.error(request, error_message)
                return redirect("prescriptions:create")
            return redirect("prescriptions:list")
    else:
        form = PrescriptionForm()

    return render(request, "prescriptions/create.html", {"form": form})
