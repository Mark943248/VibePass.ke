# Migration Guide: Single Ticket to Multi-Ticket System

## Overview
This guide helps you migrate existing events from the single-ticket system to the new multi-ticket type system.

## Automatic Fallback (Recommended for Phase 1)
The system automatically supports existing events without ticket types. When viewing an event details page:
- If NO ticket types exist → Uses old `Event_ticket_price` 
- If ticket types exist → Uses new multi-ticket UI

**No action required** - existing events will continue to work!

## Manual Migration (For Enhanced Event Setup)

### Option 1: Via Django Admin (Easiest)
1. Go to Django Admin: `/admin/events/event/`
2. Click on an event to edit it
3. Scroll to the "Ticket types" inline section
4. Click "Add Another Ticket Type"
5. Fill in:
   - **Name**: e.g., "Standard", "Early Bird", "VIP"
   - **Price**: Same as original `Event_ticket_price` (or different for tiered pricing)
   - **Capacity**: How many of this ticket type
   - **Description**: Optional description
   - **Active**: ✓ Check this box
6. Click "Save"

**Example Migration:**
```
Old System:
- Price: 1000 KES
- Total Tickets: 500

New System (Create 3 Ticket Types):
1. Early Bird - 500 KES - 100 capacity
2. Regular - 1000 KES - 300 capacity  
3. VIP - 2000 KES - 100 capacity
```

### Option 2: Via Django Shell (Bulk Migration)
```bash
python manage.py shell
```

```python
from Events.models import Event, TicketType

# Migrate all events
for event in Event.objects.all():
    # Only create if no ticket types exist
    if not event.ticket_types.exists():
        TicketType.objects.create(
            event=event,
            name="General Admission",
            price=event.Event_ticket_price,
            capacity=event.Event_total_tickets,
            description="Standard entry ticket",
            is_active=True
        )
        print(f"Migrated: {event.Event_title}")

# Or for a specific event:
event = Event.objects.get(slug='summer-music-festival')
TicketType.objects.create(
    event=event,
    name="General Admission",
    price=event.Event_ticket_price,
    capacity=event.Event_total_tickets,
    is_active=True
)
```

### Option 3: Management Command (Batch Processing)
Create `Events/management/commands/migrate_to_multi_tickets.py`:

```python
from django.core.management.base import BaseCommand
from Events.models import Event, TicketType

class Command(BaseCommand):
    help = 'Migrate existing single-ticket events to multi-ticket system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Migrate all events without ticket types'
        )
        parser.add_argument(
            '--event-id',
            type=int,
            help='Migrate specific event by ID'
        )

    def handle(self, *args, **options):
        if options['all']:
            events = Event.objects.filter(ticket_types__isnull=True).distinct()
        elif options['event_id']:
            events = Event.objects.filter(id=options['event_id'])
        else:
            self.stdout.write(self.style.ERROR('Please specify --all or --event-id'))
            return

        count = 0
        for event in events:
            if not event.ticket_types.exists():
                TicketType.objects.create(
                    event=event,
                    name="General Admission",
                    price=event.Event_ticket_price,
                    capacity=event.Event_total_tickets,
                    description="Standard entry ticket",
                    is_active=True
                )
                count += 1
                self.stdout.write(f"✓ {event.Event_title}")

        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully migrated {count} events'))
```

Run with:
```bash
# Migrate all events
python manage.py migrate_to_multi_tickets --all

# Migrate specific event
python manage.py migrate_to_multi_tickets --event-id 5
```

## Verification

### Check if events are migrated:
```python
from Events.models import Event

for event in Event.objects.all():
    types = event.ticket_types.all()
    print(f"{event.Event_title}: {types.count()} ticket types")
    for tt in types:
        print(f"  - {tt.name}: {tt.capacity} @ {tt.price} KES")
```

### Expected Output:
```
Summer Music Festival: 3 ticket types
  - Early Bird: 100 @ 500.00 KES
  - Regular: 300 @ 1000.00 KES
  - VIP: 100 @ 2000.00 KES
```

## Creating Advanced Ticket Types

### Time-Based Pricing (Early Bird)
```python
event = Event.objects.get(slug='music-festival')

TicketType.objects.create(
    event=event,
    name="Early Bird (Limited)",
    price=500,
    capacity=50,
    description="30% off - Available until Dec 31",
    is_active=True
)
```

### VIP with Benefits
```python
TicketType.objects.create(
    event=event,
    name="VIP Experience",
    price=5000,
    capacity=20,
    description="Premium seating, VIP lounge, merchandise",
    is_active=True
)
```

### Student/Group Discount
```python
TicketType.objects.create(
    event=event,
    name="Student Discount",
    price=700,
    capacity=100,
    description="Valid with student ID",
    is_active=True
)
```

## Handling Existing Tickets

### Check existing tickets:
```python
from Tickets.models import Ticket

# Count tickets by event
for event in Event.objects.all():
    total = event.tickets.count()
    sold = event.tickets.filter(status__in=['active', 'scanned']).count()
    print(f"{event.Event_title}: {sold}/{total} tickets sold")
```

### Link existing tickets to ticket type (if needed):
```python
event = Event.objects.get(slug='summer-festival')
general_admission = event.ticket_types.get(name="General Admission")

# Update all tickets without a type
event.tickets.filter(ticket_type__isnull=True).update(
    ticket_type=general_admission
)
```

## Deactivating Ticket Types

To temporarily disable a ticket type without deleting:
```python
ticket_type = TicketType.objects.get(id=1)
ticket_type.is_active = False
ticket_type.save()
```

Users will no longer see inactive ticket types in the UI.

## Archiving Old System

Once fully migrated:
1. Keep `Event.Event_ticket_price` for reference (optional)
2. Optional: Add deprecation comment in code
3. Keep fallback logic for backward compatibility

## Data Backup

Before migrating, backup your database:
```bash
# PostgreSQL
pg_dump database_name > backup.sql

# SQLite
cp db.sqlite3 db.sqlite3.backup

# Or Django fixture
python manage.py dumpdata Events.Event > events_backup.json
```

## Troubleshooting

**Issue**: Events still showing single price in UI
- **Check**: Event has no ticket types created
- **Fix**: Create ticket type via admin or shell

**Issue**: Ticket types appear but cart is empty
- **Check**: Ticket types are marked as `is_active=True`
- **Fix**: Enable in admin interface

**Issue**: Users see old UI
- **Fix**: Clear browser cache (Ctrl+F5 or Cmd+Shift+R)

## Rollback (If Needed)

To revert to old system:
1. Keep migrations (don't reverse)
2. Simply don't create any TicketType records
3. System automatically falls back to Event_ticket_price

No code changes needed!

## Next Steps

1. **Test with pilot event**: Create one event with multiple ticket types
2. **User feedback**: Get organizer feedback on UI/UX
3. **Analytics**: Monitor ticket type sales distribution
4. **Optimization**: Adjust pricing/capacity based on demand
