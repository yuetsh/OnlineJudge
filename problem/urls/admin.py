from django.urls import path

from ..views.admin import (ContestProblemAPI, ProblemAPI, TestCaseAPI, MakeContestProblemPublicAPIView,
                           CompileSPJAPI, AddContestProblemAPI, ExportProblemAPI, ImportProblemAPI,
                           FPSProblemImport)

urlpatterns = [
    path("test_case", TestCaseAPI.as_view()),
    path("compile_spj", CompileSPJAPI.as_view()),
    path("problem", ProblemAPI.as_view()),
    path("contest/problem", ContestProblemAPI.as_view()),
    path("contest_problem/make_public", MakeContestProblemPublicAPIView.as_view()),
    path("contest/add_problem_from_public", AddContestProblemAPI.as_view()),
    path("export_problem", ExportProblemAPI.as_view()),
    path("import_problem", ImportProblemAPI.as_view()),
    path("import_fps", FPSProblemImport.as_view()),
]
