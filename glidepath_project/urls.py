from django.urls import path
from glidepath_app.views import (
    home,
    rules_view,
    funds_view,
    accounts_view,
    portfolios_view,
    modeling_view,
    logout_view,
    export_rules,
)

urlpatterns = [
    path('', home, name='home'),
    path('rules/', rules_view, name='rules'),
    path('funds/', funds_view, name='funds'),
    path('accounts/', accounts_view, name='accounts'),
    path('portfolios/', portfolios_view, name='portfolios'),
    path('modeling/', modeling_view, name='modeling'),
    path('logout/', logout_view, name='logout'),
    path('export/', export_rules, name='export_rules'),
]
