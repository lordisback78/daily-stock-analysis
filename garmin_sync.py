#!/usr/bin/env python3
import os
import json
from datetime import date, timedelta

from garminconnect import Garmin

DATA_DIR = "garmin_data"
DAYS_BACK = 3


def fetch_metric(fn, *args):
    try:
        return fn(*args), None
    except Exception as e:
        return None, str(e)


def fetch_day(client, day):
    result = {"date": day, "errors": {}}

    metrics = {
        "sleep": (client.get_sleep_data, day),
        "heart_rates": (client.get_heart_rates, day),
        "hrv": (client.get_hrv_data, day),
        "body_battery": (client.get_body_battery, day, day),
        "stress": (client.get_stress_data, day),
        "training_readiness": (client.get_training_readiness, day),
        "activities": (client.get_activities_by_date, day, day),
    }

    for key, (fn, *args) in metrics.items():
        print(f"📥 Fetching {key} for {day}...")
        value, error = fetch_metric(fn, *args)
        result[key] = value
        if error:
            result["errors"][key] = error
            print(f"⚠️ {key} failed: {error}")

    heart_rates = result.get("heart_rates") or {}
    if isinstance(heart_rates, dict):
        result["resting_heart_rate"] = heart_rates.get("restingHeartRate")

    return result


def main():
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("❌ Missing GARMIN_EMAIL / GARMIN_PASSWORD environment variables")
        return

    print("🔐 Logging in to Garmin Connect (read-only)...")
    client = Garmin(email, password)
    client.login()
    print(f"✅ Logged in as {client.get_full_name()}")

    os.makedirs(DATA_DIR, exist_ok=True)

    for offset in range(DAYS_BACK):
        day = (date.today() - timedelta(days=offset)).isoformat()
        result = fetch_day(client, day)
        out_path = os.path.join(DATA_DIR, f"{day}.json")
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"✅ Saved {out_path}")


if __name__ == "__main__":
    main()
