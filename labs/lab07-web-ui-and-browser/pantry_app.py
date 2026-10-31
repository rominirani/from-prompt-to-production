"""Lab 07: Smart Pantry & Recipe Tracker Web App with FastAPI, HTMX, and Gemini.

Demonstrates how to turn a UI sketch into a secure, server-rendered Python web
application using FastAPI, HTMX partial HTML updates, Pydantic v2 validation,
parameterized SQLite storage, and strict XSS/CSP security controls.
"""

from __future__ import annotations

import html
import os
import sqlite3
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_CATEGORIES = {"Produce", "Grains", "Dairy", "Spices", "Proteins", "Pantry"}
ALLOWED_UNITS = {"g", "kg", "ml", "l", "pcs", "cups", "tbsp", "tsp"}

STRICT_CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


class PantryItemCreate(BaseModel):
    """Validated payload for adding an ingredient to the Smart Pantry."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(
        ...,
        min_length=1,
        max_length=80,
        description="Ingredient name, such as 'Chickpeas' or 'Spinach'.",
    )
    category: str = Field(
        default="Pantry",
        description="Ingredient category (Produce, Grains, Dairy, Spices, Proteins, Pantry).",
    )
    quantity: float = Field(
        ...,
        ge=0.0,
        le=10000.0,
        description="Current quantity on hand.",
    )
    unit: str = Field(
        default="pcs",
        description="Unit of measurement (g, kg, ml, l, pcs, cups, tbsp, tsp).",
    )
    reorder_threshold: float = Field(
        default=1.0,
        ge=0.0,
        le=10000.0,
        description="Quantity at or below which the ingredient is marked low stock.",
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        titled = value.capitalize()
        if titled not in ALLOWED_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(ALLOWED_CATEGORIES)}")
        return titled

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        lowered = value.lower()
        if lowered not in ALLOWED_UNITS:
            raise ValueError(f"unit must be one of {sorted(ALLOWED_UNITS)}")
        return lowered


class PantryItemRecord(BaseModel):
    """Stored pantry ingredient with computed low-stock flag."""

    model_config = ConfigDict(extra="forbid")

    item_id: int
    name: str
    category: str
    quantity: float
    unit: str
    reorder_threshold: float

    @property
    def is_low_stock(self) -> bool:
        return self.quantity <= self.reorder_threshold


class RecipeSuggestion(BaseModel):
    """Structured recipe output from Gemini or the offline recipe matcher."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., description="Short, appetizing recipe title.")
    prep_time_minutes: int = Field(..., ge=1, le=240)
    matched_ingredients: list[str] = Field(
        default_factory=list,
        description="Ingredients from the user's pantry used in this recipe.",
    )
    missing_low_stock_items: list[str] = Field(
        default_factory=list,
        description="Low-stock pantry items that should be restocked soon.",
    )
    steps: list[str] = Field(
        ...,
        min_length=1,
        description="Clear step-by-step cooking instructions.",
    )


def _resolve_db_path() -> Path:
    """Return the active SQLite database path for the pantry app."""
    configured = os.environ.get("PANTRY_DB_PATH")
    if configured:
        return Path(configured).resolve()
    return Path(tempfile.gettempdir()) / "prompt_to_prod_lab07_pantry.db"


def init_pantry_db(db_path: Path | None = None, seed_defaults: bool = True) -> Path:
    """Initialize the SQLite schema and optionally seed starter ingredients."""
    target_path = db_path or _resolve_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pantry_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                reorder_threshold REAL NOT NULL
            )
            """
        )
        existing_count = conn.execute("SELECT COUNT(*) FROM pantry_items").fetchone()[0]
        if seed_defaults and existing_count == 0:
            starter_items = [
                ("Chickpeas", "Proteins", 2.0, "cups", 1.0),
                ("Baby Spinach", "Produce", 1.0, "cups", 2.0),
                ("Basmati Rice", "Grains", 4.0, "cups", 1.5),
                ("Cumin Seeds", "Spices", 0.5, "tbsp", 1.0),
            ]
            conn.executemany(
                """
                INSERT INTO pantry_items (name, category, quantity, unit, reorder_threshold)
                VALUES (?, ?, ?, ?, ?)
                """,
                starter_items,
            )
        conn.commit()
    return target_path


def list_pantry_items(db_path: Path | None = None) -> list[PantryItemRecord]:
    """Fetch all pantry items using a parameterized query."""
    target_path = init_pantry_db(db_path, seed_defaults=True)
    with sqlite3.connect(target_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT item_id, name, category, quantity, unit, reorder_threshold
            FROM pantry_items
            ORDER BY item_id ASC
            """
        ).fetchall()

    return [
        PantryItemRecord(
            item_id=int(row["item_id"]),
            name=str(row["name"]),
            category=str(row["category"]),
            quantity=float(row["quantity"]),
            unit=str(row["unit"]),
            reorder_threshold=float(row["reorder_threshold"]),
        )
        for row in rows
    ]


def insert_pantry_item(
    payload: PantryItemCreate,
    db_path: Path | None = None,
) -> PantryItemRecord:
    """Insert a validated pantry ingredient using parameterized SQL."""
    target_path = init_pantry_db(db_path, seed_defaults=True)
    with sqlite3.connect(target_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO pantry_items (name, category, quantity, unit, reorder_threshold)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.category,
                payload.quantity,
                payload.unit,
                payload.reorder_threshold,
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        conn.commit()

    return PantryItemRecord(
        item_id=new_id,
        name=payload.name,
        category=payload.category,
        quantity=payload.quantity,
        unit=payload.unit,
        reorder_threshold=payload.reorder_threshold,
    )


def generate_recipe_suggestion(items: list[PantryItemRecord]) -> RecipeSuggestion:
    """Suggest a recipe from current pantry items via google-genai or offline fallback."""
    ingredient_names = [item.name for item in items if item.quantity > 0]
    low_stock_names = [item.name for item in items if item.is_low_stock]

    if not ingredient_names:
        return RecipeSuggestion(
            title="Pantry Restock Reminder",
            prep_time_minutes=5,
            matched_ingredients=[],
            missing_low_stock_items=low_stock_names,
            steps=["Add at least one available ingredient to generate a recipe."],
        )

    # Never hardcode API keys; read strictly from environment variables
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = (
                "Create a practical home-cooked recipe using these pantry ingredients: "
                f"{', '.join(ingredient_names)}. "
                f"Low-stock items to note: {', '.join(low_stock_names) or 'None'}."
            )
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RecipeSuggestion,
                    temperature=0.2,
                ),
            )
            if response.text:
                return RecipeSuggestion.model_validate_json(response.text)
        except Exception:
            # Fail safe to deterministic offline recipe matcher if network/API is unavailable
            pass

    top_ingredients = ingredient_names[:4]
    title_focus = " & ".join(top_ingredients[:2])
    return RecipeSuggestion(
        title=f"One-Pan {title_focus} Skillet",
        prep_time_minutes=20,
        matched_ingredients=top_ingredients,
        missing_low_stock_items=low_stock_names,
        steps=[
            f"Measure and prep {', '.join(top_ingredients)}.",
            "Warm a skillet over medium heat and toast any spices for 30 seconds.",
            "Fold in the main pantry ingredients with a splash of water and simmer for 12 minutes.",
            "Season to taste and serve warm.",
        ],
    )


def render_pantry_row_html(item: PantryItemRecord) -> str:
    """Render a single HTML table row with all untrusted strings strictly escaped."""
    safe_name = html.escape(item.name, quote=True)
    safe_category = html.escape(item.category, quote=True)
    safe_unit = html.escape(item.unit, quote=True)
    safe_qty = html.escape(f"{item.quantity:g}", quote=True)
    safe_threshold = html.escape(f"{item.reorder_threshold:g}", quote=True)

    if item.is_low_stock:
        badge_html = '<span class="badge badge-low">LOW STOCK</span>'
    else:
        badge_html = '<span class="badge badge-ok">IN STOCK</span>'

    return (
        f'<tr id="pantry-item-{item.item_id}" class="pantry-row">'
        f'<td class="cell-name">{safe_name}</td>'
        f'<td class="cell-category">{safe_category}</td>'
        f'<td class="cell-qty">{safe_qty} {safe_unit}</td>'
        f'<td class="cell-threshold">{safe_threshold} {safe_unit}</td>'
        f'<td class="cell-status">{badge_html}</td>'
        "</tr>"
    )


def render_recipe_card_html(recipe: RecipeSuggestion) -> str:
    """Render a structured RecipeSuggestion as a safe, escaped HTML fragment."""
    safe_title = html.escape(recipe.title, quote=True)
    safe_prep = html.escape(str(recipe.prep_time_minutes), quote=True)

    matched_badges = "".join(
        f'<span class="tag">{html.escape(ing, quote=True)}</span>'
        for ing in recipe.matched_ingredients
    ) or '<span class="tag">None</span>'

    low_stock_badges = "".join(
        f'<span class="tag tag-warn">{html.escape(ing, quote=True)}</span>'
        for ing in recipe.missing_low_stock_items
    ) or '<span class="tag">None</span>'

    steps_list = "".join(
        f'<li class="recipe-step">{html.escape(step, quote=True)}</li>'
        for step in recipe.steps
    )

    return (
        '<article class="recipe-card" id="generated-recipe-card">'
        f'<h3 class="recipe-title">{safe_title}</h3>'
        f'<p class="recipe-meta">Prep time: <strong>{safe_prep} mins</strong></p>'
        f'<div class="recipe-tags"><strong>Using:</strong> {matched_badges}</div>'
        f'<div class="recipe-tags"><strong>Restock soon:</strong> {low_stock_badges}</div>'
        f'<ol class="recipe-steps">{steps_list}</ol>'
        "</article>"
    )


def render_dashboard_html(items: list[PantryItemRecord]) -> str:
    """Render the full Smart Pantry HTML page with HTMX attributes and quoted attributes."""
    rows_html = "\n".join(render_pantry_row_html(item) for item in items)
    low_stock_count = sum(1 for item in items if item.is_low_stock)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Smart Pantry &amp; Recipe Tracker</title>
  <link rel="stylesheet" href="/styles.css" />
</head>
<body>
  <header class="site-header">
    <h1>Smart Pantry &amp; Recipe Tracker</h1>
    <p class="subtitle">Server-Rendered FastAPI + HTMX + Gemini Structured Recipes</p>
    <p class="summary-banner" id="low-stock-summary">
      Tracking <strong>{len(items)}</strong> ingredients (<strong>{low_stock_count}</strong> low-stock alerts)
    </p>
  </header>

  <main class="dashboard-grid">
    <section class="card" aria-labelledby="inventory-heading">
      <h2 id="inventory-heading">Pantry Inventory</h2>
      <table class="pantry-table">
        <thead>
          <tr>
            <th scope="col">Ingredient</th>
            <th scope="col">Category</th>
            <th scope="col">On Hand</th>
            <th scope="col">Reorder At</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody id="pantry-table-body">
          {rows_html}
        </tbody>
      </table>
    </section>

    <section class="card" aria-labelledby="add-item-heading">
      <h2 id="add-item-heading">Add Ingredient</h2>
      <form
        id="add-pantry-form"
        action="/pantry/items"
        method="post"
        hx-post="/pantry/items"
        hx-target="#pantry-table-body"
        hx-swap="beforeend"
      >
        <div class="form-row">
          <label for="name-input">Ingredient Name</label>
          <input id="name-input" name="name" type="text" required="required" maxlength="80" placeholder="e.g. Garlic Cloves" />
        </div>
        <div class="form-row">
          <label for="category-input">Category</label>
          <select id="category-input" name="category">
            <option value="Produce">Produce</option>
            <option value="Grains">Grains</option>
            <option value="Dairy">Dairy</option>
            <option value="Spices">Spices</option>
            <option value="Proteins">Proteins</option>
            <option value="Pantry" selected="selected">Pantry</option>
          </select>
        </div>
        <div class="form-row">
          <label for="quantity-input">Quantity</label>
          <input id="quantity-input" name="quantity" type="number" step="0.1" min="0" value="2" required="required" />
        </div>
        <div class="form-row">
          <label for="unit-input">Unit</label>
          <select id="unit-input" name="unit">
            <option value="pcs" selected="selected">pcs</option>
            <option value="cups">cups</option>
            <option value="g">g</option>
            <option value="kg">kg</option>
            <option value="tbsp">tbsp</option>
            <option value="tsp">tsp</option>
          </select>
        </div>
        <div class="form-row">
          <label for="threshold-input">Low-Stock Threshold</label>
          <input id="threshold-input" name="reorder_threshold" type="number" step="0.1" min="0" value="1" required="required" />
        </div>
        <button id="add-ingredient-btn" type="submit" class="btn-primary">Add to Pantry</button>
      </form>
    </section>

    <section class="card" aria-labelledby="recipe-heading">
      <h2 id="recipe-heading">AI Chef Suggestion</h2>
      <p>Generate a quick recipe tailored to the ingredients currently in your pantry.</p>
      <button
        id="suggest-recipe-btn"
        type="button"
        class="btn-secondary"
        hx-post="/pantry/recipes/suggest"
        hx-target="#recipe-result"
        hx-swap="innerHTML"
      >
        Suggest Recipe with Gemini
      </button>
      <div id="recipe-result" class="recipe-container">
        <p class="placeholder-text">Click "Suggest Recipe with Gemini" to generate a meal idea.</p>
      </div>
    </section>
  </main>
</body>
</html>"""


# TODO(security): Add OAuth2/cookie-backed authentication and CSRF synchronizer tokens
# before exposing this local single-user pantry tracker to a multi-user network.
app = FastAPI(title="Smart Pantry & Recipe Tracker (Lab 07)")


@app.middleware("http")
async def enforce_security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach strict CSP, anti-clickjacking, and nosniff headers to every response."""
    if request.method not in {"GET", "POST", "HEAD"}:
        return Response(status_code=405, content="Method Not Allowed")

    response = await call_next(request)
    response.headers["Content-Security-Policy"] = STRICT_CSP_HEADER
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/styles.css")
def get_stylesheet() -> Response:
    """Serve the application stylesheet from 'self' to satisfy strict CSP."""
    css = """
    body { font-family: system-ui, sans-serif; margin: 0; padding: 2rem; background: #f8fafc; color: #0f172a; }
    .site-header { margin-bottom: 1.5rem; }
    .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }
    .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 0.75rem; padding: 1.25rem; }
    .pantry-table { width: 100%; border-collapse: collapse; }
    .pantry-table th, .pantry-table td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #e2e8f0; }
    .badge { padding: 0.2rem 0.5rem; border-radius: 0.375rem; font-size: 0.75rem; font-weight: 600; }
    .badge-low { background: #fee2e2; color: #991b1b; }
    .badge-ok { background: #dcfce7; color: #166534; }
    .form-row { margin-bottom: 0.75rem; display: flex; flex-direction: column; }
    .btn-primary, .btn-secondary { padding: 0.6rem 1rem; border-radius: 0.5rem; border: none; cursor: pointer; font-weight: 600; }
    .btn-primary { background: #2563eb; color: #ffffff; }
    .btn-secondary { background: #0f766e; color: #ffffff; }
    .tag { display: inline-block; margin-right: 0.4rem; padding: 0.15rem 0.45rem; background: #e0f2fe; border-radius: 0.25rem; }
    .tag-warn { background: #fef3c7; color: #92400e; }
    """
    return Response(content=css.strip(), media_type="text/css")


@app.get("/", response_class=HTMLResponse)
def get_dashboard() -> HTMLResponse:
    """Render the main Smart Pantry dashboard."""
    items = list_pantry_items()
    return HTMLResponse(content=render_dashboard_html(items))


@app.post("/pantry/items", response_class=HTMLResponse, status_code=201)
async def add_pantry_item_endpoint(request: Request) -> HTMLResponse:
    """Validate and insert a new pantry ingredient, returning an HTMX table row fragment."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        raw_data = await request.json()
    else:
        form_data = await request.form()
        raw_data = dict(form_data)

    try:
        validated = PantryItemCreate.model_validate(raw_data)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid pantry item input: {exc}",
        ) from exc

    record = insert_pantry_item(validated)
    return HTMLResponse(content=render_pantry_row_html(record), status_code=201)


@app.post("/pantry/recipes/suggest", response_class=HTMLResponse)
def suggest_recipe_endpoint() -> HTMLResponse:
    """Generate a recipe from the current pantry inventory and return an HTML card fragment."""
    items = list_pantry_items()
    suggestion = generate_recipe_suggestion(items)
    return HTMLResponse(content=render_recipe_card_html(suggestion))


if __name__ == "__main__":
    import uvicorn

    # Always bind local development servers strictly to 127.0.0.1 (never 0.0.0.0)
    uvicorn.run(app, host="127.0.0.1", port=8007)
