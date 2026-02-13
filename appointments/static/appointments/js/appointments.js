document.getElementById("appointment-filter-form")?.addEventListener("submit", function(e) {
  e.preventDefault();
  const date = document.getElementById("filter-date").value;
  const status = document.getElementById("filter-status").value;

  console.log("Filtering appointments:", { date, status });
  // TODO: Implement AJAX filtering if needed
});

function viewAppointment(id) {
  window.location.href = `/appointments/${id}/`;
}

function openConfirmModal(id) {
  document.getElementById("confirmationModal").style.display = "block";
  document.getElementById("confirmCancel").setAttribute("data-id", id);
}

function closeConfirmModal() {
  document.getElementById("confirmationModal").style.display = "none";
}

document.getElementById("confirmCancel")?.addEventListener("click", function() {
  const id = this.getAttribute("data-id");
  alert(`Appointment ${id} cancelled successfully`);
  closeConfirmModal();
});
