from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from tasks import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),

    path("", views.board, name="board"),
    path("search/", views.search, name="search"),
    path("archive/", views.archive_list, name="archive_list"),
    path("archive/clear/", views.archive_clear, name="archive_clear"),
    path("completed/", views.completed_list, name="completed_list"),
    path("settings/toggle/<str:key>/", views.toggle_setting, name="toggle_setting"),
    path("settings/sort/", views.set_sort, name="set_sort"),
    path("settings/group/", views.set_group, name="set_group"),

    # tasks
    path("task/new/", views.task_new, name="task_new"),
    path("task/create/", views.task_create, name="task_create"),
    path("task/<str:task_id>/", views.task_detail, name="task_detail"),
    path("task/<str:task_id>/update/", views.task_update, name="task_update"),
    path("task/<str:task_id>/delete/", views.task_delete, name="task_delete"),
    path("task/<str:task_id>/toggle/", views.toggle_done, name="toggle_done"),
    path("task/<str:task_id>/move/<str:horizon>/", views.task_move, name="task_move"),
    path("task/<str:task_id>/copy/", views.task_copy, name="task_copy"),
    path("task/<str:task_id>/archive/", views.task_archive, name="task_archive"),
    path("task/<str:task_id>/unarchive/", views.task_unarchive, name="task_unarchive"),
    path("task/<str:task_id>/checklist/add/", views.check_item_add, name="check_item_add"),
    path("task/<str:task_id>/subtask/add/", views.subtask_add, name="subtask_add"),
    path("check/<int:item_id>/toggle/", views.toggle_check_item, name="toggle_check_item"),
    path("check/<int:item_id>/delete/", views.check_item_delete, name="check_item_delete"),

    # goal templates
    path("templates/", views.template_list, name="template_list"),
    path("templates/<str:template_id>/create-goal/", views.template_create_goal, name="template_create_goal"),

    # goals
    path("goals/", views.goal_list, name="goal_list"),
    path("goals/new/", views.goal_new, name="goal_new"),
    path("goals/create/", views.goal_create, name="goal_create"),
    path("goals/<str:goal_id>/edit/", views.goal_edit, name="goal_edit"),
    path("goals/<str:goal_id>/update/", views.goal_update, name="goal_update"),
    path("goals/<str:goal_id>/delete/", views.goal_delete, name="goal_delete"),
    path("goals/<str:goal_id>/archive/", views.goal_archive, name="goal_archive"),
    path("goals/<str:goal_id>/unarchive/", views.goal_unarchive, name="goal_unarchive"),

    # contexts
    path("contexts/", views.context_list, name="context_list"),
    path("contexts/create/", views.context_create, name="context_create"),
    path("contexts/<str:context_id>/delete/", views.context_delete, name="context_delete"),
]
