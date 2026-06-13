# Multi-Ticket Types Implementation Guide

## Overview
This feature allows event organizers to create different ticket types (Early Bird, VIP, Regular, etc.) for each event, each with its own price and capacity. Users can purchase multiple tickets of different types in a single transaction.

## Database Models

### TicketType Model (New)
Located in `Events/models.py`

```python
class TicketType(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_types')
    name = models.CharField(max_length=100)  # e.g., "Early Bird", "VIP", "Regular"
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()  # Max tickets available for this type
    sold_count = models.PositiveIntegerField(default=0)  # Tracks sold tickets
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

**Key Methods:**
- `get_available_count()`: Returns remaining tickets of this type
- `has_available()`: Checks if tickets are available

### Updated Ticket Model
The `Ticket` model in `Tickets/models.py` now includes:
- `ticket_type`: ForeignKey to `TicketType` (allows tracking which type was purchased)

## How to Use

### Step 1: Run Migrations
After deploying this code, run:
```bash
python manage.py migrate
```

### Step 2: Create Ticket Types in Admin
1. Go to Django Admin (`/admin/`)
2. Navigate to Events section
3. Edit an event OR create a new one
4. Scroll to "Ticket types" section
5. Add ticket types with:
   - Name (e.g., "Early Bird", "VIP", "Regular")
   - Description (optional)
   - Price
   - Capacity (max tickets available)
   - Active status

**Example Setup:**
```
Event: "Summer Music Festival"

Ticket Types:
1. Early Bird
   - Price: 500 KES
   - Capacity: 100
   - Description: "Get 20% off by booking early"

2. VIP
   - Price: 1,500 KES
   - Capacity: 50
   - Description: "Premium seating & VIP lounge access"

3. Regular
   - Price: 1,000 KES
   - Capacity: 500
   - Description: "Standard entry ticket"
```

### Step 3: User Experience on Event Details Page

1. **View Available Tickets**: Users see all active ticket types for the event
2. **Adjust Quantities**: Use +/- buttons to select quantity for each ticket type
3. **Real-time Total**: Total cost updates as selections change
4. **Capacity Validation**: Cannot select more than available tickets
5. **Checkout**: Click "Get Tickets" to proceed with all selected items

### Step 4: Process Purchases
During checkout, the system:
1. Reads cart data from `sessionStorage` containing all ticket selections
2. Creates individual `Ticket` records for each purchased ticket
3. Associates each ticket with its specific `TicketType`
4. Updates the `sold_count` on each ticket type

## Frontend Implementation

### JavaScript Cart System
The template includes a dynamic JavaScript cart that:
- Stores quantities for each ticket type in `ticketCart` object
- Calculates totals across multiple ticket types
- Validates against available capacity
- Shows confirmation summary before checkout
- Persists cart data via `sessionStorage` for checkout page

### Example Cart Structure
```javascript
{
  1: 2,    // 2 tickets of type_id 1
  3: 1,    // 1 ticket of type_id 3
  5: 3     // 3 tickets of type_id 5
}
```

## Admin Interface

### Event Admin (Updated)
- Inline editing of ticket types directly when editing an event
- Quick view of ticket type information

### TicketType Admin (New)
- Dedicated management interface for ticket types
- Read-only fields for `sold_count`, `created_at`, `updated_at`
- Organized fieldsets for better UX
- Search and filter capabilities

## Backward Compatibility

If an event has NO ticket types defined, the system falls back to the original single-ticket system using `event.Event_ticket_price`.

## Key Features

✅ **Multiple Ticket Types**: Create unlimited ticket types per event
✅ **Individual Capacity**: Each type has separate inventory
✅ **Bulk Purchases**: Users can buy multiple tickets (for friends, family, etc.)
✅ **Dynamic Pricing**: Different prices for different ticket tiers
✅ **Real-time Availability**: Shows remaining tickets per type
✅ **Admin Management**: Easy-to-use Django admin interface
✅ **Cart Summary**: Clear breakdown before purchase
✅ **Fallback Support**: Works with legacy single-price events

## Database Queries

### Get all ticket types for an event:
```python
event = Event.objects.get(id=1)
active_types = event.ticket_types.filter(is_active=True)
```

### Check availability:
```python
ticket_type = TicketType.objects.get(id=1)
if ticket_type.has_available():
    # Allow purchase
```

### Get sold tickets by type:
```python
ticket_type = TicketType.objects.get(id=1)
sold = ticket_type.tickets.filter(status__in=['active', 'scanned']).count()
```

## Next Steps

1. **Update Checkout View**: Modify the checkout view to read from `sessionStorage` and process multiple ticket types
2. **Update Payments**: Link payment records to multiple ticket instances
3. **Update QR Codes**: Generate individual QR codes for each ticket
4. **Reporting**: Add analytics to track sales by ticket type

## Troubleshooting

**Issue**: Ticket types not showing on event details page
- **Solution**: Ensure ticket types are marked as `is_active=True`
- **Check**: Run `event.ticket_types.all()` in Django shell

**Issue**: Capacity validation not working
- **Solution**: Ensure `get_available_count()` is calculating correctly
- **Check**: Verify `sold_count` is being updated after each purchase

**Issue**: Cart not persisting to checkout
- **Solution**: Check browser's sessionStorage is enabled
- **Debug**: Open browser console and check `sessionStorage.getItem('ticketCart')`

## Files Modified

1. `Events/models.py` - Added TicketType model
2. `Events/admin.py` - Updated admin interface with TicketTypeInline
3. `Events/views.py` - Updated EventDetails view to pass ticket_types
4. `Tickets/models.py` - Added ticket_type ForeignKey to Ticket
5. `Events/templates/events/event_details.html` - Updated UI and JavaScript

## Security Considerations

- Always validate ticket availability on the server-side during checkout
- Verify user permissions before allowing ticket type modifications
- Implement rate limiting on ticket purchase endpoints
- Log all ticket type changes for audit trail
