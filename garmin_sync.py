#!/usr/bin/env python3
import os
import json
from datetime import date

from garminconnect import Garmin

DATA_DIR = "garmin_data"


def fetch_metric(fn, *args):
    try:
        return fn(*args), None
    except Exception as e:
        return None, str(e)


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("❌ Missing GARMIN_EMAIL / GARMIN_PASSWORD environment variables")
        return

    print("🔐 Logging in to Garmin Connect (read-only)...")
    client = Garmin(email, password)
    client.login()
    print("✅ Logged in")

    today = date.today().isoformat()
    result = {"date": today, "errors": {}}

    metrics = {
        "sleep": (client.get_sleep_data, today),
        "heart_rates": (client.get_heart_rates, today),
        "hrv": (client.get_hrv_data, today),
        "body_battery": (client.get_body_battery, today, today),
        "stress": (client.get_stress_data, today),
        "training_readiness": (client.get_training_readiness, today),
        "activities": (client.get_activities_by_date, today, today),
    }

    for key, (fn, *args) in metrics.items():
        print(f"📥 Fetching {key}...")
        value, error = fetch_metric(fn, *args)
        result[key] = value
        if error:
            result["errors"][key] = error
            print(f"⚠️ {key} failed: {error}")

    heart_rates = result.get("heart_rates") or {}
    if isinstance(heart_rates, dict):
        result["resting_heart_rate"] = heart_rates.get("restingHeartRate")

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f"{today}.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"✅ Saved {out_path}")


if __name__ == "__main__":
    main()
