import os
import sys

# 🔥 FIX PATH
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

import django
import pandas as pd

print("STEP 1: PATH FIXED")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'capstone_project.settings')
django.setup()

print("STEP 2: DJANGO READY")

from django.contrib.auth.models import User
from django.conf import settings

file_path = os.path.join(settings.BASE_DIR, 'data', 'attendance.csv')

print("FILE:", file_path)
print("ADA?", os.path.exists(file_path))

df = pd.read_csv(file_path)

print("KOLOM:", df.columns)

for i, row in df.iterrows():
    username = row['Full_Name']
    password = str(row['Staff_Code'])

    if not User.objects.filter(username=username).exists():
        User.objects.create_user(
            username=username,
            password=password
        )
        print("✅ BUAT:", username)
    else:
        print("⚠ SUDAH ADA:", username)

print("🔥 DONE")