"""
views.py  —  employee app
"""
import calendar
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django import forms

from .models import Attendance, Leave


# ══════════════════════════════════════════════
#  REGISTER FORM
# ══════════════════════════════════════════════
class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=50, required=True,
        widget=forms.TextInput(attrs={'placeholder': 'First name'}))
    last_name  = forms.CharField(max_length=50, required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'}))
    email      = forms.EmailField(required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'you@company.com'}))
    class Meta(UserCreationForm.Meta):
        fields = ['username','first_name','last_name','email','password1','password2']


# ══════════════════════════════════════════════
#  MONTH CHOICES HELPER
# ══════════════════════════════════════════════
def _month_choices():
    """Returns list of dicts with value (int) and label (str) for all 12 months."""
    return [
        {'value': i, 'label': calendar.month_name[i]}
        for i in range(1, 13)
    ]

def _year_choices():
    today = timezone.localdate()
    return list(range(today.year - 2, today.year + 1))


# ══════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════
def register_view(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'Account created! Please log in, {user.first_name}.')
        return redirect('employee:login')
    elif request.method == 'POST':
        messages.error(request, 'Please fix the errors below.')
    return render(request, 'register.html', {'form': form})


def login_view(request):

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == 'POST':

        if form.is_valid():

            logout(request)

            login(request, form.get_user())

            messages.success(
                request,
                f'Welcome, {form.get_user().first_name or form.get_user().username}!'
            )

            user = form.get_user()

            # ADMIN / HRD
            if user.is_staff:
                return redirect('employee:admin_dashboard')

            # EMPLOYEE
            else:
                return redirect('employee:dashboard')

        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'login.html', {
        'form': form
    })
            
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('employee:login')


# ══════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════
@login_required
def dashboard_view(request):
    today = timezone.localdate()
    today_attendance   = Attendance.objects.filter(user=request.user, date=today).first()
    recent_attendances = Attendance.objects.filter(user=request.user).order_by('-date')[:5]
    this_month = Attendance.objects.filter(
        user=request.user, date__month=today.month, date__year=today.year)
    recent_leaves = Leave.objects.filter(user=request.user).order_by('-created_at')[:3]
    context = {
        'today':              today,
        'today_attendance':   today_attendance,
        'recent_attendances': recent_attendances,
        'recent_leaves':      recent_leaves,
        'attendance_count':   this_month.count(),
        'ontime_count':       this_month.filter(status='present').count(),
        'late_count':         this_month.filter(status='late').count(),
        'leave_count':        this_month.filter(status='leave').count(),
        'work_summary':       _work_summary(request.user, today),
        'stats':              _stats(request.user, today),
        'company_name':       'Garuda TV',
    }
    return render(request, 'dashboard.html', context)


# ══════════════════════════════════════════════
#  ATTENDANCE
# ══════════════════════════════════════════════
@login_required
def checkin_view(request):
    today = timezone.localdate()
    now   = timezone.localtime()
    today_attendance = Attendance.objects.filter(user=request.user, date=today).first()

    if request.method == 'POST':
        action    = request.POST.get('action', 'checkin')
        address   = request.POST.get('address', '')
        photo_b64 = request.POST.get('photo', '')
        try:
            lat = float(request.POST.get('latitude'))  if request.POST.get('latitude')  else None
            lng = float(request.POST.get('longitude')) if request.POST.get('longitude') else None
        except ValueError:
            lat = lng = None

        if action == 'checkin':
            if today_attendance and today_attendance.check_in:
                messages.warning(request, 'You have already checked in today.')
                return redirect('employee:checkin')
            status = _determine_status(now)
            att = Attendance(
                user=request.user, date=today, check_in=now,
                check_in_lat=lat, check_in_lng=lng,
                check_in_address=address, status=status)
            if photo_b64:
                att.save_checkin_photo(photo_b64)
            att.save()
            messages.success(request,
                f'✅ Check-in {"on time" if status=="present" else "late"} at {now.strftime("%H:%M")}')

        elif action == 'checkout':
            if not today_attendance or not today_attendance.check_in:
                messages.error(request, 'You have not checked in today.')
                return redirect('employee:checkin')
            if today_attendance.check_out:
                messages.warning(request, 'You have already checked out today.')
                return redirect('employee:checkin')
            today_attendance.check_out         = now
            today_attendance.check_out_lat     = lat
            today_attendance.check_out_lng     = lng
            today_attendance.check_out_address = address
            if photo_b64:
                today_attendance.save_checkout_photo(photo_b64)
            today_attendance.save()
            messages.success(request,
                f'👋 Check-out at {now.strftime("%H:%M")} — Duration: {today_attendance.duration or "—"}')

        return redirect('employee:checkin')

    today_attendance = Attendance.objects.filter(user=request.user, date=today).first()
    return render(request, 'attendance.html', {
        'today': today,
        'today_attendance': today_attendance,
    })


# ══════════════════════════════════════════════
#  ATTENDANCE HISTORY  ← FIXED month_choices
# ══════════════════════════════════════════════
@login_required
def attendance_history_view(request):
    today = timezone.localdate()

    # ── get selected period (default = current month/year) ──
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year  = int(request.GET.get('year',  today.year))
    except (ValueError, TypeError):
        selected_month = today.month
        selected_year  = today.year

    # clamp month to 1–12
    selected_month = max(1, min(12, selected_month))

    selected_status = request.GET.get('status', '')

    qs = Attendance.objects.filter(
        user=request.user,
        date__month=selected_month,
        date__year=selected_year,
    ).order_by('-date')

    if selected_status:
        qs = qs.filter(status=selected_status)

    # summary stats
    month_qs = Attendance.objects.filter(
        user=request.user,
        date__month=selected_month,
        date__year=selected_year,
    )
    total   = month_qs.count()
    present = month_qs.filter(status='present').count()
    late    = month_qs.filter(status='late').count()
    absent  = month_qs.filter(status='absent').count()
    leave   = month_qs.filter(status='leave').count()
    rate    = round((present + late) / total * 100, 2) if total else 0.0

    return render(request, 'attendance_history.html', {
        'attendances':     qs,
        'today':           today,
        'summary': {
            'present': present,
            'late':    late,
            'absent':  absent,
            'leave':   leave,
            'rate':    rate,
        },
        'selected_month':  selected_month,
        'selected_year':   selected_year,
        'selected_status': selected_status,
        # ✅ month_name uses calendar.month_name (January, February, ...)
        'month_name':      calendar.month_name[selected_month],
        'year':            selected_year,
        # ✅ month_choices: list of dicts with value (int) and label (str)
        'month_choices': _month_choices(),
        'year_choices':  _year_choices(),
    })


# ══════════════════════════════════════════════
#  REPORTS
# ══════════════════════════════════════════════
@login_required
def reports_view(request):
    today = timezone.localdate()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year  = int(request.GET.get('year',  today.year))
    except (ValueError, TypeError):
        selected_month = today.month
        selected_year  = today.year

    selected_month = max(1, min(12, selected_month))
    stats = _get_period_stats(request.user, selected_month, selected_year)

    return render(request, 'reports.html', {
        'stats':          stats,
        'selected_month': selected_month,
        'selected_year':  selected_year,
        'current_year':   today.year,
        # ✅ year_choices for dropdown
        'year_choices':   _year_choices(),
    })


@login_required
def report_stats_api(request):
    today = timezone.localdate()
    try:
        month = int(request.GET.get('month', today.month))
        year  = int(request.GET.get('year',  today.year))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    return JsonResponse(_get_period_stats(request.user, month, year))


@login_required
def report_pdf_view(request):
    today = timezone.localdate()
    try:
        month = int(request.GET.get('month', today.month))
        year  = int(request.GET.get('year',  today.year))
    except (ValueError, TypeError):
        month, year = today.month, today.year

    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        import io

        qs         = Attendance.objects.filter(
            user=request.user, date__month=month, date__year=year).order_by('date')
        stats      = _get_period_stats(request.user, month, year)
        month_name = calendar.month_name[month]
        full_name  = request.user.get_full_name() or request.user.username

        buf = io.BytesIO()
        c   = rl_canvas.Canvas(buf, pagesize=A4)
        W, H = A4

        # Header bar
        c.setFillColorRGB(0.118, 0.227, 0.373)
        c.rect(0, H-80, W, 80, fill=1, stroke=0)
        c.setFillColorRGB(1,1,1)
        c.setFont('Helvetica-Bold', 18)
        c.drawString(40, H-40, 'Attendance Report')
        c.setFont('Helvetica', 11)
        c.drawString(40, H-60, f'{month_name} {year}  |  {full_name}')
        c.setFont('Helvetica', 9)
        c.drawRightString(W-40, H-50, f'Generated: {today.strftime("%d %B %Y")}')

        y = H - 130
        c.setFillColorRGB(0,0,0)
        c.setFont('Helvetica-Bold', 11)
        c.drawString(40, y, 'Quick Stats')
        c.setFont('Helvetica', 10)
        y -= 20
        for label, val in [
            ('Present', stats['present']), ('Late', stats['late']),
            ('Absent',  stats['absent']),  ('Permit', stats['leave']),
            ('Rate',    f"{stats['rate']}%"),
        ]:
            c.drawString(50, y, f'{label}: {val}')
            y -= 16

        y -= 16
        c.setFont('Helvetica-Bold', 9)
        for txt, x in [('Date',55),('Day',120),('Check-In',160),('Check-Out',220),('Duration',280),('Status',360)]:
            c.drawString(x, y, txt)
        y -= 4
        c.line(40, y, W-40, y)

        c.setFont('Helvetica', 9)
        for att in qs:
            y -= 16
            if y < 60:
                c.showPage(); y = H-60; c.setFont('Helvetica', 9)
            c.drawString(55,  y, att.date.strftime('%d-%m-%Y'))
            c.drawString(120, y, att.date.strftime('%a'))
            c.drawString(160, y, att.check_in.strftime('%H:%M')  if att.check_in  else '—')
            c.drawString(220, y, att.check_out.strftime('%H:%M') if att.check_out else '—')
            c.drawString(280, y, att.duration or '—')
            c.drawString(360, y, att.get_status_display())

        c.setFont('Helvetica', 8)
        c.setFillColorRGB(0.6, 0.7, 0.8)
        c.drawCentredString(W/2, 30, f'Garuda TV  |  {full_name}  |  {month_name} {year}')
        c.save()
        buf.seek(0)

        response = HttpResponse(buf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="attendance_{month}_{year}.pdf"'
        return response

    except ImportError:
        return HttpResponse('pip install reportlab', content_type='text/plain', status=501)


# ══════════════════════════════════════════════
#  PAYROLL
# ══════════════════════════════════════════════
@login_required
def payroll_view(request):
    today = timezone.localdate()
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year  = int(request.GET.get('year',  today.year))
    except (ValueError, TypeError):
        selected_month = today.month
        selected_year  = today.year

    selected_month = max(1, min(12, selected_month))

    payroll = None
    try:
        from .models import Payroll
        payroll = Payroll.objects.get(
            user=request.user, month=selected_month, year=selected_year)
    except Exception:
        pass

    if payroll is None:
        try:
            from .models import calculate_and_save_payroll
            payroll = calculate_and_save_payroll(
                request.user, selected_month, selected_year)
        except Exception:
            payroll = None

    att_qs = Attendance.objects.filter(
        user=request.user, date__month=selected_month, date__year=selected_year)
    total_hours    = sum(a.duration_minutes for a in att_qs) / 60
    overtime_hours = sum(a.overtime_hours   for a in att_qs)
    att_summary = {
        'total_hours':    round(total_hours, 1),
        'present':        att_qs.filter(status='present').count(),
        'late':           att_qs.filter(status='late').count(),
        'overtime_hours': round(overtime_hours, 1),
    }

    overtime_details = []
    ot_records = [a for a in att_qs.filter(
        check_in__isnull=False, check_out__isnull=False) if a.overtime_hours > 0]
    for att in ot_records:
        overtime_details.append({
            'date':        att.date,
            'description': 'Weekday overtime' if att.date.weekday() < 5 else 'Weekend overtime',
            'hours':       round(att.overtime_hours, 1),
            'pay':         round(float(payroll.overtime_pay) / max(len(ot_records), 1), 0) if payroll else 0,
        })

    return render(request, 'payroll.html', {
        'payroll':          payroll,
        'att_summary':      att_summary,
        'overtime_details': overtime_details,
        'selected_month':   selected_month,
        'selected_year':    selected_year,
        'month_name':       calendar.month_name[selected_month],
        # ✅ month_choices with proper labels
        'month_choices':    _month_choices(),
        'year_choices':     _year_choices(),
    })


@login_required
def payslip_pdf_view(request):
    today = timezone.localdate()
    try:
        month = int(request.GET.get('month', today.month))
        year  = int(request.GET.get('year',  today.year))
    except (ValueError, TypeError):
        month, year = today.month, today.year

    try:
        from .models import Payroll
        payroll = Payroll.objects.get(user=request.user, month=month, year=year)
    except Exception:
        return HttpResponse('Payroll not found.', content_type='text/plain', status=404)

    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        import io

        month_name = calendar.month_name[month]
        full_name  = request.user.get_full_name() or request.user.username
        buf        = io.BytesIO()
        c          = rl_canvas.Canvas(buf, pagesize=A4)
        W, H       = A4

        c.setFillColorRGB(0.118, 0.227, 0.373)
        c.rect(0, H-90, W, 90, fill=1, stroke=0)
        c.setFillColorRGB(1,1,1)
        c.setFont('Helvetica-Bold', 20)
        c.drawString(40, H-45, 'E-Payslip')
        c.setFont('Helvetica', 11)
        c.drawString(40, H-65, f'Garuda TV — {month_name} {year}')
        c.setFont('Helvetica', 9)
        c.drawRightString(W-40, H-45, full_name)
        c.drawRightString(W-40, H-60, request.user.username)
        c.drawRightString(W-40, H-75, f'Generated: {today.strftime("%d %B %Y")}')

        y = H - 120
        c.setFillColorRGB(0,0,0)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(40, y, f'Pay Period: {month_name} {year}')
        c.setFont('Helvetica', 10)
        c.setFillColorRGB(0.086, 0.643, 0.29)
        c.drawString(40, y-18, '● Status: Approved')
        c.setFillColorRGB(0,0,0)

        y -= 36
        c.line(40, y, W-40, y)
        y -= 20

        def draw_section(title, rows, total_label, total_val, start_y):
            c.setFont('Helvetica-Bold', 10)
            c.setFillColorRGB(0.42, 0.52, 0.63)
            c.drawString(40, start_y, title.upper())
            c.setFillColorRGB(0,0,0)
            c.setFont('Helvetica', 10)
            sy = start_y - 16
            for label, val in rows:
                c.drawString(55, sy, label)
                c.drawRightString(W-40, sy, f'IDR {val:,.0f}')
                sy -= 15
            c.line(40, sy-2, W-40, sy-2)
            sy -= 14
            c.setFont('Helvetica-Bold', 11)
            c.setFillColorRGB(0.118, 0.227, 0.373)
            c.drawString(55, sy, total_label)
            c.drawRightString(W-40, sy, f'IDR {total_val:,.0f}')
            c.setFillColorRGB(0,0,0)
            return sy - 24

        y = draw_section('Earnings', [
            ('Base Salary',  float(payroll.base_salary)),
            ('Allowance',    float(payroll.allowance)),
            ('Benefits',     float(payroll.benefits)),
            ('Overtime Pay', float(payroll.overtime_pay)),
        ], 'Total Earning', float(payroll.total_earning), y)
        y -= 8

        y = draw_section('Deductions', [
            ('BPJS Kesehatan (1%)', float(payroll.bpjs)),
            ('Late Deduction',      float(payroll.late_deduction)),
            ('PPh21',               float(payroll.pph21)),
        ], 'Total Deduction', float(payroll.total_deduction), y)
        y -= 16

        c.setFillColorRGB(0.118, 0.227, 0.373)
        c.roundRect(40, y-30, W-80, 44, 6, fill=1, stroke=0)
        c.setFillColorRGB(1,1,1)
        c.setFont('Helvetica-Bold', 14)
        c.drawString(55, y-12, 'Take Home Pay (Net Salary)')
        c.drawRightString(W-55, y-12, f'IDR {float(payroll.net_salary):,.0f}')

        c.setFillColorRGB(0.6, 0.7, 0.8)
        c.setFont('Helvetica', 8)
        c.drawCentredString(W/2, 30,
            'Payroll automatically calculated from validated attendance records — Garuda TV HRD')

        c.save(); buf.seek(0)
        response = HttpResponse(buf, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="payslip_{month}_{year}_{request.user.username}.pdf"')
        return response

    except ImportError:
        return HttpResponse('pip install reportlab', content_type='text/plain', status=501)


# ══════════════════════════════════════════════
#  LEAVE
# ══════════════════════════════════════════════
@login_required
def leave_request_view(request):
    leaves = Leave.objects.filter(user=request.user).order_by('-created_at')
    stats  = {
        'total':    leaves.count(),
        'pending':  leaves.filter(status='pending').count(),
        'approved': leaves.filter(status='approved').count(),
        'rejected': leaves.filter(status='rejected').count(),
    }
    form_data = {}

    if request.method == 'POST':
        lt  = request.POST.get('leave_type', '').strip()
        sd  = request.POST.get('start_date', '').strip()
        ed  = request.POST.get('end_date',   '').strip()
        rsn = request.POST.get('reason',     '').strip()
        doc = request.FILES.get('document')
        form_data = {'leave_type': lt, 'start_date': sd, 'end_date': ed, 'reason': rsn}

        if not all([lt, sd, ed, rsn]):
            messages.error(request, '⚠ All fields are required.')
        elif sd > ed:
            messages.error(request, '⚠ End date must be after start date.')
        else:
            if doc:
                ext = '.' + doc.name.rsplit('.', 1)[-1].lower()
                if ext not in ['.pdf', '.jpg', '.jpeg', '.png']:
                    messages.error(request, '⚠ Only PDF, JPG, PNG allowed.')
                    return render(request, 'leave_request.html', {
                        'leaves': leaves, 'stats': stats,
                        'form_data': form_data, 'today': timezone.localdate()})
            Leave.objects.create(
                user=request.user, leave_type=lt,
                start_date=sd, end_date=ed,
                reason=rsn, document=doc, status='pending')
            messages.success(request, '✅ Leave request submitted!')
            return redirect('employee:leave_request')

    return render(request, 'leave_request.html', {
        'leaves': leaves, 'stats': stats,
        'form_data': form_data, 'today': timezone.localdate()})


@login_required
def leave_history_view(request):
    st = request.GET.get('status', '')
    qs = Leave.objects.filter(user=request.user).order_by('-created_at')
    if st:
        qs = qs.filter(status=st)
    return render(request, 'leave_history.html', {
        'leaves': qs, 'total_count': qs.count(), 'selected_status': st})


@login_required
def leave_cancel_view(request, pk):
    leave = get_object_or_404(Leave, pk=pk, user=request.user, status='pending')
    leave.status = 'cancelled'
    leave.save()
    messages.success(request, 'Leave request cancelled.')
    return redirect('employee:leave_request')


# ══════════════════════════════════════════════
#  PROFILE
# ══════════════════════════════════════════════
@login_required
def profile_view(request):
    google_connected = False
    try:
        google_connected = request.user.social_auth.filter(
            provider='google-oauth2').exists()
    except Exception:
        pass

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            u = request.user
            u.first_name = request.POST.get('first_name', u.first_name).strip()
            u.last_name  = request.POST.get('last_name',  u.last_name).strip()
            u.email      = request.POST.get('email',      u.email).strip()
            u.save()
            messages.success(request, '✅ Profile updated successfully!')
            return redirect('employee:profile')

        elif action == 'change_password':
            current_pw = request.POST.get('current_password', '')
            new_pw     = request.POST.get('new_password', '')
            confirm_pw = request.POST.get('confirm_password', '')

            if not request.user.check_password(current_pw):
                messages.error(request, '❌ Current password is incorrect.')
            elif len(new_pw) < 8:
                messages.error(request, '❌ Password must be at least 8 characters.')
            elif new_pw != confirm_pw:
                messages.error(request, '❌ Passwords do not match.')
            else:
                request.user.set_password(new_pw)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, '✅ Password changed successfully!')
            return redirect('employee:profile')

    return render(request, 'profile.html', {
        'google_connected': google_connected,
    })


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
def _determine_status(t):
    return 'present' if (t.hour < 8 or (t.hour == 8 and t.minute == 0)) else 'late'


def _get_period_stats(user, month, year):
    qs      = Attendance.objects.filter(user=user, date__month=month, date__year=year)
    present = qs.filter(status='present').count()
    late    = qs.filter(status='late').count()
    absent  = qs.filter(status='absent').count()
    leave   = qs.filter(status='leave').count()
    total   = qs.count()
    rate    = round((present + late) / total * 100, 2) if total else 0.0
    return {
        'present': present, 'late': late,
        'absent':  absent,  'leave': leave,
        'total':   total,   'rate': rate,
    }


def _work_summary(user, today):
    qs = Attendance.objects.filter(
        user=user, date__month=today.month, date__year=today.year,
        check_in__isnull=False, check_out__isnull=False)
    total_min, day_totals = 0, {}
    for att in qs:
        mins = att.duration_minutes
        total_min += mins
        day = att.date.strftime('%A')
        day_totals[day] = day_totals.get(day, 0) + mins
    count    = qs.count() or 1
    overtime = max(0, total_min - count * 480)
    best     = max(day_totals, key=day_totals.get) if day_totals else '—'
    best_h   = round(day_totals.get(best, 0) / 60, 1) if day_totals else 0
    return {
        'total_hours':     f'{round(total_min/60,1)}h',
        'overtime':        f'{round(overtime/60,1)}h',
        'avg_daily':       f'{round(total_min/count/60,1)}h',
        'highest_workday': f'{best} ({best_h}h)' if best != '—' else '—',
    }


def _stats(user, today):
    qs = Attendance.objects.filter(
        user=user, date__month=today.month, date__year=today.year)
    return {
        'invalid_location':  0,
        'excessive_late':    qs.filter(status='late').count(),
        'missing_clock_out': qs.filter(check_in__isnull=False, check_out__isnull=True).count(),
        'missing_photo':     qs.filter(photo_checkin='').count(),
    }

# ══════════════════════════════════════════════
#  ADMIN DASHBOARD
# ══════════════════════════════════════════════

## ADMIN

from django.contrib.auth.decorators import login_required
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from django.contrib.auth.models import User
from django.shortcuts import render, redirect

import pandas as pd
import os
import json

from django.conf import settings


@login_required
def admin_dashboard(request):

    # =========================
    # CHECK ADMIN
    # =========================

    if not request.user.is_staff:
        return redirect('employee:dashboard')

    # =========================
    # LOAD CSV
    # =========================

    file_path = os.path.join(
        settings.BASE_DIR,
        'data',
        'attendance.csv'
    )

    df = pd.read_csv(file_path)

    # =========================
    # CLEAN DATA
    # =========================

    df = df.dropna()

    status_map = {
        'Present': 0,
        'Late': 1,
        'Absent': 2,
        'Leave': 3
    }

    df['Attendance_Status'] = df['Attendance_Status'].map(status_map)

    # =========================
    # FEATURES
    # =========================

    X = df[[
        'Total_Attendance',
        'Total_Tardiness_Minutes',
        'Delay_in_Minutes'
    ]]

    y = df['Attendance_Status']

    # =========================
    # MACHINE LEARNING
    # =========================

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42
    )

    model = RandomForestClassifier()

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    accuracy = accuracy_score(y_test, predictions)

    # =========================
    # COUNTS
    # =========================

    present = (y == 0).sum()
    late = (y == 1).sum()
    absent = (y == 2).sum()
    leave = (y == 3).sum()

    # =========================
    # CHART DATA
    # =========================

    chart_labels = [
        'Present',
        'Late',
        'Absent',
        'Leave'
    ]

    chart_data = [
        int(present),
        int(late),
        int(absent),
        int(leave)
    ]

    # =========================
    # TABLE DATA
    # =========================

    employees = df.head(10).to_dict('records')

    # =========================
    # CONTEXT
    # =========================

    context = {

        'total_employees': User.objects.count(),

        'present_today': int(present),

        'absent_today': int(absent),

        'leave_requests': int(leave),

        'late_today': int(late),

        'accuracy': round(accuracy * 100, 2),

        'employees': employees,

        'chart_labels': json.dumps(chart_labels),

        'chart_data': json.dumps(chart_data),
    }

    return render(
        request,
        'admin_dashboard.html',
        context
    )