from django.shortcuts import render
from .forms import OptimizeForm
from .utils.processors import CoffeeRecipeOptimizer  # pastikan import benar

from django.shortcuts import render
from .forms import OptimizeForm
from .utils.processors import CoffeeRecipeOptimizer

def optimize_view(request):
    result = None
    message = None
    status_type = None

    if request.method == "POST":
        form = OptimizeForm(request.POST)
        if form.is_valid():
            density_input = form.cleaned_data["density"]
            strength = form.cleaned_data["target_strength"]

            try:
                optimizer = CoffeeRecipeOptimizer()
                items, actual_density = optimizer.find_best_recipes(
                    density=density_input, target_strength=strength, top_n=20
                )

                if not items:
                    message = "⚠️ No suitable combinations were found for your criteria."
                    status_type = "error"
                else:
                    # Mark the best result (fuzzy=1 & topsis=1)
                    for row in items:
                        compat = float(row["recipe"].get("compatibility", 0.0))
                        topsis = float(row.get("topsis_score", 0.0))
                        row["is_top"] = (compat == 1.0 and topsis == 1.0)

                    top_items = [r for r in items if r["is_top"]]
                    others = [r for r in items if not r["is_top"]]

                    # If no perfect top result → use the first item as top recommendation
                    if not top_items and items:
                        top_items = [items[0]]
                        others = items[1:]

                    # Prepare card display data for top recommendations
                    best_cards = []
                    for r in top_items:
                        br = r["recipe"]
                        best_cards.append({
                            "density": br["density"],
                            "temp": br["temp"],
                            "grindsize": br["grindsize"],
                            "ratio": br["ratio"],
                            "strength": br["strength"],
                            "fuzzy_pct": round(float(br.get("compatibility", 0.0)) * 100.0, 1),
                            "topsis": round(float(r.get("topsis_score", 0.0)), 3),
                        })

                    # Table will show up to 4 additional results
                    table_items_raw = others[:4]
                    table_items = []
                    next_rank = 2
                    for r in table_items_raw:
                        r = dict(r)
                        r["rank"] = next_rank
                        next_rank += 1
                        table_items.append(r)

                    # Validation message for density adjustment
                    if actual_density != density_input:
                        message = f"Input density {density_input} was rounded to {actual_density} for valid results."
                        status_type = "warning"
                    else:
                        message = f"Recommendation results successfully generated for density {density_input}."
                        status_type = "success"

                    result = {
                        "density_input": density_input,
                        "density_actual": actual_density,
                        "strength": strength.title(),
                        "best_cards": best_cards,   # rank 1 (can be multiple)
                        "table_items": table_items,  # rank 2–5
                    }

            except Exception as e:
                message = f"An error occurred while processing the data: {e}"
                status_type = "error"
        else:
            message = "Please fill out all fields correctly."
            status_type = "error"
    else:
        form = OptimizeForm()

    return render(request, "optimize.html", {
        "form": form,
        "result": result,
        "message": message,
        "status_type": status_type,
    })