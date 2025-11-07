import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .forms import GlidepathRuleUploadForm, APISettingsForm
from .models import GlidepathRule, RuleSet, APISettings
from .services import export_glidepath_rules, import_glidepath_rules
from .ticker_service import query_ticker as query_ticker_service

DEFAULT_COLORS = [
    "#4dc9f6",
    "#f67019",
    "#f53794",
    "#537bc4",
    "#acc236",
    "#166a8f",
    "#00a950",
    "#58595b",
    "#8549ba",
    "#e5ae38",
]


def _base_color(idx: int) -> str:
    """Return a base color, cycling through defaults and generating new ones."""
    if idx < len(DEFAULT_COLORS):
        return DEFAULT_COLORS[idx]
    hue = (idx * 47) % 360
    return f"hsl({hue}, 65%, 55%)"


def _lighten(color: str, factor: float) -> str:
    """Lighten a hex color by the given factor (0-1)."""
    color = color.lstrip("#")
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _build_chart_data(rules):
    rules_sorted = sorted(rules, key=lambda r: r.gt_retire_age)
    if not rules_sorted:
        return {"labels": [], "datasets": []}, {"labels": [], "datasets": []}, {"labels": [], "datasets": [{"data": [], "backgroundColor": []}]}

    # Build a mapping of age -> rule for all ages from -100 to 100
    # Each rule covers [gt_retire_age, lt_retire_age)
    age_to_rule = {}
    for rule in rules_sorted:
        for age in range(rule.gt_retire_age, rule.lt_retire_age):
            age_to_rule[age] = rule

    # Build chart_rules with labels for every age
    chart_rules: list[tuple[str, GlidepathRule]] = []

    # Add "earlier" for age -100
    if -100 in age_to_rule:
        chart_rules.append(("earlier", age_to_rule[-100]))

    # Determine the range of individual ages to show
    # Start from: lt_retire_age of the rule with gt=-100, OR the first gt value
    # End at: gt_retire_age of the rule with lt=100, OR the last lt value
    first_rule = rules_sorted[0]
    last_rule = rules_sorted[-1]

    if first_rule.gt_retire_age == -100:
        start_age = first_rule.lt_retire_age
    else:
        start_age = first_rule.gt_retire_age

    # End age depends on whether the last rule ends at 100
    if last_rule.lt_retire_age == 100:
        end_age = last_rule.gt_retire_age + 1  # +1 because range() is exclusive
    else:
        end_age = last_rule.lt_retire_age

    # Add individual age labels from start_age to end_age-1
    for age in range(start_age, end_age):
        if age in age_to_rule:
            chart_rules.append((str(age), age_to_rule[age]))

    # Add "later" for age 100 (uses the last rule's allocations)
    if last_rule.lt_retire_age == 100:
        chart_rules.append(("later", last_rule))

    labels = [lbl for lbl, _ in chart_rules]

    class_names: list[str] = []
    for r in rules:
        for ca in r.class_allocations.all():
            name = ca.asset_class.name
            if name not in class_names:
                class_names.append(name)

    class_datasets = []
    for idx, name in enumerate(class_names):
        color = _base_color(idx)
        data = []
        for _, rule in chart_rules:
            perc = 0.0
            for ca in rule.class_allocations.all():
                if ca.asset_class.name == name:
                    perc = float(ca.percentage)
                    break
            data.append(perc)
        class_datasets.append(
            {
                "label": name,
                "data": data,
                "backgroundColor": color,
                "borderColor": color,
                "fill": True,
                "stack": "class",
                "tension": 0.4,
                "pointRadius": 0,
                "pointHoverRadius": 0,
            }
        )

    category_datasets = []
    for class_idx, class_name in enumerate(class_names):
        cat_names: list[str] = []
        for r in rules:
            for ca in r.category_allocations.all():
                if ca.asset_category.asset_class.name == class_name:
                    cname = ca.asset_category.name
                    if cname not in cat_names:
                        cat_names.append(cname)
        base_color = _base_color(class_idx)
        count = len(cat_names)
        for j, cname in enumerate(cat_names):
            color = _lighten(base_color, 0.2 + 0.6 * j / max(1, count))
            data = []
            for _, rule in chart_rules:
                perc = 0.0
                for ca in rule.category_allocations.all():
                    if (
                        ca.asset_category.name == cname
                        and ca.asset_category.asset_class.name == class_name
                    ):
                        perc = float(ca.percentage)
                        break
                data.append(perc)
            category_datasets.append(
                {
                    "label": cname,
                    "data": data,
                    "backgroundColor": color,
                    "borderColor": color,
                    "fill": True,
                    "stack": "category",
                    "tension": 0.4,
                    "pointRadius": 0,
                    "pointHoverRadius": 0,
                }
            )

    pie_data = {"labels": [], "datasets": [{"data": [], "backgroundColor": []}]}
    if "-7" in labels:
        idx = labels.index("-7")
        pie_data["labels"] = [ds["label"] for ds in class_datasets]
        pie_data["datasets"][0]["data"] = [ds["data"][idx] for ds in class_datasets]
        pie_data["datasets"][0]["backgroundColor"] = [ds["backgroundColor"] for ds in class_datasets]

    class_chart = {"labels": labels, "datasets": class_datasets}
    category_chart = {"labels": labels, "datasets": category_datasets}
    return class_chart, category_chart, pie_data


def home(request):
    """Home page view - provides overview and navigation."""
    return render(request, "glidepath_app/home.html")


def settings_view(request):
    """Settings page view - manage API keys and configuration."""
    settings = APISettings.get_settings()
    success_message = None

    if request.method == "POST":
        form = APISettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            success_message = "Settings saved successfully!"
    else:
        form = APISettingsForm(instance=settings)

    context = {
        "form": form,
        "success_message": success_message,
    }

    return render(request, "glidepath_app/settings.html", context)


def rules_view(request):
    """Rules management view - upload, manage, and visualize glidepath rules."""
    error = None
    new_set = None
    if request.method == "POST":
        if "delete" in request.POST:
            RuleSet.objects.filter(id=request.POST["delete"]).delete()
            form = GlidepathRuleUploadForm()
        elif "rename" in request.POST:
            ruleset_id = request.POST["rename"]
            new_name = request.POST.get("new_name", "").strip()
            if new_name:
                try:
                    ruleset = RuleSet.objects.get(id=ruleset_id)
                    ruleset.name = new_name
                    ruleset.save()
                except RuleSet.DoesNotExist:
                    error = "Ruleset not found"
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

    rules = []
    class_chart = {"labels": [], "datasets": []}
    category_chart = {"labels": [], "datasets": []}
    pie_chart = {"labels": [], "datasets": [{"data": [], "backgroundColor": []}]}

    if selected_set:
        rules = GlidepathRule.objects.filter(ruleset=selected_set).prefetch_related(
            "class_allocations__asset_class",
            "category_allocations__asset_category__asset_class",
        )
        class_chart, category_chart, pie_chart = _build_chart_data(list(rules))

    # Generate year and retirement age options
    years_born = list(range(1940, 2021))
    retirement_ages = list(range(40, 81))

    context = {
        "form": form,
        "error": error,
        "rules": rules,
        "rule_sets": rule_sets,
        "selected_set": selected_set,
        "class_chart": json.dumps(class_chart),
        "category_chart": json.dumps(category_chart),
        "class_pie_chart": json.dumps(pie_chart),
        "years_born": years_born,
        "retirement_ages": retirement_ages,
    }

    template = "glidepath_app/upload.html"
    if request.headers.get("HX-Request"):
        template = "glidepath_app/rules.html"
    return render(request, template, context)


def funds_view(request):
    """Funds management view - manage investment funds."""
    return render(request, "glidepath_app/funds.html")


def accounts_view(request):
    """Accounts management view - manage investment accounts."""
    return render(request, "glidepath_app/accounts.html")


def portfolios_view(request):
    """Portfolios management view - manage investment portfolios."""
    return render(request, "glidepath_app/portfolios.html")


def modeling_view(request):
    """Modeling view - run investment simulations and modeling."""
    return render(request, "glidepath_app/modeling.html")


def logout_view(request):
    """Logout view - handle user logout."""
    # Placeholder for logout functionality
    return render(request, "glidepath_app/logout.html")


# Keep backward compatibility alias
upload_rules = rules_view


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


@require_POST
def query_ticker(request):
    """Handle AJAX requests to query ticker information."""
    ticker = request.POST.get('ticker', '').strip()
    source = request.POST.get('source', '').strip()

    if not ticker:
        return JsonResponse({'error': 'Ticker symbol is required'}, status=400)

    if not source:
        return JsonResponse({'error': 'Data source is required'}, status=400)

    # Get API settings
    api_settings = APISettings.get_settings()

    # Query the ticker
    result = query_ticker_service(ticker, source, api_settings)

    return JsonResponse(result)
