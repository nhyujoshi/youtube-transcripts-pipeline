from django.urls import path
from .views import TotalCountsAPIView, KeywordSearchAPIView, CommonWordsAPIView

from . import views

urlpatterns = [
    path('counts/', TotalCountsAPIView.as_view(), name='total-counts'),
    path('search/', KeywordSearchAPIView.as_view(), name='keyword-search'),
    path('common_words/', CommonWordsAPIView.as_view(), name='common-words'),
]