"""
accounts/views.py

Combined HTML and API views for the accounts app.

- HTML views: RegisterView, LoginView, LogoutView, ProfileView, ProfileUpdateView,
  PasswordChangeView, PasswordResetRequestView, PasswordResetDoneView,
  PasswordResetConfirmView, PasswordResetCompleteView, EmailVerificationView.

- API views: lightweight DRF endpoints for registration, JWT login, logout, profile,
  password change, password reset placeholders, email verification placeholder,
  and user activity listing.

Design goals:
- Email-first authentication: try email login first, then username.
- Defensive activity logging: always provide safe defaults for ip_address and user_agent;
  wrap writes in try/except so logging never breaks the request flow.
- Minimal, clear API endpoints: use existing forms for validation to keep behavior consistent.
"""

from typing import Optional
import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

# Local forms and models
from .forms import (
    CustomUserRegistrationForm,
    CustomAuthenticationForm,
    UserProfileUpdateForm,
    PasswordChangeForm,
    PasswordResetRequestForm,
    PasswordResetConfirmForm,
)
from .models import CustomUser, UserActivity, VerificationToken

# DRF imports (API views)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.views import TokenObtainPairView


# ---------------------------
# Small helpers
# ---------------------------

def _get_client_ip(request) -> Optional[str]:
    """
    Return the client's IP address in a best-effort way.
    - Honors X-Forwarded-For if present (first entry).
    - Falls back to REMOTE_ADDR.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_user_agent(request) -> str:
    """
    Return the User-Agent header or a safe default.
    This prevents NOT NULL IntegrityErrors when logging activities.
    """
    return request.META.get("HTTP_USER_AGENT") or "unknown"


def _create_verification_token(user, token_type="PASSWORD_RESET", days_valid=1):
    """
    Create and return a VerificationToken for the given user.
    """
    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(days=days_valid)
    vt = VerificationToken.objects.create(
        user=user,
        token=token,
        token_type=token_type,
        expires_at=expires_at,
    )
    return vt


# ---------------------------
# HTML Views (server-rendered)
# ---------------------------

class RegisterView(View):
    """
    HTML registration view.
    """
    template_name = "accounts/register.html"
    form_class = CustomUserRegistrationForm

    def get(self, request):
        return render(request, self.template_name, {"form": self.form_class()})

    def post(self, request):
        form = self.form_class(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        user = form.save(commit=False)
        user.email = (form.cleaned_data.get("email") or "").strip().lower()
        user.role = form.cleaned_data.get("role")
        user.first_name = form.cleaned_data.get("first_name")
        user.last_name = form.cleaned_data.get("last_name")
        user.phone = form.cleaned_data.get("phone")
        user.save()

        try:
            UserActivity.objects.create(
                user=user,
                action="REGISTER",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={"role": user.role, "email": user.email},
            )
        except Exception:
            pass

        messages.success(request, "Account created successfully. Please sign in.")
        return redirect(reverse("accounts:login"))


class LoginView(View):
    """
    HTML login view (email-first).
    """
    template_name = "accounts/login.html"
    form_class = CustomAuthenticationForm

    def get(self, request):
        return render(request, self.template_name, {"form": self.form_class()})

    def post(self, request):
        form = self.form_class(request, data=request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        identifier = (form.cleaned_data.get("username") or "").strip()
        password = form.cleaned_data.get("password")

        user = None
        # Try email first (normalize for case-insensitive match)
        if "@" in identifier:
            candidate = CustomUser.objects.filter(email__iexact=identifier.strip().lower()).first()
            if candidate:
                user = authenticate(request, username=candidate.username, password=password)

        # Fallback to username
        if user is None:
            user = authenticate(request, username=identifier, password=password)

        if user is None:
            messages.error(request, "Invalid email/username or password.")
            return render(request, self.template_name, {"form": form})

        login(request, user)

        try:
            UserActivity.objects.create(
                user=user,
                action="LOGIN",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={},
            )
        except Exception:
            pass

        # Role-based redirect
        if user.is_patient():
            return redirect("patients:dashboard")
        if user.is_doctor():
            return redirect("doctors:dashboard")
        if user.is_hospital():
            return redirect("hospitals:dashboard")
        if user.is_admin():
            return redirect("adminpanel:dashboard")

        # Fallback if no role matched
        return redirect("accounts:profile")


class LogoutView(LoginRequiredMixin, View):
    """
    HTML logout view. Supports POST and GET (GET calls POST).
    """
    def post(self, request):
        try:
            UserActivity.objects.create(
                user=request.user,
                action="LOGOUT",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={},
            )
        except Exception:
            pass
        logout(request)
        messages.info(request, "You have been signed out.")
        return redirect(reverse("accounts:login"))

    def get(self, request):
        # Allow GET for convenience if your dropdown uses an anchor link
        return self.post(request)


class ProfileView(LoginRequiredMixin, View):
    """
    Simple profile display view.
    """
    template_name = "accounts/profile.html"

    def get(self, request):
        return render(request, self.template_name, {"user": request.user})


class ProfileUpdateView(LoginRequiredMixin, View):
    """
    Profile update view using UserProfileUpdateForm.
    """
    template_name = "accounts/profile_edit.html"
    form_class = UserProfileUpdateForm

    def get(self, request):
        form = self.form_class(instance=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = self.form_class(request.POST, instance=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        user = form.save()
        try:
            UserActivity.objects.create(
                user=user,
                action="PROFILE_UPDATE",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={},
            )
        except Exception:
            pass
        messages.success(request, "Profile updated.")
        return redirect(reverse("accounts:profile"))


# ---------------------------
# Password change / reset / verification (HTML)
# ---------------------------

class PasswordChangeView(LoginRequiredMixin, View):
    """
    HTML view to change password for authenticated users.
    Uses PasswordChangeForm from accounts/forms.py.
    """
    template_name = "accounts/password_change.html"
    form_class = PasswordChangeForm

    def get(self, request):
        form = self.form_class(user=request.user)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = self.form_class(user=request.user, data=request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        # form handles old password verification
        new_password = form.cleaned_data.get("new_password1")
        request.user.set_password(new_password)
        request.user.save()
        try:
            UserActivity.objects.create(
                user=request.user,
                action="PASSWORD_CHANGE",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={},
            )
        except Exception:
            pass
        messages.success(request, "Password changed successfully. Please sign in again.")
        logout(request)
        return redirect(reverse("accounts:login"))


class PasswordResetRequestView(View):
    """
    HTML view to request a password reset.
    Creates a VerificationToken and (optionally) sends an email with the token link.
    """
    template_name = "accounts/password_reset.html"
    form_class = PasswordResetRequestForm

    def get(self, request):
        return render(request, self.template_name, {"form": self.form_class()})

    def post(self, request):
        form = self.form_class(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        email = (form.cleaned_data.get("email") or "").strip().lower()
        user = CustomUser.objects.filter(email__iexact=email).first()
        if user:
            try:
                vt = _create_verification_token(user, token_type="PASSWORD_RESET", days_valid=1)
                # Send email with reset link (best-effort; fail silently)
                reset_link = request.build_absolute_uri(reverse("accounts:password_reset_confirm", args=[vt.token]))
                try:
                    send_mail(
                        subject="MedApp password reset",
                        message=f"Use the following link to reset your password:\n\n{reset_link}\n\nThis link expires in 24 hours.",
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            except Exception:
                pass

        # Always show the same response to avoid account enumeration
        return redirect(reverse("accounts:password_reset_done"))


class PasswordResetDoneView(TemplateView):
    """
    Simple page telling the user to check their email.
    """
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(View):
    """
    HTML view to confirm password reset using a token.
    URL pattern: password/reset/confirm/<str:token>/
    """
    template_name = "accounts/password_reset_confirm.html"
    form_class = PasswordResetConfirmForm

    def get(self, request, token):
        vt = VerificationToken.objects.filter(token=token, token_type="PASSWORD_RESET", is_used=False).first()
        if not vt or vt.expires_at < timezone.now():
            messages.error(request, "Invalid or expired password reset token.")
            return redirect(reverse("accounts:password_reset"))
        form = self.form_class()
        return render(request, self.template_name, {"form": form, "token": token})

    def post(self, request, token):
        vt = VerificationToken.objects.filter(token=token, token_type="PASSWORD_RESET", is_used=False).first()
        if not vt or vt.expires_at < timezone.now():
            messages.error(request, "Invalid or expired password reset token.")
            return redirect(reverse("accounts:password_reset"))

        form = self.form_class(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "token": token})

        new_password = form.cleaned_data.get("new_password1")
        user = vt.user
        user.set_password(new_password)
        user.save()
        vt.is_used = True
        vt.save()

        try:
            UserActivity.objects.create(
                user=user,
                action="PASSWORD_RESET",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={},
            )
        except Exception:
            pass

        return redirect(reverse("accounts:password_reset_complete"))


class PasswordResetCompleteView(TemplateView):
    """
    Page shown after successful password reset.
    """
    template_name = "accounts/password_reset_complete.html"


class EmailVerificationView(View):
    """
    HTML view to verify email using a token in the URL:
    /accounts/verify-email/<str:token>/
    """
    def get(self, request, token):
        vt = VerificationToken.objects.filter(token=token, token_type="EMAIL", is_used=False).first()
        if not vt or vt.expires_at < timezone.now():
            messages.error(request, "Invalid or expired verification token.")
            return redirect(reverse("accounts:login"))

        user = vt.user
        user.is_verified = True
        user.save()
        vt.is_used = True

        try:
            UserActivity.objects.create(
                user=user,
                action="VERIFICATION",
                ip_address=_get_client_ip(request),
                user_agent=_get_user_agent(request),
                metadata={"method": "email_token"},
            )
        except Exception:
            pass

        messages.success(request, "Email verified. You can now sign in.")
        return redirect(reverse("accounts:login"))


# ---------------------------
# Lightweight DRF API Views
# ---------------------------

class UserLoginAPIView(TokenObtainPairView):
    """
    JWT token obtain endpoint (login).
    Uses djangorestframework-simplejwt's TokenObtainPairView.
    """
    permission_classes = [permissions.AllowAny]


class UserRegistrationAPIView(APIView):
    """
    API endpoint for user registration.
    Accepts the same fields as the HTML registration form.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data.copy()
        form = CustomUserRegistrationForm(data)
        if not form.is_valid():
            return Response({"errors": form.errors}, status=status.HTTP_400_BAD_REQUEST)

        user = form.save(commit=False)
        user.email = (form.cleaned_data.get("email") or "").strip().lower()
        user.role = form.cleaned_data.get("role")
        user.first_name = form.cleaned_data.get("first_name")
        user.last_name = form.cleaned_data.get("last_name")
        user.phone = form.cleaned_data.get("phone")
        user.save()

        try:
            UserActivity.objects.create(
                user=user,
                action="REGISTER",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT") or "unknown",
                metadata={"role": user.role, "email": user.email},
            )
        except Exception:
            pass

        return Response({
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }, status=status.HTTP_201_CREATED)


class UserLogoutAPIView(APIView):
    """
    Minimal logout endpoint. For JWT-based auth, clients typically discard tokens.
    We still record a LOGOUT activity for auditing.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            UserActivity.objects.create(
                user=request.user,
                action="LOGOUT",
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT") or "unknown",
                metadata={},
            )
        except Exception:
            pass
        return Response({"detail": "Logged out"}, status=status.HTTP_200_OK)


class UserProfileAPIView(APIView):
    """
    Return basic profile information for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.pk,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "phone": user.phone,
        })


class PasswordChangeAPIView(APIView):
    """
    Change password for authenticated users (API).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        old = request.data.get("old_password")
        new1 = request.data.get("new_password1")
        new2 = request.data.get("new_password2")
        if not request.user.check_password(old):
            return Response({"detail": "Current password incorrect"}, status=status.HTTP_400_BAD_REQUEST)
        if not new1 or new1 != new2:
            return Response({"detail": "New passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new1)
        request.user.save()
        return Response({"detail": "Password changed"}, status=status.HTTP_200_OK)


class PasswordResetRequestAPIView(APIView):
    """
    Placeholder for password reset request (API).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        user = CustomUser.objects.filter(email__iexact=email).first()
        if user:
            try:
                vt = _create_verification_token(user, token_type="PASSWORD_RESET", days_valid=1)
                # Optionally send email (best-effort)
                reset_link = request.build_absolute_uri(reverse("accounts:password_reset_confirm", args=[vt.token]))
                try:
                    send_mail(
                        subject="MedApp password reset",
                        message=f"Use the following link to reset your password:\n\n{reset_link}\n\nThis link expires in 24 hours.",
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                        recipient_list=[user.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass
            except Exception:
                pass
        return Response({"detail": "If an account exists, a reset email will be sent"}, status=status.HTTP_200_OK)


class PasswordResetConfirmAPIView(APIView):
    """
    Placeholder for password reset confirm (API).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({"detail": "Password reset confirm endpoint not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)


class EmailVerificationAPIView(APIView):
    """
    Placeholder for email verification (API).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({"detail": "Email verification endpoint not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)


class UserActivityListAPIView(APIView):
    """
    Return recent activities for the authenticated user (up to 50).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = UserActivity.objects.filter(user=request.user).order_by("-created_at")[:50]
        data = [
            {
                "action": a.action,
                "ip_address": a.ip_address,
                "user_agent": a.user_agent,
                "metadata": a.metadata,
                "created_at": a.created_at,
            }
            for a in qs
        ]
        return Response({"activities": data}, status=status.HTTP_200_OK)
