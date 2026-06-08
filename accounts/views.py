from django.contrib.auth.views import LoginView, LogoutView
from .forms import EmailLoginForm


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = 'accounts:login'
