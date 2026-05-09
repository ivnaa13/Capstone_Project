from django.urls import path
from . import views

app_name = 'employee'

urlpatterns = [

    # ── Authentication ────────────────────────────────
    path('login/',    views.login_view,    name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/',   views.logout_view,   name='logout'),

    # ── Dashboard ─────────────────────────────────────
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # ── Attendance ────────────────────────────────────
    path('attendance/',         views.checkin_view,            name='checkin'),
    path('attendance/history/', views.attendance_history_view, name='attendance_history'),

    # ── Reports ───────────────────────────────────────
    path('reports/',       views.reports_view,    name='reports'),
    path('reports/stats/', views.report_stats_api, name='report_stats'),
    path('reports/pdf/',   views.report_pdf_view,  name='report_pdf'),

    # ── Leave ─────────────────────────────────────────
    path('leave/',                 views.leave_request_view, name='leave_request'),
    path('leave/history/',         views.leave_history_view, name='leave_history'),
    path('leave/<int:pk>/cancel/', views.leave_cancel_view,  name='leave_cancel'),

    # ── Payroll ───────────────────────────────────────
    path('payroll/',     views.payroll_view,     name='payroll'),
    path('payroll/pdf/', views.payslip_pdf_view, name='payslip_pdf'),

    # ── Profile ───────────────────────────────────────
    path('profile/', views.profile_view, name='profile'),
]