// Basic client-side validation for appointment booking confirmation
function validateAppointmentDetails(date, time) {
  if (!date || !time) {
    alert("Please fill in both date and time fields.");
    return false;
  }
  return true;
}

function validateCancellation(status) {
  if (status === "Completed") {
    alert("Completed appointments cannot be cancelled.");
    return false;
  }
  return true;
}
