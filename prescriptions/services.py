from .models import Prescription, Medication
from doctors.models import DoctorProfile
from patients.models import PatientProfile
from appointments.models import Appointment

def create_prescription_with_medications(data, user):
    doctor = DoctorProfile.objects.get(user=user)
    patient_id = data.get("patient")
    notes = data.get("notes")

    # Try to find an appointment between this doctor and patient
    appointment = Appointment.objects.filter(
        doctor=doctor,
        patient_id=patient_id,
        status="confirmed"
    ).first()

    if not appointment:
        # Instead of raising ValueError, return None and let the view handle it
        return None, "No confirmed appointment found for this patient and doctor. Please schedule or confirm an appointment first."

    # ✅ Create prescription linked to appointment
    prescription = Prescription.objects.create(
        appointment=appointment,
        notes=notes
    )

    # Add medications
    medications_data = data.get("medications", [])
    for med in medications_data:
        Medication.objects.create(
            prescription=prescription,
            name=med.get("name"),
            dosage=med.get("dosage"),
            frequency=med.get("frequency"),
            duration=med.get("duration")
        )

    return prescription, None
