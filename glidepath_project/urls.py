from django.urls import path
from glidepath_app.views import (
    home,
    rules_view,
    funds_view,
    accounts_view,
    portfolios_view,
    modeling_view,
    settings_view,
    logout_view,
    export_rules,
    query_ticker,
)

urlpatterns = [
    path('', home, name='home'),
    path('rules/', rules_view, name='rules'),
    path('funds/', funds_view, name='funds'),
    path('accounts/', accounts_view, name='accounts'),
    path('portfolios/', portfolios_view, name='portfolios'),
    path('modeling/', modeling_view, name='modeling'),
    path('settings/', settings_view, name='settings'),
    path('logout/', logout_view, name='logout'),
    path('export/', export_rules, name='export_rules'),
    path('api/query-ticker/', query_ticker, name='query_ticker'),
]
