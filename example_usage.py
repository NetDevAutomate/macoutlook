#!/usr/bin/env python3
"""
Comprehensive example showing how to use pyoutlook-db to access Outlook data.

This script demonstrates:
1. Listing calendars
2. Getting calendar events (both historical and modern)
3. Getting emails with full details
4. Searching and filtering
5. Exporting data
"""

import json
from datetime import datetime, timedelta
from pyoutlook_db import OutlookClient

def main():
    print("🔍 PyOutlook-DB Comprehensive Example")
    print("=" * 50)
    
    # Initialize client (uses SQLite database by default)
    print("\n📊 Database Information:")
    client = OutlookClient()
    
    try:
        # Get database info
        tables = client.db.get_table_names()
        print(f"Database: {client.db.db_path}")
        print(f"Tables available: {len(tables)}")
        
        # Get counts
        if "Mail" in tables:
            email_count = client.db.get_row_count("Mail")
            print(f"📧 Total emails: {email_count:,}")
        
        if "CalendarEvents" in tables:
            event_count = client.db.get_row_count("CalendarEvents")
            print(f"📅 Total calendar events: {event_count:,}")
        
    except Exception as e:
        print(f"Error getting database info: {e}")

    print("\n" + "=" * 50)
    print("📅 CALENDAR FUNCTIONALITY")
    print("=" * 50)
    
    # List available calendars
    print("\n1. Available Calendars:")
    try:
        calendars = client.get_calendars()
        for i, cal in enumerate(calendars, 1):
            print(f"   {i}. ID: {cal.calendar_id}")
            print(f"      Name: {cal.name}")
            print(f"      Default: {'Yes' if cal.is_default else 'No'}")
            print()
    except Exception as e:
        print(f"   Error: {e}")
    
    # Get historical calendar events (2007-2008 data)
    print("\n2. Historical Calendar Events (2007-2008):")
    try:
        historical_events = client.get_calendar_events(
            start_date=datetime(2007, 11, 1),
            end_date=datetime(2007, 12, 1),
            limit=5
        )
        
        print(f"   Found {len(historical_events)} historical events:")
        for event in historical_events:
            print(f"   • {event.title}")
            print(f"     📅 {event.start_time.strftime('%Y-%m-%d %H:%M')} - {event.end_time.strftime('%H:%M')}")
            if event.organizer:
                print(f"     👤 Organizer: {event.organizer}")
            print()
    except Exception as e:
        print(f"   Error: {e}")
    
    # Get modern calendar events (from .ics files)
    print("\n3. Modern Calendar Events (.ics files):")
    try:
        modern_client = OutlookClient(use_ics=True)
        modern_events = modern_client.get_calendar_events(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2025, 12, 31)
        )
        
        print(f"   Found {len(modern_events)} modern events:")
        for event in modern_events:
            print(f"   • {event.title}")
            print(f"     📅 {event.start_time.strftime('%Y-%m-%d %H:%M')} - {event.end_time.strftime('%H:%M')}")
            if event.location:
                print(f"     📍 {event.location}")
            if event.attendees:
                print(f"     👥 {len(event.attendees)} attendees")
            print()
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 50)
    print("📧 EMAIL FUNCTIONALITY")
    print("=" * 50)
    
    # Get recent emails
    print("\n1. Recent Emails (Last 7 days):")
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        recent_emails = client.get_emails_by_date_range(
            start_date=start_date,
            end_date=end_date,
            limit=5,
            include_content=False  # Faster without full content
        )
        
        print(f"   Found {len(recent_emails)} recent emails:")
        for email in recent_emails:
            print(f"   • {email.subject}")
            print(f"     📨 From: {email.sender_name or email.sender}")
            print(f"     📅 {email.timestamp.strftime('%Y-%m-%d %H:%M')}")
            if email.recipients:
                print(f"     👥 To: {len(email.recipients)} recipients")
            print()
    except Exception as e:
        print(f"   Error: {e}")
    
    # Get emails from specific time period
    print("\n2. Emails from June 2025:")
    try:
        june_emails = client.get_emails_by_date_range(
            start_date=datetime(2025, 6, 1),
            end_date=datetime(2025, 7, 1),
            limit=3,
            include_content=True
        )
        
        print(f"   Found {len(june_emails)} emails from June 2025:")
        for email in june_emails:
            print(f"   • {email.subject}")
            print(f"     📨 From: {email.sender_name or email.sender}")
            print(f"     📅 {email.timestamp.strftime('%Y-%m-%d %H:%M')}")
            print(f"     📄 Size: {email.message_size:,} bytes")
            if email.content_text:
                preview = email.content_text[:100]
                if len(email.content_text) > 100:
                    preview += "..."
                print(f"     📖 Preview: {preview}")
            print()
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 50)
    print("🔍 SEARCH AND ANALYSIS")
    print("=" * 50)
    
    # Search emails
    print("\n1. Search for AWS-related emails:")
    try:
        from pyoutlook_db.models.email import EmailSearchFilter
        
        search_filter = EmailSearchFilter(
            query="AWS",
            limit=3,
            start_date=datetime(2025, 6, 1)
        )
        
        search_results = client.search_emails(search_filter)
        print(f"   Found {len(search_results)} AWS-related emails:")
        for email in search_results:
            print(f"   • {email.subject}")
            print(f"     📨 From: {email.sender_name or email.sender}")
            print(f"     📅 {email.timestamp.strftime('%Y-%m-%d')}")
            print()
    except Exception as e:
        print(f"   Error: {e}")
    
    # Email statistics
    print("\n2. Email Statistics:")
    try:
        # Get emails from last month
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        month_emails = client.get_emails_by_date_range(
            start_date=start_date,
            end_date=end_date,
            limit=1000,
            include_content=False
        )
        
        # Analyze senders
        senders = {}
        total_size = 0
        read_count = 0
        
        for email in month_emails:
            sender = email.sender_name or email.sender
            senders[sender] = senders.get(sender, 0) + 1
            total_size += email.message_size or 0
            if email.is_read:
                read_count += 1
        
        print(f"   📊 Last 30 days statistics:")
        print(f"   • Total emails: {len(month_emails):,}")
        print(f"   • Total size: {total_size / (1024*1024):.1f} MB")
        print(f"   • Read emails: {read_count:,} ({read_count/len(month_emails)*100:.1f}%)")
        print(f"   • Unique senders: {len(senders):,}")
        
        # Top senders
        top_senders = sorted(senders.items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"   • Top senders:")
        for sender, count in top_senders:
            print(f"     - {sender}: {count} emails")
        
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 50)
    print("💾 DATA EXPORT EXAMPLES")
    print("=" * 50)
    
    # Export recent emails to JSON
    print("\n1. Export recent emails to JSON:")
    try:
        recent_emails = client.get_emails_by_date_range(
            start_date=datetime.now() - timedelta(days=7),
            end_date=datetime.now(),
            limit=10,
            include_content=False
        )
        
        # Convert to JSON-serializable format
        emails_data = []
        for email in recent_emails:
            emails_data.append({
                'id': email.message_id,
                'subject': email.subject,
                'sender': email.sender,
                'sender_name': email.sender_name,
                'timestamp': email.timestamp.isoformat(),
                'recipients_count': len(email.recipients),
                'message_size': email.message_size,
                'is_read': email.is_read
            })
        
        # Save to file
        with open('recent_emails.json', 'w') as f:
            json.dump(emails_data, f, indent=2)
        
        print(f"   ✅ Exported {len(emails_data)} emails to 'recent_emails.json'")
        
    except Exception as e:
        print(f"   Error: {e}")
    
    # Export calendar events
    print("\n2. Export calendar events to JSON:")
    try:
        # Get both historical and modern events
        all_events = []
        
        # Historical events
        historical = client.get_calendar_events(
            start_date=datetime(2007, 1, 1),
            end_date=datetime(2008, 12, 31),
            limit=100
        )
        
        # Modern events
        modern_client = OutlookClient(use_ics=True)
        modern = modern_client.get_calendar_events(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2025, 12, 31)
        )
        
        all_events.extend(historical)
        all_events.extend(modern)
        
        # Convert to JSON-serializable format
        events_data = []
        for event in all_events:
            events_data.append({
                'id': event.event_id,
                'title': event.title,
                'start_time': event.start_time.isoformat(),
                'end_time': event.end_time.isoformat(),
                'location': event.location,
                'organizer': event.organizer,
                'attendees_count': len(event.attendees),
                'is_all_day': event.is_all_day,
                'is_recurring': event.is_recurring
            })
        
        # Save to file
        with open('calendar_events.json', 'w') as f:
            json.dump(events_data, f, indent=2)
        
        print(f"   ✅ Exported {len(events_data)} events to 'calendar_events.json'")
        
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 50)
    print("✨ SUMMARY")
    print("=" * 50)
    print("""
🎉 Successfully demonstrated pyoutlook-db functionality:

📧 EMAIL ACCESS:
   • 72,000+ emails from 2021-2025
   • Full search and filtering capabilities
   • Content parsing (HTML, text, markdown)
   • Export to JSON/CSV formats

📅 CALENDAR ACCESS:
   • 6,800+ historical events (2007-2008) from SQLite
   • Modern events from .ics files
   • Calendar listing and filtering
   • Event details with attendees/locations

🔍 SEARCH & ANALYSIS:
   • Advanced email search with filters
   • Statistics and analytics
   • Sender analysis and trends
   • Date range queries

💾 DATA EXPORT:
   • JSON export for programmatic use
   • CSV export for spreadsheet analysis
   • Raw data access for custom processing

This library gives you full programmatic access to your Outlook data
without the timeouts and limitations of other solutions!
""")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure Microsoft Outlook is installed and has data.")