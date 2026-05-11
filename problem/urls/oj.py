from django.urls import path

from ..views.oj import (
    ContestProblemAPI,
    PickOneAPI,
    ProblemAPI,
    ProblemAuthorAPI,
    ProblemSolvedPeopleCount,
    ProblemTagAPI,
    ProblemYearlyACRateAPI,
    SimilarProblemAPI,
)

urlpatterns = [
    path("problem/tags", ProblemTagAPI.as_view()),
    path("problem", ProblemAPI.as_view()),
    path("problem/beat_count", ProblemSolvedPeopleCount.as_view()),
    path("problem/similar", SimilarProblemAPI.as_view()),
    path("problem/author", ProblemAuthorAPI.as_view()),
    path("problem/yearly_ac", ProblemYearlyACRateAPI.as_view()),
    path("pickone", PickOneAPI.as_view()),
    path("contest/problem", ContestProblemAPI.as_view()),
]
