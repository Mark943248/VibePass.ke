# VibePass Multi-Ticket Types - Quick Reference

## 🚀 Installation

```bash
# 1. Apply migrations
python manage.py migrate

# 2. No additional packages needed - uses existing Django/Cloudinary
```

## 📋 Create Ticket Types (Admin)

1. Go to: `/admin/events/event/`
2. Click on event name
3. Scroll to "Ticket types" section
4. Click "Add Another Ticket Type"
5. Fill fields:
   - **name**: "Early Bird", "VIP", "Regular", etc.
   - **price**: 500, 1500, 1000, etc.
   - **capacity**: 100, 50, 500, etc.
   - **description**: (optional) "Get 20% off", "Premium access", etc.
   - **is_active**: ✓ Check this
6. Save

## 💻 Django Shell Commands

```python
# Create ticket type
from Events.models import Event, TicketType

event = Event.objects.get(slug='my-event')
TicketType.objects.create(
    event=event,
    name="VIP",
    price=1500,
    capacity=50,
    is_active=True
)

# Check availability
tt = TicketType.objects.get(id=1)
print(f"Available: {tt.get_available_count()}/{tt.capacity}")

# Get all types for event
types = event.ticket_types.filter(is_active=True)
for t in types:
    print(f"{t.name}: {t.sold_count}/{t.capacity} sold")

# Bulk migrate events
for event in Event.objects.all():
    if not event.ticket_types.exists():
        TicketType.objects.create(
            event=event,
            name="General",
            price=event.Event_ticket_price,
            capacity=event.Event_total_tickets,
            is_active=True
        )
```

## 🎨 Frontend Implementation

### Template Display
```html
{% for ticket_type in ticket_types %}
  <div class="ticket-option">
    <h3>{{ ticket_type.name }}</h3>
    <p>{{ ticket_type.description }}</p>
    <span>{{ ticket_type.price }} KES</span>
    <span>{{ ticket_type.get_available_count }}/{{ ticket_type.capacity }}</span>
  </div>
{% endfor %}
```

### JavaScript Cart
```javascript
// Add to quantity
ticketCart[ticket_type_id] = currentQty + 1;

// Calculate total
let total = 0;
for (let typeId in ticketCart) {
  total += ticketTypes[typeId].price * ticketCart[typeId];
}

// Pass to checkout
sessionStorage.setItem('ticketCart', JSON.stringify(ticketCart));
```

## 💳 Payment Processing

```python
from Payments.checkout_handler import process_multi_ticket_checkout

# After successful MPESA payment:
cart_data = {
    1: 2,  # 2 tickets of type 1
    3: 1   # 1 ticket of type 3
}

success, msg, ticket_ids = process_multi_ticket_checkout(payment, cart_data)

if success:
    print(f"Created tickets: {ticket_ids}")
    # Send confirmation email, generate QR codes, etc.
```

## 🔍 Common Queries

```python
# All active types for event
event.ticket_types.filter(is_active=True)

# Check if has stock
type.has_available()  # Returns True/False

# Get remaining
type.get_available_count()  # Returns int

# Get tickets of specific type
type.tickets.all()

# Update sold count after purchase
type.sold_count += quantity
type.save()

# Tickets by type for event
from Tickets.models import Ticket
Ticket.objects.filter(event=event, ticket_type=type)

# Revenue by ticket type
from django.db.models import Sum
type.tickets.filter(
    status__in=['active', 'scanned']
).count() * type.price
```

## 🛠️ Admin Customization

```python
# In Events/admin.py

@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'price', 'capacity', 'sold_count')
    search_fields = ('name', 'event__Event_title')
    list_filter = ('is_active', 'event__Event_date')
    readonly_fields = ('sold_count', 'created_at', 'updated_at')
```

## 📊 Reporting Queries

```python
# Sales by ticket type
for tt in event.ticket_types.all():
    revenue = tt.sold_count * tt.price
    print(f"{tt.name}: {tt.sold_count} × {tt.price} = {revenue} KES")

# Total event revenue
total = sum(
    tt.sold_count * tt.price 
    for tt in event.ticket_types.all()
)
print(f"Total: {total} KES")

# Capacity utilization
for tt in event.ticket_types.all():
    util = (tt.sold_count / tt.capacity) * 100
    print(f"{tt.name}: {util:.1f}% full")
```

## ⚠️ Validation

```python
from Payments.checkout_handler import validate_cart, get_checkout_summary

# Validate cart before checkout
is_valid, error = validate_cart(event, cart_data)
if not is_valid:
    print(f"Error: {error}")

# Get summary for display
summary = get_checkout_summary(event, cart_data)
print(f"Total: {summary['total']} {summary['currency']}")
print(f"Items: {summary['total_quantity']}")
for item in summary['items']:
    print(f"  {item['type_name']}: {item['quantity']} × {item['price_per_unit']}")
```

## 🔄 Migration Path

```python
# Option 1: Migrate specific event
from Events.models import Event, TicketType

event = Event.objects.get(id=123)
TicketType.objects.create(
    event=event,
    name="General",
    price=event.Event_ticket_price,
    capacity=event.Event_total_tickets,
    is_active=True
)

# Option 2: Migrate all
for event in Event.objects.filter(ticket_types__isnull=True):
    TicketType.objects.create(
        event=event,
        name="General",
        price=event.Event_ticket_price,
        capacity=event.Event_total_tickets,
        is_active=True
    )
```

## 📱 Mobile Responsiveness

The template includes full responsive design:
- Ticket cards stack on mobile
- Touch-friendly buttons (+/- at least 44px)
- Readable font sizes
- Flexbox layout adapts to screen size

## 🔐 Security Notes

1. **Server-side validation**: Always validate capacity on checkout
2. **Atomic transactions**: Use `transaction.atomic()` for ticket creation
3. **Rate limiting**: Implement on checkout endpoint
4. **Audit trail**: Log all TicketType modifications
5. **Permission checks**: Verify organizer permissions before modifications

## 📞 Troubleshooting

| Problem | Solution |
|---------|----------|
| Ticket types not showing | Check `is_active=True` in admin |
| Cart not persisting | Enable sessionStorage in browser |
| Capacity errors | Verify `sold_count` accuracy |
| Admin inline missing | Run migrations, restart Django |
| Old price still showing | Ensure no fallback, create ticket type |

## 📚 Documentation Files

- **MULTI_TICKET_TYPES_GUIDE.md** - Full documentation
- **CHECKOUT_INTEGRATION.md** - Payment system integration
- **MIGRATION_GUIDE.md** - Migrate existing events
- **IMPLEMENTATION_SUMMARY.md** - Architecture overview

---

**Need help?** Check the main documentation files or Django admin interface.
