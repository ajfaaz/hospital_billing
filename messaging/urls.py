from django.urls import path
from . import views

urlpatterns = [
    path("thread/<int:thread_id>/", views.thread_detail, name="thread_detail"),
    path("conversation/<int:user_id>/", views.conversation_view, name="conversation"),

]

