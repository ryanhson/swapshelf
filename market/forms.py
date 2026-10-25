from django.contrib.auth.models import User
from django import forms

from market.models import Listing


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = ["title", "description", "price", "category", "seller_note"]


class ProfileForm(forms.ModelForm):
    # Only non-privileged profile fields are editable here. `is_staff` is a
    # Django authorization flag (it gates the department desk and the admin
    # site), so it must never be bound to a self-service form — otherwise any
    # account can grant itself staff. Desk/board membership is assigned by an
    # administrator (createsuperuser or the seed), not chosen on this page.
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
