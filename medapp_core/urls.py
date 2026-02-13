"""
URL configuration for medapp_core project.

This file preserves your existing routes and adds a couple of safe, optional
development conveniences:
- Serves MEDIA files in DEBUG mode (useful for local testing).
- Optionally exposes DRF's login views for the browsable API (api-auth).
All existing app includes and the simple home_view are left intact.
"""
from accounts.views import LogoutView
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from django.views.generic import TemplateView

# Development-only static/media serving helpers
from django.conf import settings
from django.conf.urls.static import static


# Simple homepage view (keeps your original behavior)
def home_view(request):
    return render(request, 'pages/home.html')


urlpatterns = [
    # -------------------------------
    # Core + Admin
    # -------------------------------
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),

    # App routes (preserve existing order and names)
    path('doctors/', include('doctors.urls')),
     path('accounts/', include('accounts.urls')),  # intentionally commented in original
    path('adminpanel/', include('adminpanel.urls')),
    path('appointments/', include('appointments.urls')),
    path('departments/', include('departments.urls')),
    path('hospitals/', include('hospitals.urls')),
    path('api/ml/', include('mlmodule.urls')),
    path('patients/', include('patients.urls')),
    path('prescriptions/', include('prescriptions.urls')),
    path('reports/', include('reports.urls')),
    path('schedules/', include('schedules.urls')),
    path("logout/", LogoutView.as_view(), name="logout"),

    # -------------------------------
    # Utility + Staging
    # -------------------------------
    path('staging/', TemplateView.as_view(template_name='pages/staging.html'), name='staging'),

    # -------------------------------
    # DRF Browsable API login/logout
    # -------------------------------
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]


# -------------------------------
# Development-only static/media serving
# -------------------------------
if settings.DEBUG:
    # Serve user-uploaded media files
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Optionally serve static files from STATIC_ROOT in dev
    # Uncomment if needed:
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
