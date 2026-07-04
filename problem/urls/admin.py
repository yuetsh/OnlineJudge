from django.urls import path

from ..views.admin import (
    AddContestProblemAPI,
    ContestProblemAPI,
    MakeContestProblemPublicAPIView,
    ProblemAPI,
    ProblemFlowchartAIGen,
    ProblemVisibleAPI,
    SQLTestCaseAIGenAPI,
    SQLTestCasePreviewAPI,
    SQLTestCaseScriptsAPI,
    StuckProblemsAPI,
    TestCaseAPI,
    TopACTrendAPI,
)

urlpatterns = [
    path("test_case", TestCaseAPI.as_view()),
    path("sql_test_case_preview", SQLTestCasePreviewAPI.as_view()),
    path("sql_test_case_scripts", SQLTestCaseScriptsAPI.as_view()),
    path("sql_test_case_ai_gen", SQLTestCaseAIGenAPI.as_view()),
    path("problem", ProblemAPI.as_view()),
    path("problem/visible", ProblemVisibleAPI.as_view()),
    path("problem/stuck", StuckProblemsAPI.as_view()),
    path("problem/top_ac_trend", TopACTrendAPI.as_view()),
    path("problem/flowchart", ProblemFlowchartAIGen.as_view()),
    path("contest/problem", ContestProblemAPI.as_view()),
    path("contest_problem/make_public", MakeContestProblemPublicAPIView.as_view()),
    path("contest/add_problem_from_public", AddContestProblemAPI.as_view()),
]
