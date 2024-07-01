from django.urls import path

from ..views.oj import ProblemTagAPI, ProblemAPI, ContestProblemAPI, PickOneAPI

urlpatterns = [
    path("problem/tags", ProblemTagAPI.as_view()),
    path("problem", ProblemAPI.as_view()),
    path("pickone", PickOneAPI.as_view()),
    path("contest/problem", ContestProblemAPI.as_view()),
]
