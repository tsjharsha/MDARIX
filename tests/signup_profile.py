"""The answers every trial sign-up must give (backend/app/trial/request_profile.py), for tests whose subject is something
else about the sign-up. Never a password: the requester creates it from the invitation email."""

PROFILE = {"job_title": "Quality Lead", "country": "United States", "no_patient_data": True}

# What the review email lists for PROFILE (request_profile.describe).
PROFILE_LINES = (("Job title", "Quality Lead"), ("Country", "United States"), ("No patient data", "Confirmed"))
