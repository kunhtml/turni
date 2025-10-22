#!/usr/bin/env python3
"""Check subscription status with Vietnam timezone"""

import json
from datetime import datetime
import pytz

# Load subscriptions
with open("subscriptions.json", "r") as f:
    subscriptions = json.load(f)

# Vietnam timezone
vietnam_tz = pytz.timezone('Asia/Ho_Chi_Minh')
now_vietnam = datetime.now(vietnam_tz)

print("=" * 70)
print("SUBSCRIPTION STATUS CHECK - Vietnam Time (GMT+7)")
print("=" * 70)
print(f"\n🕐 Current Time (Vietnam): {now_vietnam.strftime('%Y-%m-%d %H:%M:%S %Z')}")
print("\n" + "-" * 70)

for user_id, data in subscriptions.items():
    print(f"\n👤 User ID: {user_id}")
    plan_type = data.get('plan_type') or data.get('type', 'unknown')
    print(f"   Plan Type: {plan_type}")
    
    if "end_date" in data:
        end_date_str = data["end_date"]
        try:
            # Parse the end date
            if "T" in end_date_str:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            else:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
            
            # Make it timezone aware (assume UTC from storage)
            if end_date.tzinfo is None:
                end_date = pytz.UTC.localize(end_date)
            
            # Convert to Vietnam time
            end_date_vietnam = end_date.astimezone(vietnam_tz)
            
            print(f"   End Date: {end_date_vietnam.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # Calculate remaining time
            if now_vietnam < end_date_vietnam:
                remaining = end_date_vietnam - now_vietnam
                days = remaining.days
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                print(f"   ✅ Status: ACTIVE")
                print(f"   ⏳ Remaining: {days}d {hours}h {minutes}m")
            else:
                expired_diff = now_vietnam - end_date_vietnam
                print(f"   ❌ Status: EXPIRED")
                print(f"   ⏳ Expired: {expired_diff.days} days ago")
        except Exception as e:
            print(f"   ⚠️  Error parsing date: {e}")
    
    if "documents_remaining" in data:
        print(f"   📄 Documents Remaining: {data['documents_remaining']}")
    
    if "plan_name" in data:
        print(f"   Plan Name: {data['plan_name']}")
    
    if "price" in data:
        print(f"   Price: Rs.{data['price']}")

print("\n" + "=" * 70)
print("✅ Check complete!")
print("=" * 70)
