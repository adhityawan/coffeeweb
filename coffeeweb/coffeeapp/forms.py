from django import forms

class OptimizeForm(forms.Form):
    STRENGTH_CHOICES = [
        ("strong", "Strong"),
        ("medium", "Medium"),
        ("light", "Light"),
    ]

    density = forms.IntegerField(
        min_value=350,
        max_value=450,
        label="Density (350–450)",
        widget=forms.NumberInput(attrs={
            "class": "input",
            "placeholder": "Enter coffee density value..."
        })
    )

    target_strength = forms.ChoiceField(
        choices=STRENGTH_CHOICES,
        label="Strength Profile",
        widget=forms.Select(attrs={"class": "select"})
    )
