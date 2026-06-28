from django.urls import path

from guideapp import views

urlpatterns = [
    path("", views.guide, name="guide"),
]
