# coffeeapp/urls.py
# coffeeapp/urls.py
from django.urls import path

from . import views
urlpatterns = [
     path('', views.optimize_view, name='optimize'),
]

