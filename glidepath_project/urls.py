from django.urls import path
from glidepath_app.views import upload_rules, export_rules

urlpatterns = [
    path('', upload_rules, name='home'),
    path('export/', export_rules, name='export_rules'),
]
