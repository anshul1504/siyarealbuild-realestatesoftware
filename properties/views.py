from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import redirect, render

from .forms import PropertyForm
from .models import Property


@login_required
def dashboard(request):
    properties = Property.objects.filter(owner=request.user)
    stats = properties.aggregate(total_value=Sum("price"), total_properties=Count("id"))
    recent = properties[:5]
    return render(
        request,
        "properties/dashboard.html",
        {
            "properties": recent,
            "stats": stats,
            "active_count": properties.exclude(status__in=["sold", "rented"]).count(),
            "lead_total": sum(p.lead_count for p in properties),
        },
    )


@login_required
def property_list(request):
    properties = Property.objects.filter(owner=request.user)
    return render(request, "properties/list.html", {"properties": properties})


@login_required
def property_create(request):
    form = PropertyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        prop = form.save(commit=False)
        prop.owner = request.user
        prop.save()
        messages.success(request, "Property added successfully.")
        return redirect("properties:list")
    return render(request, "properties/form.html", {"form": form})

# Create your views here.
