---
name: new-endpoint
description: Step-by-step checklist for adding a new FastAPI endpoint with Pydantic validation, parameterized SQL, security headers, and automated tests.
---

# Adding a New FastAPI Endpoint

When the user asks you to add a new web endpoint to any FastAPI app in this repository, follow these 4 steps in order:

1. **Define the Pydantic Request & Response Models**:
   - Create a `BaseModel` class with explicit `Field(...)` constraints (e.g., `min_length`, `max_length`, `gt=0`).
   - Add a `@field_validator` if custom business rules apply.

2. **Use Parameterized Database Queries**:
   - Never use Python `f"SELECT ... {user_input}"` in SQL queries.
   - Always pass parameters as a tuple (`cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))`).

3. **Return Clear HTTP Status Codes & Security Headers**:
   - Return `201 Created` when creating a record, `400 Bad Request` or `422 Unprocessable Entity` for invalid inputs, `404 Not Found` for missing records, and `409 Conflict` when capacity or uniqueness rules fail.

4. **Write Two Automated Tests**:
   - Write at least one **happy-path test** (valid request returns expected JSON).
   - Write at least one **failure-path test** (invalid or duplicate data is rejected cleanly without crashing).
