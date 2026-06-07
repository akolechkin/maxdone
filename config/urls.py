from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from tasks import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.board, name="board"),
    path("task/<str:task_id>/", views.task_detail, name="task_detail"),
    path("task/<str:task_id>/toggle/", views.toggle_done, name="toggle_done"),
    path("check/<int:item_id>/toggle/", views.toggle_check_item, name="toggle_check_item"),
]
