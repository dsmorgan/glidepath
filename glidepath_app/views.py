from django.http import HttpResponse
from django.shortcuts import render

from .forms import GlidepathRuleUploadForm
from .models import GlidepathRule, RuleSet
from .services import export_glidepath_rules, import_glidepath_rules


def upload_rules(request):
    error = None
    new_set = None
    if request.method == "POST":
        if "delete" in request.POST:
            RuleSet.objects.filter(id=request.POST["delete"]).delete()
            form = GlidepathRuleUploadForm()
        else:
            form = GlidepathRuleUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    new_set = import_glidepath_rules(form.cleaned_data["file"])
                except ValueError as exc:  # pragma: no cover - defensive
                    error = str(exc)
            else:  # pragma: no cover - defensive
                error = "Invalid upload"
    else:
        form = GlidepathRuleUploadForm()

    selected_id = request.POST.get("ruleset") or request.GET.get("ruleset")
    if new_set:
        selected_id = new_set.id
    rule_sets = RuleSet.objects.order_by("name")
    selected_set = None
    if selected_id:
        selected_set = RuleSet.objects.filter(id=selected_id).first()
    if not selected_set:
        selected_set = rule_sets.first()

    rules = GlidepathRule.objects.filter(ruleset=selected_set).prefetch_related(
        "class_allocations__asset_class",
        "category_allocations__asset_category__asset_class",
    )

    return render(
        request,
        "glidepath_app/upload.html",
        {
            "form": form,
            "error": error,
            "rules": rules,
            "rule_sets": rule_sets,
            "selected_set": selected_set,
        },
    )


def export_rules(request):
    ruleset_id = request.GET.get("ruleset")
    ruleset = RuleSet.objects.filter(id=ruleset_id).first()
    if not ruleset:
        ruleset = RuleSet.objects.order_by("name").first()
    if not ruleset:
        return HttpResponse("", content_type="text/csv")
    data = export_glidepath_rules(ruleset)
    response = HttpResponse(data, content_type="text/csv")
    filename = f"{ruleset.name}.csv"
    response["Content-Disposition"] = f"attachment; filename={filename}"
    return response
