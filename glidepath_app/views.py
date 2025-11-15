import json
import csv
import io

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .forms import GlidepathRuleUploadForm, APISettingsForm, FundForm, UserForm, IdentityProviderForm, AccountUploadForm, PortfolioForm, AssumptionUploadForm
from .models import GlidepathRule, RuleSet, APISettings, Fund, AssetCategory, User, IdentityProvider, AccountUpload, AccountPosition, Portfolio, PortfolioItem, AssumptionUpload, AssumptionData
from .services import export_glidepath_rules, import_glidepath_rules, import_blackrock_assumptions
from .ticker_service import query_ticker as query_ticker_service
from .account_services import import_fidelity_csv, import_etrade_csv, get_portfolio_analysis, calculate_rebalance_recommendations

DEFAULT_COLORS = [
    "#FF6384",
    "#36A2EB",
    "#FFCE56",
    "#4BC0C0",
    "#9966FF",
    "#FF9F40",
    "#C9CBCF",
    "#85C1E2",
    "#F8B195",
    "#C7B3A3",
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
    """Settings page view - manage API keys, users, and identity providers."""
    settings = APISettings.get_settings()
    success_message = None

    if request.method == "POST":
        form = APISettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            success_message = "Settings saved successfully!"
    else:
        form = APISettingsForm(instance=settings)

    # Get all users and identity providers
    users = User.objects.all().order_by('username')
    identity_providers = IdentityProvider.objects.all().order_by('name')

    # Get session messages for funds upload
    funds_upload_success = request.session.pop('funds_upload_success', None)
    funds_upload_error = request.session.pop('funds_upload_error', None)

    context = {
        "form": form,
        "success_message": success_message,
        "users": users,
        "identity_providers": identity_providers,
        "funds_upload_success": funds_upload_success,
        "funds_upload_error": funds_upload_error,
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
    # Get sorting parameters
    sort_by = request.GET.get('sort', 'ticker')
    order = request.GET.get('order', 'asc')

    # Map sort parameters to model fields
    sort_fields = {
        'ticker': 'ticker',
        'name': 'name',
        'category': 'category__name',
        'preference': 'preference',
    }

    # Get the sort field, default to ticker if invalid
    sort_field = sort_fields.get(sort_by, 'ticker')

    # Apply ordering (prefix with - for descending)
    if order == 'desc':
        sort_field = f'-{sort_field}'

    # Get all funds with sorting
    funds_list = Fund.objects.select_related('category', 'category__asset_class').order_by(sort_field)

    # Get per-page parameter (default 10, options 10 or 100)
    per_page_str = request.GET.get('per_page', '10')
    try:
        per_page = int(per_page_str)
        if per_page not in [10, 100]:
            per_page = 10
    except ValueError:
        per_page = 10

    # Pagination
    paginator = Paginator(funds_list, per_page)
    page = request.GET.get('page', 1)

    try:
        funds = paginator.page(page)
    except PageNotAnInteger:
        funds = paginator.page(1)
    except EmptyPage:
        funds = paginator.page(paginator.num_pages)

    context = {
        'funds': funds,
        'sort_by': sort_by,
        'order': order,
        'per_page': per_page,
    }

    return render(request, "glidepath_app/funds.html", context)


def accounts_view(request):
    """Accounts management view - manage investment accounts."""
    error = None
    success = None

    # Determine which user's data to show
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            # Fall back to first user if selected user doesn't exist
            current_user = User.objects.first()
    else:
        # Default to first user
        current_user = User.objects.first()

    if request.method == "POST":
        form = AccountUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                upload_type = form.cleaned_data['upload_type']
                file_obj = form.cleaned_data['file']
                filename = file_obj.name

                # Import based on type
                if upload_type == 'fidelity':
                    upload = import_fidelity_csv(file_obj, current_user, filename)
                    success = f"Successfully uploaded {upload.entry_count} positions from {filename}"
                elif upload_type == 'etrade':
                    upload = import_etrade_csv(file_obj, current_user, filename)
                    success = f"Successfully uploaded {upload.entry_count} positions from {filename}"
                else:
                    error = f"Unsupported upload type: {upload_type}"

            except ValueError as exc:
                error = str(exc)
            except Exception as exc:
                error = f"Error uploading file: {str(exc)}"
    else:
        form = AccountUploadForm()

    # Get all uploads for the current user
    if current_user:
        uploads = AccountUpload.objects.filter(user=current_user).order_by('-upload_datetime')
    else:
        uploads = AccountUpload.objects.none()

    context = {
        'form': form,
        'error': error,
        'success': success,
        'uploads': uploads,
        'current_user': current_user,
    }

    return render(request, "glidepath_app/accounts.html", context)


def view_account_upload(request, upload_id):
    """View details of a specific account upload."""
    try:
        upload = AccountUpload.objects.get(id=upload_id)
        positions = AccountPosition.objects.filter(upload=upload).order_by('account_number', 'symbol')

        context = {
            'upload': upload,
            'positions': positions,
        }
        return render(request, "glidepath_app/account_upload_detail.html", context)
    except AccountUpload.DoesNotExist:
        return redirect('accounts')


@require_POST
def delete_account_upload(request, upload_id):
    """Delete an account upload and all its positions."""
    try:
        upload = AccountUpload.objects.get(id=upload_id)
        upload.delete()
    except AccountUpload.DoesNotExist:
        pass
    return redirect('accounts')


def assumptions_view(request):
    """Assumptions management view - manage market assumptions (global, admin-only upload/delete)."""
    error = None
    success = None

    # Determine current user
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            # Fall back to first user if selected user doesn't exist
            current_user = User.objects.first()
    else:
        # Default to first user
        current_user = User.objects.first()

    # Check if user is admin
    is_admin = current_user and current_user.is_admin()

    if request.method == "POST":
        # Only admins can upload
        if not is_admin:
            error = "Only administrators can upload assumptions."
        else:
            form = AssumptionUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    upload_type = form.cleaned_data['upload_type']
                    file_obj = form.cleaned_data['file']
                    filename = file_obj.name

                    # Import based on type
                    if upload_type == 'blackrock':
                        upload = import_blackrock_assumptions(file_obj, current_user)
                        success = f"Successfully uploaded {upload.entry_count} entries from {filename}"
                    else:
                        error = f"Unsupported upload type: {upload_type}"

                except ValueError as exc:
                    error = str(exc)
                except Exception as exc:
                    error = f"Error uploading file: {str(exc)}"
    else:
        form = AssumptionUploadForm()

    # Get all uploads (global - not filtered by user)
    uploads = AssumptionUpload.objects.all().order_by('-upload_datetime')

    context = {
        'form': form,
        'error': error,
        'success': success,
        'uploads': uploads,
        'current_user': current_user,
        'is_admin': is_admin,
    }

    return render(request, "glidepath_app/assumptions.html", context)


def view_assumption_upload(request, upload_id):
    """View details of a specific assumption upload."""
    try:
        upload = AssumptionUpload.objects.get(id=upload_id)
        data_rows = AssumptionData.objects.filter(upload=upload).order_by('asset_class', 'asset')

        context = {
            'upload': upload,
            'data_rows': data_rows,
        }
        return render(request, "glidepath_app/assumption_upload_detail.html", context)
    except AssumptionUpload.DoesNotExist:
        return redirect('assumptions')


@require_POST
def delete_assumption_upload(request, upload_id):
    """Delete an assumption upload and all its data rows (admin only)."""
    # Determine current user
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            current_user = User.objects.first()
    else:
        current_user = User.objects.first()

    # Check if user is admin
    if current_user and current_user.is_admin():
        try:
            upload = AssumptionUpload.objects.get(id=upload_id)
            upload.delete()
        except AssumptionUpload.DoesNotExist:
            pass

    return redirect('assumptions')


def portfolios_view(request):
    """Portfolios management view - manage investment portfolios."""
    # Determine which user's data to show
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            current_user = User.objects.first()
    else:
        current_user = User.objects.first()

    # Get tolerance parameter (default to 2.0%)
    tolerance_str = request.GET.get('tolerance', '2.0')
    try:
        tolerance = float(tolerance_str)
    except ValueError:
        tolerance = 2.0

    # Get all portfolios for the current user
    analysis_data = None
    rebalance_data = None
    if current_user:
        portfolios = Portfolio.objects.filter(user=current_user)
        selected_portfolio_id = request.GET.get('portfolio') or request.POST.get('selected_portfolio')
        selected_portfolio = None

        if selected_portfolio_id:
            try:
                selected_portfolio = portfolios.get(id=selected_portfolio_id)
            except Portfolio.DoesNotExist:
                pass

        # Default to first portfolio if none selected
        if not selected_portfolio and portfolios.exists():
            selected_portfolio = portfolios.first()

        # Get portfolio analysis if a portfolio is selected
        if selected_portfolio:
            analysis_data = get_portfolio_analysis(selected_portfolio)
            # Serialize category_details to JSON for JavaScript consumption
            if analysis_data and 'category_details' in analysis_data:
                analysis_data['category_details_json'] = json.dumps(analysis_data['category_details'])

            # Calculate rebalance recommendations
            rebalance_data = calculate_rebalance_recommendations(selected_portfolio, tolerance)
    else:
        portfolios = Portfolio.objects.none()
        selected_portfolio = None

    context = {
        'portfolios': portfolios,
        'selected_portfolio': selected_portfolio,
        'current_user': current_user,
        'analysis_data': analysis_data,
        'rebalance_data': rebalance_data,
        'tolerance': tolerance,
    }

    return render(request, "glidepath_app/portfolios.html", context)


def create_portfolio(request):
    """Create a new portfolio."""
    # Determine which user to create the portfolio for
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            current_user = User.objects.first()
    else:
        current_user = User.objects.first()

    if not current_user:
        return redirect('portfolios')

    if request.method == "POST":
        # Handle portfolio configuration (name and ruleset)
        form = PortfolioForm(request.POST, user=current_user)
        if form.is_valid():
            # Create the portfolio with the current user
            portfolio = form.save(commit=False)
            portfolio.user = current_user
            portfolio.save()

            # Get selected items from POST data
            selected_items = request.POST.getlist('selected_items')

            # Create portfolio items
            for item in selected_items:
                # Parse the item format: "account_number|symbol"
                try:
                    account_number, symbol = item.split('|', 1)
                    PortfolioItem.objects.create(
                        portfolio=portfolio,
                        account_number=account_number,
                        symbol=symbol
                    )
                except ValueError:
                    continue

            # Redirect to portfolios page with the new portfolio selected
            return redirect(f'{"/portfolios/"}?portfolio={portfolio.id}')
        else:
            # Form had errors, continue to re-render with errors
            pass

    # Initialize empty form for new portfolio
    form = PortfolioForm(user=current_user)

    # Get all unique account+symbol combinations from the user's account positions
    if current_user:
        positions = AccountPosition.objects.filter(upload__user=current_user).values(
            'account_number', 'account_name', 'symbol', 'description'
        ).distinct().order_by('account_number', 'symbol')

        # Group by account for display
        accounts_data = {}
        for pos in positions:
            acc_num = pos['account_number']
            if acc_num not in accounts_data:
                accounts_data[acc_num] = {
                    'account_number': acc_num,
                    'account_name': pos['account_name'],
                    'symbols': []
                }
            accounts_data[acc_num]['symbols'].append({
                'symbol': pos['symbol'],
                'description': pos['description']
            })
    else:
        accounts_data = {}

    context = {
        'accounts_data': accounts_data,
        'current_user': current_user,
        'form': form,
        'is_create': True,
    }

    return render(request, "glidepath_app/portfolio_create.html", context)


@require_POST
def delete_portfolio(request, portfolio_id):
    """Delete a portfolio and all its items."""
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
        portfolio.delete()
    except Portfolio.DoesNotExist:
        pass
    return redirect('portfolios')


def edit_portfolio(request, portfolio_id):
    """Edit portfolio to select which account+symbol combinations to include and configure ruleset."""
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
    except Portfolio.DoesNotExist:
        return redirect('portfolios')

    # Get the current user
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            current_user = User.objects.first()
    else:
        current_user = User.objects.first()

    if request.method == "POST":
        # Handle portfolio configuration (name and ruleset)
        form = PortfolioForm(request.POST, instance=portfolio, user=current_user)
        if form.is_valid():
            form.save()

            # Clear existing items
            PortfolioItem.objects.filter(portfolio=portfolio).delete()

            # Get selected items from POST data
            selected_items = request.POST.getlist('selected_items')

            # Create new portfolio items
            for item in selected_items:
                # Parse the item format: "account_number|symbol"
                try:
                    account_number, symbol = item.split('|', 1)
                    PortfolioItem.objects.create(
                        portfolio=portfolio,
                        account_number=account_number,
                        symbol=symbol
                    )
                except ValueError:
                    continue

            return redirect('portfolios')
        else:
            # Form had errors, continue to re-render with errors
            pass

    # Initialize form with current portfolio data
    form = PortfolioForm(instance=portfolio, user=current_user)

    # Get all unique account+symbol combinations from the user's account positions
    if current_user:
        positions = AccountPosition.objects.filter(upload__user=current_user).values(
            'account_number', 'account_name', 'symbol', 'description'
        ).distinct().order_by('account_number', 'symbol')

        # Group by account for display
        accounts_data = {}
        for pos in positions:
            acc_num = pos['account_number']
            if acc_num not in accounts_data:
                accounts_data[acc_num] = {
                    'account_number': acc_num,
                    'account_name': pos['account_name'],
                    'symbols': []
                }
            accounts_data[acc_num]['symbols'].append({
                'symbol': pos['symbol'],
                'description': pos['description']
            })

        # Get currently selected items (format as "account_number|symbol" strings)
        selected_items = set(
            f"{item[0]}|{item[1]}" for item in
            PortfolioItem.objects.filter(portfolio=portfolio).values_list(
                'account_number', 'symbol'
            )
        )
    else:
        accounts_data = {}
        selected_items = set()

    context = {
        'portfolio': portfolio,
        'accounts_data': accounts_data,
        'selected_items': selected_items,
        'current_user': current_user,
        'form': form,
    }

    return render(request, "glidepath_app/portfolio_edit.html", context)


def download_portfolio_csv(request, portfolio_id):
    """Download a CSV of portfolio analysis data (category breakdown)."""
    import csv
    from io import StringIO

    try:
        portfolio = Portfolio.objects.get(id=portfolio_id)
    except Portfolio.DoesNotExist:
        return redirect('portfolios')

    # Get portfolio analysis data
    analysis_data = get_portfolio_analysis(portfolio)

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Category', 'Asset Class', 'Current Value', 'Current %', 'Target %', 'Difference'
    ])

    # Write category data
    total_current = 0
    total_target_pct = 0
    total_difference = 0

    for category_item in analysis_data.get('category_details', []):
        writer.writerow([
            category_item.get('category', ''),
            category_item.get('asset_class', ''),
            f"${category_item.get('subtotal', 0):.2f}",
            f"{category_item.get('current_pct', 0):.2f}%",
            f"{category_item.get('target_pct', 0):.2f}%",
            f"${category_item.get('difference', 0):.2f}" if category_item.get('difference', 0) >= 0 else f"-${abs(category_item.get('difference', 0)):.2f}"
        ])
        total_current += category_item.get('subtotal', 0)
        total_target_pct += category_item.get('target_pct', 0)
        total_difference += category_item.get('difference', 0)

    # Write empty row before total
    writer.writerow([])

    # Write total row
    writer.writerow([
        'Total Portfolio',
        '',
        f"${total_current:.2f}",
        '100.00%',
        f"{total_target_pct:.2f}%",
        f"${total_difference:.2f}" if total_difference >= 0 else f"-${abs(total_difference):.2f}"
    ])

    response = HttpResponse(output.getvalue(), content_type='text/csv')
    filename = f"{portfolio.name}_analysis.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


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


def fund_detail(request):
    """Add or edit a fund with ticker, name, and category."""
    # Get ticker and name from query parameters (passed from funds page)
    ticker = request.GET.get('ticker', '').strip().upper()
    name = request.GET.get('name', '').strip()

    # Check if fund already exists
    existing_fund = None
    if ticker:
        existing_fund = Fund.objects.filter(ticker=ticker).first()

    if request.method == 'POST':
        if existing_fund:
            # Update existing fund
            form = FundForm(request.POST, instance=existing_fund)
        else:
            # Create new fund
            form = FundForm(request.POST)

        if form.is_valid():
            try:
                form.save()
                return redirect('funds')
            except Exception as e:
                form.add_error(None, f"Error saving fund: {str(e)}")
    else:
        if existing_fund:
            # Load existing fund for editing
            form = FundForm(instance=existing_fund)
        else:
            # Pre-populate the form with ticker and name from query params
            initial_data = {}
            if ticker:
                initial_data['ticker'] = ticker
            if name:
                initial_data['name'] = name
            form = FundForm(initial=initial_data)

    context = {
        'form': form,
        'is_edit': existing_fund is not None,
        'fund': existing_fund
    }
    return render(request, 'glidepath_app/fund_detail.html', context)


@require_POST
def delete_fund(request, fund_id):
    """Delete a fund from the database."""
    try:
        fund = Fund.objects.get(id=fund_id)
        fund.delete()
        return redirect('funds')
    except Fund.DoesNotExist:
        return redirect('funds')


def user_detail(request, user_id=None):
    """Add or edit a user account."""
    user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return redirect('settings')

    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('settings')
    else:
        form = UserForm(instance=user)

    context = {
        'form': form,
        'is_edit': user is not None,
        'user': user,
    }
    return render(request, 'glidepath_app/user_detail.html', context)


@require_POST
def delete_user(request, user_id):
    """Delete a user account."""
    try:
        user = User.objects.get(id=user_id)
        user.delete()
    except User.DoesNotExist:
        pass
    return redirect('settings')


def identity_provider_detail(request, provider_id=None):
    """Add or edit an identity provider configuration."""
    provider = None
    if provider_id:
        try:
            provider = IdentityProvider.objects.get(id=provider_id)
        except IdentityProvider.DoesNotExist:
            return redirect('settings')

    if request.method == 'POST':
        form = IdentityProviderForm(request.POST, instance=provider)
        if form.is_valid():
            form.save()
            return redirect('settings')
    else:
        form = IdentityProviderForm(instance=provider)

    context = {
        'form': form,
        'is_edit': provider is not None,
        'provider': provider,
    }
    return render(request, 'glidepath_app/identity_provider_detail.html', context)


@require_POST
def delete_identity_provider(request, provider_id):
    """Delete an identity provider configuration."""
    try:
        provider = IdentityProvider.objects.get(id=provider_id)
        provider.delete()
    except IdentityProvider.DoesNotExist:
        pass
    return redirect('settings')


@require_POST
def select_user(request, user_id):
    """Select a user for filtering accounts, portfolios, and models."""
    try:
        user = User.objects.get(id=user_id)
        request.session['selected_user_id'] = str(user.id)
    except User.DoesNotExist:
        pass

    # Get the referer URL or default to home
    referer = request.META.get('HTTP_REFERER', '/')
    return redirect(referer)


def download_funds_csv(request):
    """Download all funds as a CSV file."""
    # Create the HttpResponse object with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="funds.csv"'

    writer = csv.writer(response)
    writer.writerow(['ticker', 'name', 'category', 'preference'])

    # Get all funds
    funds = Fund.objects.select_related('category', 'category__asset_class').all()

    for fund in funds:
        # Format category as "Class:Category" or leave blank
        if fund.category:
            category_str = f"{fund.category.asset_class.name}:{fund.category.name}"
        else:
            category_str = ""

        writer.writerow([
            fund.ticker,
            fund.name,
            category_str,
            fund.preference if fund.preference is not None else 99
        ])

    return response


def upload_funds_csv(request):
    """Upload funds from a CSV file."""
    if request.method != 'POST':
        return redirect('settings')

    if 'file' not in request.FILES:
        request.session['funds_upload_error'] = 'No file uploaded'
        return redirect('settings')

    csv_file = request.FILES['file']

    # Validate file extension
    if not csv_file.name.endswith('.csv'):
        request.session['funds_upload_error'] = 'File must be a CSV'
        return redirect('settings')

    try:
        # Read and decode the CSV file
        file_data = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(file_data))

        inserted_count = 0
        skipped_count = 0
        errors = []

        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (after header)
            ticker = row.get('ticker', '').strip()
            name = row.get('name', '').strip()
            category_str = row.get('category', '').strip()
            preference_str = row.get('preference', '99').strip()

            if not ticker:
                errors.append(f"Row {row_num}: Missing ticker")
                continue

            # Check if fund already exists
            if Fund.objects.filter(ticker=ticker).exists():
                skipped_count += 1
                continue

            # Parse preference
            try:
                preference = int(preference_str) if preference_str else 99
            except ValueError:
                preference = 99

            # Parse category
            category = None
            if category_str:
                parts = category_str.split(':', 1)
                if len(parts) == 2:
                    class_name, category_name = parts[0].strip(), parts[1].strip()

                    # Find or create asset class
                    from .models import AssetClass
                    asset_class, _ = AssetClass.objects.get_or_create(name=class_name)

                    # Find or create category
                    category, _ = AssetCategory.objects.get_or_create(
                        asset_class=asset_class,
                        name=category_name
                    )

            # Create the fund
            Fund.objects.create(
                ticker=ticker,
                name=name if name else ticker,
                category=category,
                preference=preference
            )
            inserted_count += 1

        # Build success message
        message_parts = []
        if inserted_count > 0:
            message_parts.append(f"{inserted_count} fund(s) inserted")
        if skipped_count > 0:
            message_parts.append(f"{skipped_count} fund(s) skipped (already exist)")

        if errors:
            request.session['funds_upload_error'] = f"{'; '.join(message_parts)}. Errors: {'; '.join(errors)}"
        elif message_parts:
            request.session['funds_upload_success'] = '; '.join(message_parts)
        else:
            request.session['funds_upload_error'] = 'No funds were processed'

    except Exception as e:
        request.session['funds_upload_error'] = f'Error processing CSV: {str(e)}'

    return redirect('settings')


def modeling_view(request):
    """Monte Carlo retirement modeling page."""
    from .monte_carlo import run_monte_carlo_simulation
    from decimal import Decimal, InvalidOperation

    # Determine which user's data to show
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            current_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            current_user = User.objects.first()
    else:
        current_user = User.objects.first()

    if not current_user:
        return render(request, 'glidepath_app/modeling.html', {
            'portfolios': Portfolio.objects.none(),
            'selected_portfolio': None,
            'balance_info': None,
            'simulation_results': None,
            'errors': ['No user selected']
        })

    # Get all portfolios for the current user
    portfolios = Portfolio.objects.filter(user=current_user)

    # Handle portfolio selection
    selected_portfolio_id = request.GET.get('portfolio') or request.POST.get('portfolio')
    selected_portfolio = None
    balance_info = None
    simulation_results = None
    errors = []

    if selected_portfolio_id:
        try:
            selected_portfolio = portfolios.get(id=selected_portfolio_id)
        except Portfolio.DoesNotExist:
            errors.append("Selected portfolio not found.")

    if selected_portfolio:
        # Get balance info
        balance_info = selected_portfolio.get_balance_info()

        # Validation checks
        if balance_info['unmapped_positions']:
            unmapped_count = len(balance_info['unmapped_positions'])
            unmapped_list = ', '.join([f"{pos['symbol']} ({pos['account_number']})"
                                      for pos in balance_info['unmapped_positions'][:5]])
            if unmapped_count > 5:
                unmapped_list += f" and {unmapped_count - 5} more"
            errors.append(
                f"Cannot run simulation: {unmapped_count} position(s) are not mapped to asset categories. "
                f"Unmapped positions: {unmapped_list}. "
                f"Please map all positions on the Portfolio page before running simulation."
            )

        if not selected_portfolio.ruleset:
            errors.append("Cannot run simulation: Portfolio does not have a glidepath ruleset assigned. "
                        "Please assign a ruleset on the Portfolio page.")

        if not selected_portfolio.year_born or not selected_portfolio.retirement_age:
            errors.append("Cannot run simulation: Portfolio is missing birth year or retirement age. "
                        "Please configure these on the Portfolio page.")

        if balance_info['total_balance'] <= 0:
            errors.append("Cannot run simulation: Portfolio has no balance. "
                        "Please upload account positions on the Accounts page.")

        # If form submitted and no errors, run simulation
        if request.method == 'POST' and not errors:
            try:
                annual_contribution = Decimal(request.POST.get('annual_contribution', '0'))
                withdrawal_mode = request.POST.get('withdrawal_mode', 'percent')
                withdrawal_amount = float(request.POST.get('withdrawal_amount', '4.0'))
                inflation_rate = float(request.POST.get('inflation_rate', '3.0')) / 100  # Convert to decimal

                # Validate inputs
                if annual_contribution < 0:
                    errors.append("Annual contribution cannot be negative.")
                if withdrawal_amount <= 0:
                    errors.append("Withdrawal amount must be greater than zero.")
                if inflation_rate < 0 or inflation_rate > 1:
                    errors.append("Inflation rate must be between 0% and 100%.")

                if not errors:
                    simulation_results = run_monte_carlo_simulation(
                        selected_portfolio,
                        annual_contribution,
                        withdrawal_mode,
                        withdrawal_amount,
                        inflation_rate
                    )

                    # Prepare chart data
                    simulation_results['chart_data'] = json.dumps({
                        'percentile_10': simulation_results['percentile_10'],
                        'percentile_50': simulation_results['percentile_50'],
                        'percentile_90': simulation_results['percentile_90'],
                    })
            except (ValueError, InvalidOperation) as e:
                errors.append(f"Invalid input: {str(e)}")
            except Exception as e:
                errors.append(f"Error running simulation: {str(e)}")

    context = {
        'portfolios': portfolios,
        'selected_portfolio': selected_portfolio,
        'balance_info': balance_info,
        'simulation_results': simulation_results,
        'errors': errors,
        'current_user': current_user,
    }

    return render(request, 'glidepath_app/modeling.html', context)
