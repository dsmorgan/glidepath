from django.urls import path
from hello.views import home

urlpatterns = [
    path('', home, name='home'),
]
