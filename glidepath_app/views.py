from django.http import HttpResponse
from django.shortcuts import render

from .forms import GlidepathRuleUploadForm
from .models import GlidepathRule
from .services import export_glidepath_rules, import_glidepath_rules


def upload_rules(request):
    error = None
    if request.method == "POST":
        form = GlidepathRuleUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                import_glidepath_rules(form.cleaned_data["file"])
            except ValueError as exc:  # pragma: no cover - defensive
                error = str(exc)
        else:  # pragma: no cover - defensive
            error = "Invalid upload"
    else:
        form = GlidepathRuleUploadForm()

    rules = GlidepathRule.objects.prefetch_related(
        "class_allocations__asset_class",
        "category_allocations__asset_category__asset_class",
    )

    return render(
        request,
        "glidepath_app/upload.html",
        {"form": form, "error": error, "rules": rules},
    )


def export_rules(request):
    data = export_glidepath_rules()
    response = HttpResponse(data, content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=glidepath-rules.csv"
    return response
