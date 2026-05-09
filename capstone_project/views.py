from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth import login

def register_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return redirect("employee:register")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("employee:register")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name
        )

        messages.success(request, "Account created successfully. Please login.")
        return redirect("employee:login")

    return render(request, "register.html")