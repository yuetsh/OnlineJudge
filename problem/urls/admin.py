from django.urls import path

from ..views.admin import (
    ContestProblemAPI,
    ProblemAPI,
    ProblemFlowchartAIGen,
    TestCaseAPI,
    MakeContestProblemPublicAPIView,
    AddContestProblemAPI,
    ProblemVisibleAPI,
)

urlpatterns = [
    path("test_case", TestCaseAPI.as_view()),
    path("problem", ProblemAPI.as_view()),
    path("problem/visible", ProblemVisibleAPI.as_view()),
    path("problem/flowchart", ProblemFlowchartAIGen.as_view()),
    path("contest/problem", ContestProblemAPI.as_view()),
    path("contest_problem/make_public", MakeContestProblemPublicAPIView.as_view()),
    path("contest/add_problem_from_public", AddContestProblemAPI.as_view()),
]
