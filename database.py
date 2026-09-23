"""
The demo company database: 8 related tables for a fictional retailer, "Acme Retail Co.".

All rows are randomly generated (but realistic), so no real company data is used.
The table and column descriptions below are also what the AI reads to understand
the database - good descriptions are the secret to good text-to-SQL.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

COMPANY_NAME = "Acme Retail Co."
YEARS_OF_HISTORY = 3

# ---------------------------------------------------------------------------
# Documentation of every table and column (shown in the app and sent to the AI)
# ---------------------------------------------------------------------------

TABLE_INFO = {
    "regions": ("Sales regions the company operates in.", {
        "region_id": "Unique region ID",
        "region_name": "Region name ('Online' is the region of the web store)",
    }),
    "stores": ("Physical stores plus one online store.", {
        "store_id": "Unique store ID",
        "store_name": "Store name",
        "city": "City the store is in ('Online' for the web store)",
        "region_id": "Region the store belongs to",
        "store_type": "Type of store",
    }),
    "employees": ("Staff who make the sales.", {
        "employee_id": "Unique employee ID",
        "first_name": "First name",
        "last_name": "Last name",
        "job_title": "Job title",
        "store_id": "Store the employee works at",
        "hire_date": "Date the employee was hired",
    }),
    "customers": ("People and businesses who buy from the company.", {
        "customer_id": "Unique customer ID",
        "first_name": "First name",
        "last_name": "Last name",
        "city": "City the customer lives in",
        "region_id": "Region the customer lives in",
        "segment": "Customer type",
        "loyalty_tier": "Loyalty program level (Platinum is the best)",
        "signup_date": "Date the customer signed up",
    }),
    "categories": ("Product categories.", {
        "category_id": "Unique category ID",
        "category_name": "Category name",
    }),
    "products": ("Everything the company sells.", {
        "product_id": "Unique product ID",
        "product_name": "Product name",
        "category_id": "Product category",
        "list_price": "Normal selling price in USD",
        "unit_cost": "What the company pays per unit, in USD",
    }),
    "orders": ("One row per customer order.", {
        "order_id": "Unique order ID",
        "customer_id": "Customer who placed the order",
        "store_id": "Store that made the sale (the online store for web orders)",
        "employee_id": "Employee who handled the sale",
        "order_date": "Date of the order",
        "channel": "Where the order was placed",
        "status": "Order status",
    }),
    "order_items": ("The products inside each order (one row per product per order).", {
        "order_item_id": "Unique order line ID",
        "order_id": "Order this line belongs to",
        "product_id": "Product bought",
        "quantity": "Number of units bought",
        "unit_price": "Price charged per unit before discount, in USD",
        "discount": "Discount as a fraction (0.10 = 10% off)",
    }),
}

# The first column of every table is its primary key
PRIMARY_KEYS = {table: [next(iter(columns))] for table, (_, columns) in TABLE_INFO.items()}

# (table, column) points to (parent table, parent column)
RELATIONSHIPS = [
    ("stores", "region_id", "regions", "region_id"),
    ("employees", "store_id", "stores", "store_id"),
    ("customers", "region_id", "regions", "region_id"),
    ("products", "category_id", "categories", "category_id"),
    ("orders", "customer_id", "customers", "customer_id"),
    ("orders", "store_id", "stores", "store_id"),
    ("orders", "employee_id", "employees", "employee_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
]


def business_rules(start, end):
    """How the company defines its metrics. The AI must follow these so answers match the business."""
    return f"""- Revenue (sales) = SUM(order_items.quantity * order_items.unit_price * (1 - order_items.discount)).
  Only count orders WHERE orders.status = 'Completed' unless the user asks otherwise.
- Profit = revenue - SUM(order_items.quantity * products.unit_cost). Profit margin = profit / revenue.
- Number of orders = COUNT(DISTINCT orders.order_id). Average order value = revenue / number of orders.
- Return rate = returned orders / (completed + returned orders).
- Sales region = orders.store_id -> stores.region_id. Customer home region = customers.region_id.
- Today is {end:%Y-%m-%d}. Orders exist from {start:%Y-%m-%d} to {end:%Y-%m-%d}.
  "This year" = {end.year}, "last year" = {end.year - 1}."""


# ---------------------------------------------------------------------------
# Reference data used to generate realistic rows
# ---------------------------------------------------------------------------

REGION_CITIES = {
    "North": ["Chicago", "Minneapolis", "Detroit"],
    "South": ["Houston", "Atlanta", "Miami"],
    "East": ["New York", "Boston", "Philadelphia"],
    "West": ["Los Angeles", "Seattle", "San Francisco"],
    "Central": ["Denver", "Kansas City", "Dallas"],
}

# (store name, city, region, store type)
STORES = [
    ("Chicago Flagship", "Chicago", "North", "Flagship"),
    ("Detroit Outlet", "Detroit", "North", "Outlet"),
    ("Houston Galleria", "Houston", "South", "Standard"),
    ("Miami Beach", "Miami", "South", "Standard"),
    ("Manhattan Flagship", "New York", "East", "Flagship"),
    ("Boston Back Bay", "Boston", "East", "Standard"),
    ("LA Flagship", "Los Angeles", "West", "Flagship"),
    ("Seattle Downtown", "Seattle", "West", "Standard"),
    ("Denver Central", "Denver", "Central", "Standard"),
    ("Dallas Outlet", "Dallas", "Central", "Outlet"),
    ("Acme Online", "Online", "Online", "Online"),
]
STORE_TYPE_WEIGHT = {"Flagship": 1.6, "Standard": 1.0, "Outlet": 0.7}
STAFF_PER_STORE = {"Flagship": 8, "Standard": 5, "Outlet": 4, "Online": 6}

# category -> (popularity, [(product name, list price), ...])
CATEGORIES = {
    "Electronics": (1.3, [
        ("Wireless Earbuds", 79), ("4K Smart TV", 649), ("Laptop Pro 14", 1199), ("Bluetooth Speaker", 59),
        ("Smartwatch", 249), ("Tablet 10-inch", 329), ("Gaming Console", 499), ("Noise-Cancelling Headphones", 299),
    ]),
    "Home & Kitchen": (1.1, [
        ("Espresso Machine", 389), ("Air Fryer", 119), ("Blender", 69), ("Cookware Set", 179),
        ("Robot Vacuum", 299), ("Stand Mixer", 349), ("Knife Set", 89), ("Desk Lamp", 39),
    ]),
    "Clothing": (1.2, [
        ("Denim Jacket", 89), ("Running Shoes", 119), ("Wool Sweater", 75), ("Rain Jacket", 99),
        ("Cotton T-Shirt", 19), ("Chino Pants", 55), ("Leather Boots", 159), ("Hoodie", 49),
    ]),
    "Sports & Outdoors": (0.8, [
        ("Yoga Mat", 35), ("Adjustable Dumbbells", 229), ("Camping Tent", 189), ("Mountain Bike", 649),
        ("Hiking Backpack", 99), ("Tennis Racket", 129), ("Fitness Tracker", 99), ("Water Bottle", 25),
    ]),
    "Beauty": (0.7, [
        ("Skincare Set", 65), ("Hair Dryer", 89), ("Perfume", 95), ("Electric Toothbrush", 79),
        ("Makeup Palette", 45), ("Beard Trimmer", 59),
    ]),
    "Toys": (0.6, [
        ("Building Blocks Set", 59), ("RC Car", 79), ("Board Game", 35), ("Plush Bear", 25),
        ("Science Kit", 45), ("Mini Drone", 129),
    ]),
}

FIRST_NAMES = [
    "James", "Mary", "Priya", "Wei", "Carlos", "Aisha", "Liam", "Sofia", "Noah", "Emma", "Arjun", "Mei",
    "Diego", "Fatima", "Ethan", "Olivia", "Hiroshi", "Ana", "Lucas", "Chloe", "Omar", "Grace", "Mateo",
    "Zara", "Daniel", "Ava", "Ravi", "Lina", "Samuel", "Isabella", "Kenji", "Maya", "David", "Nora",
]
LAST_NAMES = [
    "Smith", "Johnson", "Patel", "Chen", "Garcia", "Khan", "Brown", "Martinez", "Lee", "Williams",
    "Nguyen", "Kim", "Lopez", "Singh", "Davis", "Wilson", "Tanaka", "Rossi", "Anderson", "Thomas",
    "Hernandez", "Moore", "Ali", "Clark", "Lewis", "Walker", "Young", "Shah", "Hall", "Allen",
]


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

def history_window(end=None):
    end = end or date.today()
    return end - timedelta(days=365 * YEARS_OF_HISTORY), end


def generate_tables(end=None, seed=7):
    """Create all 8 tables as pandas DataFrames, parents before children."""
    rng = np.random.default_rng(seed)
    start, end = history_window(end)
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    # --- regions & stores ---
    region_names = list(REGION_CITIES) + ["Online"]  # the web store gets its own sales region
    regions = pd.DataFrame({"region_id": range(1, len(region_names) + 1), "region_name": region_names})
    region_id = dict(zip(region_names, regions.region_id))
    stores = pd.DataFrame([
        {"store_id": i + 1, "store_name": name, "city": city, "region_id": region_id[region], "store_type": kind}
        for i, (name, city, region, kind) in enumerate(STORES)
    ])

    # --- employees: one store manager plus sales staff per store ---
    employees = []
    for store in stores.itertuples():
        staff_title = "Customer Service Agent" if store.store_type == "Online" else "Sales Associate"
        for title in ["Store Manager"] + [staff_title] * STAFF_PER_STORE[store.store_type]:
            employees.append({
                "employee_id": len(employees) + 1, "first_name": rng.choice(FIRST_NAMES),
                "last_name": rng.choice(LAST_NAMES), "job_title": title, "store_id": store.store_id,
                "hire_date": end_ts - pd.Timedelta(days=int(rng.integers(120, 365 * 8))),
            })
    employees = pd.DataFrame(employees)
    sellers = {  # who can make a sale in each store, and how good they are at it
        store_id: (group.employee_id.values, group.hire_date.values, rng.lognormal(0, 0.45, len(group)))
        for store_id, group in employees[employees.job_title != "Store Manager"].groupby("store_id")
    }

    # --- customers (IDs follow signup order) ---
    n_customers = 3000
    home_region = rng.choice(list(REGION_CITIES), n_customers, p=[0.22, 0.20, 0.24, 0.22, 0.12])
    tiers = rng.choice(["Bronze", "Silver", "Gold", "Platinum"], n_customers, p=[0.5, 0.3, 0.15, 0.05])
    signup_days = np.sort(rng.integers(0, (end - start).days + 730, n_customers))
    customers = pd.DataFrame({
        "customer_id": np.arange(1, n_customers + 1),
        "first_name": rng.choice(FIRST_NAMES, n_customers),
        "last_name": rng.choice(LAST_NAMES, n_customers),
        "city": [rng.choice(REGION_CITIES[r]) for r in home_region],
        "region_id": [region_id[r] for r in home_region],
        "segment": rng.choice(["Consumer", "Corporate", "Small Business"], n_customers, p=[0.6, 0.25, 0.15]),
        "loyalty_tier": tiers,
        "signup_date": start_ts - pd.Timedelta(days=730) + pd.to_timedelta(signup_days, unit="D"),
    })

    # --- categories & products ---
    categories = pd.DataFrame({"category_id": range(1, len(CATEGORIES) + 1), "category_name": list(CATEGORIES)})
    products = []
    for category_id, (popularity, items) in enumerate(CATEGORIES.values(), start=1):
        for product_name, price in items:
            products.append({
                "product_id": len(products) + 1, "product_name": product_name, "category_id": category_id,
                "list_price": float(price), "unit_cost": round(price * rng.uniform(0.45, 0.7), 2),
            })
    products = pd.DataFrame(products)
    category_names = list(CATEGORIES)
    product_category = np.array([category_names[c - 1] for c in products.category_id])
    product_weight = np.array([CATEGORIES[c][0] for c in product_category]) / np.sqrt(products.list_price.values)

    # --- orders: growth over time, holiday peaks, busier weekends, online growing ---
    days = pd.date_range(start, end, freq="D")
    season = days.month.map({1: 0.8, 2: 0.85, 3: 0.95, 4: 1, 5: 1, 6: 1.05, 7: 1.05, 8: 1.1, 9: 0.95,
                             10: 1.05, 11: 1.5, 12: 1.9}).values
    weights = (1 + 0.6 * np.linspace(0, 1, len(days))) * season * np.where(days.dayofweek >= 5, 1.25, 1.0)
    n_orders = 15000
    order_dates = np.sort(rng.choice(days.values, n_orders, p=weights / weights.sum()))

    # Customers only order after signing up; higher loyalty tiers order more often
    tier_weight = pd.Series(tiers).map({"Bronze": 1, "Silver": 1.5, "Gold": 2.5, "Platinum": 4}).values
    cumulative = np.cumsum(tier_weight)
    signed_up = np.maximum(np.searchsorted(customers.signup_date.values, order_dates, side="right"), 1)
    picked = np.searchsorted(cumulative, rng.random(n_orders) * cumulative[signed_up - 1], side="right")
    order_customers = np.minimum(picked, signed_up - 1)

    physical = stores[stores.store_type != "Online"]
    online_store = int(stores.loc[stores.store_type == "Online", "store_id"].iloc[0])
    store_info = stores.set_index("store_id")
    west = region_id["West"]

    orders, items = [], []
    for i, order_date in enumerate(order_dates):
        progress = (order_date - start_ts.to_datetime64()) / (end_ts - start_ts).to_timedelta64()
        customer = customers.iloc[order_customers[i]]

        # Online share grows from about 22% to 47% over the years
        if rng.random() < 0.22 + 0.25 * progress:
            channel, store = "Online", online_store
        else:
            channel = "In-store"
            nearby = physical.region_id.values == customer.region_id
            pool = nearby if rng.random() < 0.85 and nearby.any() else np.ones(len(physical), bool)
            w = physical.store_type.map(STORE_TYPE_WEIGHT).values * pool
            store = int(rng.choice(physical.store_id.values, p=w / w.sum()))

        ids, hired, skill = sellers[store]
        w = skill * (hired <= order_date) + 1e-9  # only staff hired before the order
        employee = int(rng.choice(ids, p=w / w.sum()))

        # Order lines: the West buys more electronics; holidays and outlets mean bigger discounts
        w = product_weight * np.where((product_category == "Electronics") & (store_info.region_id[store] == west), 1.6, 1)
        holiday_or_outlet = pd.Timestamp(order_date).month in (11, 12) or store_info.store_type[store] == "Outlet"
        biggest_discount, has_clothing = 0, False
        for product in rng.choice(len(products), min(1 + rng.poisson(1.2), 5), replace=False, p=w / w.sum()):
            price = products.list_price.values[product] * (1 + 0.09 * progress) * (1 + rng.normal(0, 0.02))
            discount = rng.choice([0, 0.05, 0.1, 0.15, 0.2, 0.3],
                                  p=[0.3, 0.15, 0.2, 0.15, 0.12, 0.08] if holiday_or_outlet
                                  else [0.55, 0.15, 0.15, 0.08, 0.05, 0.02])
            if customer.loyalty_tier in ("Gold", "Platinum") and discount < 0.3 and rng.random() < 0.5:
                discount += 0.05
            biggest_discount = max(biggest_discount, discount)
            has_clothing |= product_category[product] == "Clothing"
            items.append({
                "order_item_id": len(items) + 1, "order_id": i + 1, "product_id": int(product) + 1,
                "quantity": int(rng.choice([1, 2, 3], p=[0.7, 0.2, 0.1])),
                "unit_price": round(float(price), 2), "discount": round(float(discount), 2),
            })

        # Orders with clothing (sizes!) or big discounts get returned more often
        chance = rng.random()
        if chance < 0.04:
            status = "Cancelled"
        elif chance < 0.08 + 0.05 * has_clothing + 0.3 * biggest_discount:
            status = "Returned"
        else:
            status = "Completed"
        orders.append({"order_id": i + 1, "customer_id": int(customer.customer_id), "store_id": store,
                       "employee_id": employee, "order_date": order_date, "channel": channel, "status": status})

    return {
        "regions": regions, "stores": stores, "employees": employees, "customers": customers,
        "categories": categories, "products": products,
        "orders": pd.DataFrame(orders), "order_items": pd.DataFrame(items),
    }


# ---------------------------------------------------------------------------
# Loading into DuckDB (with real primary and foreign keys)
# ---------------------------------------------------------------------------

def sql_type(column, series):
    if column.endswith("_date"):
        return "DATE"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE"
    return "VARCHAR"


def load_into_duckdb(con, tables):
    for name, df in tables.items():
        columns = [f"{col} {sql_type(col, df[col])}" for col in df.columns]
        columns.append(f"PRIMARY KEY ({', '.join(PRIMARY_KEYS[name])})")
        columns += [f"FOREIGN KEY ({col}) REFERENCES {parent}({parent_col})"
                    for child, col, parent, parent_col in RELATIONSHIPS if child == name]
        con.execute(f"CREATE TABLE {name} ({', '.join(columns)})")
        con.register("new_rows", df)
        con.execute(f"INSERT INTO {name} SELECT * FROM new_rows")
        con.unregister("new_rows")


# ---------------------------------------------------------------------------
# ER diagram (entity-relationship diagram) of the tables
# ---------------------------------------------------------------------------

def foreign_keys(table):
    return {col: parent for child, col, parent, _ in RELATIONSHIPS if child == table}


def er_diagram_dot():
    """Graphviz description of the tables and how they connect (drawn in the app)."""
    lines = [
        "digraph ER {",
        '  graph [rankdir=LR, bgcolor="transparent", nodesep=0.4, ranksep=1.0];',
        '  node [shape=plaintext, fontname="Helvetica", fontsize=11];',
        '  edge [color="#8b8fa3", arrowhead=crow, arrowtail=tee, dir=both, penwidth=1.3];',
    ]
    for table, (_, columns) in TABLE_INFO.items():
        fks = foreign_keys(table)
        rows = [f'<tr><td bgcolor="#4f46e5"><font color="white"><b>{table}</b></font></td></tr>']
        for col in columns:
            if col in PRIMARY_KEYS[table]:
                label = f'<b>{col}</b>  <font color="#b45309">PK</font>'
            elif col in fks:
                label = f'{col}  <font color="#4f46e5">FK</font>'
            else:
                label = col
            rows.append(f'<tr><td bgcolor="white" align="left" port="{col}">{label}</td></tr>')
        lines.append(f'  {table} [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4" '
                     f'color="#c7c9d9">{"".join(rows)}</table>>];')
    for child, col, parent, parent_col in RELATIONSHIPS:
        lines.append(f"  {parent}:{parent_col} -> {child}:{col};")
    lines.append("}")
    return "\n".join(lines)


def er_diagram_mermaid():
    """The same diagram in Mermaid format (GitHub draws this automatically in the README)."""
    lines = ["erDiagram"]
    for child, col, parent, _ in RELATIONSHIPS:
        lines.append(f'    {parent} ||--o{{ {child} : "{col}"')
    for table, (_, columns) in TABLE_INFO.items():
        fks = foreign_keys(table)
        lines.append(f"    {table} {{")
        for col in columns:
            if col.endswith("_id") or col == "quantity":
                kind = "int"
            elif col.endswith("_date"):
                kind = "date"
            elif col in ("list_price", "unit_cost", "unit_price", "discount"):
                kind = "decimal"
            else:
                kind = "string"
            key = " PK" if col in PRIMARY_KEYS[table] else " FK" if col in fks else ""
            lines.append(f"        {kind} {col}{key}")
        lines.append("    }")
    return "\n".join(lines)
