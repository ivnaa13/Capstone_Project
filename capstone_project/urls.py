from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),

    # Redirect root → login
    path('', lambda req: redirect('employee:login'), name='root'),

    # Employee app — semua URL ada di bawah /employee/
    path('employee/', include('employee.urls', namespace='employee')),
]

# Serve media files saat development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)