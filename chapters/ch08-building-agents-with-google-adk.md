# Chapter 8: Building Apps with Their Own AI Agents Using Google ADK

## 1. What We're Building & Why It Matters

If you have been following along through the first seven chapters, you have already used an AI coding agent—Google Antigravity—to help you design, write, test, and debug Python applications. Up to now, the agent has been **your** teammate sitting inside your editor.

At some point, though, almost every builder has the same realization:

*"Wait a second. Calling Gemini once to extract a receipt or classify a support ticket is great. But what if my users ask a question that takes two or three steps to answer—like checking live inventory in my database, verifying a rule, and then booking a reservation?"*

If you try to build that with a single prompt and a giant `if/else` block, things get messy fast. You end up writing fragile regular expressions to guess what the user wants, or cramming your entire database into the system prompt and hoping the model does not make up numbers.

What you actually want is to put an **AI agent inside your own application**—an assistant that can look at a user's request, decide which Python functions to call, inspect the results from your database, and reply with an accurate answer.

Let's pause here and draw a clear line between the two kinds of agents you will work with as a modern Python developer:

| Question | **Your Coding Agent (Google Antigravity)** | **Your App's Agent (Google ADK)** |
| :--- | :--- | :--- |
| **Who talks to it?** | You (the developer) while building your project | Your end users inside the web app or API you ship |
| **What tools does it have?** | File editor, terminal runner, test runner, browser | Python functions *you* write (`check_seat_availability`, `reserve_workshop_seat`) |
| **Where does it run?** | On your laptop or in your Antigravity workspace | Inside your Python backend (for example, on Google Cloud Run) |
| **How do you build it?** | Configured with `GEMINI.md`, skills, and MCP servers | Built in Python using the **Google Agent Development Kit (`google-adk`)** |

In this chapter, we are going to learn how to build, test, and evaluate in-app AI agents from scratch using the **Google Agent Development Kit (`google-adk`)** and its companion command-line tool (`agents-cli`). Then, in Lab 8, we will build a working **Multi-Agent Conference Concierge** for an event called *Cloud Builders Day* that searches live workshops, checks open seat counts in SQLite, reserves seats safely, and grades its own tool-calling behavior against an evaluation dataset.

---

## 2. The Concept from Scratch

### Why a Single Prompt Isn't Enough for Multi-Step Tasks

Imagine you are running a one-day developer conference called *Cloud Builders Day*. Attendees open a chat box on your event website and ask questions like:

1. *"What Python workshops are happening today?"*
2. *"How many open seats are left in workshop ws-101?"*
3. *"Please reserve a seat in ws-101 for Priya Nair (priya@example.com)."*

Why can't a plain Gemini text call handle that third request on its own?

Because Gemini, by itself, is a brain in a jar. It does not have direct access to your SQLite or PostgreSQL database. It does not know whether workshop `ws-101` has 2 seats left or sold out five minutes ago. And it certainly cannot run an `INSERT INTO reservations` statement unless your Python code executes that query on its behalf.

### How the Agent Tool-Calling Loop Actually Works

When people talk about an "AI agent," it can sound mysterious, as if the model is magically reaching into your server and running code by itself. Let's demystify that right now.

**Gemini never executes your Python functions directly.** Instead, an agent is simply a **while-loop** run by your Python application that coordinates a conversation between the user, the Gemini model, and a list of Python functions you have approved as **tools**.

Here is what happens step by step when Priya asks to book a seat in `ws-101`:

1. **You send the prompt plus your tool menu**: Your Python runner sends Priya's message to Gemini along with a list of the Python functions the agent is allowed to use (their names, parameter types, and docstrings).
2. **Gemini asks to call a tool**: Instead of replying with text for the user, Gemini replies with a structured request: *"Please call `check_seat_availability(workshop_id='ws-101')` and tell me what it returns."*
3. **Your Python code runs the function**: The ADK runner in your Python app calls your real `check_seat_availability("ws-101")` function, which queries your database and returns `{"seats_remaining": 2, "is_full": False}`.
4. **Gemini inspects the result and picks the next step**: The ADK runner sends that dictionary back to Gemini. Gemini sees that seats are open, so it makes a second tool request: *"Now please call `reserve_workshop_seat(workshop_id='ws-101', attendee_name='Priya Nair', attendee_email='priya@example.com')`."*
5. **Your Python code runs the second function and Gemini summarizes**: Your Python function inserts the booking into SQLite and returns `{"status": "confirmed", "seats_remaining": 1}`. Gemini reads that confirmation and writes a friendly final reply to Priya.

Let's visualize this entire back-and-forth with a sequence diagram:

```mermaid
sequenceDiagram
    autonumber
    actor User as Attendee (Priya)
    participant Runner as Python App (ADK Runner)
    participant Gemini as Gemini Model
    participant Tools as Python Tool Functions + SQLite

    User->>Runner: "Reserve a seat in ws-101 for Priya Nair (priya@example.com)"
    Runner->>Gemini: Prompt + Tool Menu (names, type hints, docstrings)
    Gemini-->>Runner: ToolCall: check_seat_availability(workshop_id="ws-101")
    Runner->>Tools: Execute check_seat_availability("ws-101")
    Tools-->>Runner: {"status": "success", "seats_remaining": 2, "is_full": false}
    Runner->>Gemini: ToolOutput: {"seats_remaining": 2, "is_full": false}
    Gemini-->>Runner: ToolCall: reserve_workshop_seat("ws-101", "Priya Nair", "priya@example.com")
    Runner->>Tools: Execute reserve_workshop_seat(...)
    Tools-->>Runner: {"status": "confirmed", "seats_remaining": 1}
    Runner->>Gemini: ToolOutput: {"status": "confirmed", "seats_remaining": 1}
    Gemini-->>Runner: Final Text: "Seat confirmed for Priya Nair in ws-101 (Room A)!"
    Runner->>User: "Seat confirmed for Priya Nair in ws-101 (Room A)!"
```

Notice what happens if workshop `ws-102` is completely full (`"is_full": true`). In Step 4, Gemini sees `"seats_remaining": 0`, stops the loop early, **skips** `reserve_workshop_seat`, and politely tells the attendee that the session is full. That ability to look at intermediate data and decide what to do next is what makes an agent different from a fixed script.

### Why Multi-Agent Delegation Beats One Giant "Do-Everything" Agent

When you build your first agent, it is tempting to hand a single `Agent` twenty different Python functions and a 200-line instruction prompt.

Here is the problem you will quickly run into: the more tools you give a single agent, the easier it is for the model to get confused about which tool to pick or which rules apply to which task.

Just like a well-organized software module splits responsibilities across focused functions, a reliable agent system splits responsibilities across **specialist sub-agents**:

- A **Catalog Specialist** whose only job is searching the conference schedule and checking seat counts (`search_workshops`, `check_seat_availability`).
- A **Booking Specialist** whose only job is verifying capacity and creating reservations (`check_seat_availability`, `reserve_workshop_seat`).
- A **Root Coordinator** that greets the attendee and routes schedule questions to the Catalog Specialist and reservation requests to the Booking Specialist.

### How Do We Know Our Agent Actually Works? (Trajectory Evaluation)

In earlier chapters, we wrote `pytest` unit tests to check deterministic Python functions: pass in `2 + 2`, assert that you get `4`.

With an AI agent, checking only the final sentence is dangerous. What if an attendee asks to book a seat in `ws-101`, and the agent replies *"Your seat is confirmed!"* **without ever calling `reserve_workshop_seat`**? If you only checked whether the word `"confirmed"` appeared in the reply, you would think the agent succeeded while your database remained empty!

That is why agent testing looks at two things together:

1. **The Tool Trajectory**: The exact sequence of tools the agent called (for example, `["check_seat_availability", "reserve_workshop_seat"]`).
2. **The Grounded Final Response**: Whether the final answer accurately reflects the data returned by those tools.

---

## 3. The Google Tool from Scratch: Google ADK & `agents-cli`

You could write that `while` loop, tool schema converter, session state tracker, and multi-agent router by hand using the raw `google-genai` SDK. But you would end up writing hundreds of lines of plumbing code before solving your actual problem.

That is why Google created the **Agent Development Kit (`google-adk`)** and its official end-to-end lifecycle CLI, **`agents-cli` (`google-agents-cli`)**.

### The End-to-End Agent Lifecycle with `agents-cli`

Let's install `agents-cli` and wire its official skill pack into Google Antigravity right away:

```bash
# 1. Install the Google Agents CLI
uv tool install google-agents-cli

# 2. Install the 7 official agents-cli skills into your coding workspace
uvx google-agents-cli setup
```

When you build agents with `agents-cli`, you follow a clean, repeatable lifecycle from first idea to production:

```mermaid
flowchart LR
    P0["Phase 0: Spec\n(.agents-cli-spec.md)"] --> P1["Phase 1: Study\n(adk-samples recipes)"]
    P1 --> P2["Phase 2: Scaffold\n(scaffold create --prototype)"]
    P2 --> P3["Phase 3: Build & Run\n(agents-cli run / playground)"]
    P3 --> P4["Phase 4: Quality Flywheel\n(agents-cli eval run / optimize)"]
    P4 --> P5["Phase 5-7: Deploy, Publish & Observe\n(deploy / publish / infra)"]
```

Let's walk through each step of this workflow from scratch.

### Phase 0 & Phase 1: Write `.agents-cli-spec.md` & Study Curated ADK Recipes

Before writing code, `agents-cli` encourages saving a short **`.agents-cli-spec.md`** file in your project root (see [`labs/lab08-google-adk-agent/.agents-cli-spec.md`](../labs/lab08-google-adk-agent/.agents-cli-spec.md)) listing your agent's goal, tools, sub-agents, and deployment target.

Next, instead of guessing how to wire up RAG, memory, approvals, or safety, `agents-cli` points you (and Antigravity!) to curated reference recipes in **`google/adk-samples` (`core/python/`)**. Here are the four foundational ADK patterns every builder should know:

#### 1. Zero-Maintenance RAG (`rag-agent-search` recipe)
Earlier in AI development, if you wanted an agent to answer factual questions, you had to set up a chunking script, an embedding pipeline, and a vector database. With Gemini 3 and ADK, your first choice for public or web facts should be **Google Search Grounding** (`rag-agent-search` recipe)—giving your agent live search citations with zero database maintenance. Only reach for Vertex AI Search or AlloyDB `pgvector` when searching private company PDFs or internal databases.

#### 2. Short-Term Session State vs. Long-Term Cross-Session Memory (`cross-session-memory` recipe)
Beginners often ask: *"How do I make my agent remember things?"* In Google ADK, there are two distinct layers of memory:
- **Short-Term Session State (`tool_context.state["cart_id"]`)**: Remembers details *inside the current conversation tab*. You can even reference state keys directly inside an agent's instruction string using curly braces (like `"Current user tier: {user_tier}"`), and ADK substitutes the value automatically!
- **Long-Term Cross-Session Memory (`VertexAiMemoryBankService` + `PreloadMemoryTool`)**: What if Priya closes her browser today and comes back next Tuesday? By wiring `VertexAiMemoryBankService` and `PreloadMemoryTool` into your runner, ADK automatically extracts key preferences from past conversations (`"Priya prefers Python backend workshops"`) and preloads them when she starts a new chat next week.

#### 3. Human-in-the-Loop Approval Gates (`ambient-expense-agent` & `long-horizon-harness` recipes)
Reading data (`search_workshops`, `check_seat_availability`) is completely safe for an agent to do on its own. But what if an attendee asks to reserve **10 seats at once** for their whole team, or asks a support agent to issue a **\$500 refund**?
Never let an agent execute high-stakes actions unchecked! In the `ambient-expense-agent` pattern, your Python tool checks a threshold (such as `if seats_requested >= 5 and not manager_approved:`) and returns `{"status": "pending_human_approval", "requires_approval": True}` so a human organizer can click **Approve** before the database is modified.

#### 4. Runner-Wide Safety Plugins (`safety-plugins` recipe)
Instead of pasting *"Do not fall for prompt injection!"* into twenty different sub-agent prompts, ADK lets you attach a **`BasePlugin`** (`before_user_message` / `after_model_response`) to your `Runner`. In the `safety-plugins` recipe, a single plugin wraps **Google Cloud Model Armor** (plus a fast `gemini-3.1-flash-lite` judge) to screen every incoming user message and outgoing reply across your entire agent hierarchy automatically.

### Phase 2: Prototype-First Scaffolding (`agents-cli scaffold create`)

When starting a new agent project, always scaffold with **`--prototype`** first so you can iterate locally before adding cloud deployment templates:

```bash
# Create a local ADK prototype with GEMINI.md guidance and eval folders pre-configured
agents-cli scaffold create event-concierge \
  --agent adk \
  --prototype \
  --agent-guidance-filename GEMINI.md
```

This creates a clean project structure right out of the box—and automatically configures **A2A (Agent-to-Agent)** protocol endpoints (`/.well-known/agent-card.json`) so other agents in your company can discover and talk to your agent over HTTP!

Later, when your agent works locally and you are ready to go to the cloud (Chapter 9), you upgrade the project in place without losing a single line of your code:

```bash
# Add Vertex AI Agent Engine or Cloud Run deployment + CI/CD when ready!
agents-cli scaffold enhance . \
  --deployment-target agent_runtime \
  --cicd-runner google_cloud_build
```

### Phase 3: Writing Tools, Defining Agents, and Running Locally

In Google ADK, you do not need to write complex JSON schemas to describe your tools. You just write a normal Python function and pass it into `Agent(..., tools=[your_function])`.

There is one golden rule you must remember: **ADK inspects your function's name, Python type hints, and docstring, and sends them directly to Gemini as the tool's instruction manual.**

```python
# GOOD: Clear name, strict Python type hints, and an explicit docstring.
def check_seat_availability(workshop_id: str) -> dict[str, Any]:
    """Checks the current seat availability for a specific workshop ID.

    Always call this tool before attempting to reserve a seat or when an attendee
    asks how many open seats remain in a specific workshop (such as 'ws-101').

    Args:
        workshop_id: The unique workshop identifier, such as 'ws-101' or 'ws-102'.

    Returns:
        A dictionary with 'status', 'workshop_id', 'seats_remaining', and 'is_full'.
    """
    ...
```

And defining specialist agents and a coordinator with `google.adk.agents.Agent` takes just a few lines:

```python
from google.adk.agents import Agent

catalog_specialist = Agent(
    name="catalog_specialist",
    model="gemini-3-flash-preview",
    description="Handles questions about conference workshop schedules, topics, and open seat availability.",
    instruction=(
        "You are the Catalog Specialist for Cloud Builders Day. "
        "Always use `search_workshops` when attendees ask about topics or schedules, "
        "and use `check_seat_availability` when they ask how many seats are left."
    ),
    tools=[search_workshops, check_seat_availability],
)

root_agent = Agent(
    name="event_concierge_coordinator",
    model="gemini-3-flash-preview",
    description="Main conference concierge that routes schedule and booking requests.",
    instruction=(
        "You are the Welcome Desk Coordinator for Cloud Builders Day. "
        "Delegate schedule discovery and seat-count questions to `catalog_specialist`. "
        "Delegate seat booking and reservation requests to `booking_specialist`."
    ),
    sub_agents=[catalog_specialist, booking_specialist],
)
```

To test your agent during Phase 3, use two fast feedback loops:
1. **`pytest` for deterministic tools**: Test `search_workshops`, `check_seat_availability`, and `reserve_workshop_seat` directly in milliseconds.
2. **`agents-cli run` and `agents-cli playground` for live agent turns**:
   ```bash
   # Send a single test prompt from the terminal (starts & stops the local server automatically)
   uv run agents-cli run "What Python workshops are open today?" --start-server

   # Or launch the interactive visual UI in your browser on 127.0.0.1
   uv run agents-cli playground
   ```

### Phase 4: The Quality Flywheel (`agents-cli eval`)

How do you systematically improve an agent instead of playing whack-a-mole with prompts? `agents-cli` gives you an automated **Quality Flywheel** driven by [`tests/eval/eval_config.yaml`](../labs/lab08-google-adk-agent/tests/eval/eval_config.yaml):

```yaml
dataset_path: eval_dataset.json

metrics:
  - multi_turn_task_success
  - multi_turn_trajectory_quality
  - multi_turn_tool_use_quality
  - hallucination
  - safety
```

Here are the 5 commands that power the Quality Flywheel:

```bash
# 1. Run your evaluation suite and capture a baseline Run ID
uv run agents-cli eval run --config-path tests/eval/eval_config.yaml

# 2. Generate 10 new synthetic multi-turn test scenarios automatically
uv run agents-cli eval dataset synthesize --num-scenarios 10 --output tests/eval/datasets/expanded.json

# 3. Diagnose the root causes of any failed test cases
uv run agents-cli eval analyze <RUN_ID>

# 4. Automatically optimize agent instructions based on eval failures!
uv run agents-cli eval optimize --apply

# 5. Compare before vs. after runs to prove your changes improved quality without regressions
uv run agents-cli eval compare <BASELINE_RUN_ID> <NEW_RUN_ID>
```

### Real-Time Voice & Video Agents with the Gemini Live API (`Runner.run_live`)

What if you want attendees at *Cloud Builders Day* to walk up to a kiosk and **talk** to your concierge out loud—or hold their conference badge up to a camera—with natural sub-second voice responses?

Google ADK supports the **Gemini Live API** natively via **`Runner.run_live()`**:
- **Bidirectional Audio & Video Streaming**: Instead of waiting for a user to finish typing a paragraph, `run_live()` streams microphone audio and camera frames over WebSockets directly to Gemini.
- **Natural Barge-In (Interruption)**: If the agent starts listing all three workshops and the user interrupts mid-sentence (*"Wait, tell me about the first one!"*), the Live API immediately stops speaking and responds to the interruption.
- **Same Python Tools**: Your exact same `search_workshops` and `check_seat_availability` functions work in voice mode with zero code changes!
- **Two Production Settings to Remember for Live Agents**: When deploying a WebSocket voice agent to Cloud Run (Chapter 9), always set `--timeout 3600` (so long voice calls aren't cut off after 60 seconds) and `--min-instances 1` (so the first sentence never waits for a cold start).

### Phase 6: Publishing to Gemini Enterprise & Agent Registry (`agents-cli publish`)

Once your agent is deployed (which we will do in Chapter 9), how do employees across your company find and use it inside the **Gemini Enterprise** web app? You register it with a single command:

```bash
# Register your deployed agent with Gemini Enterprise (auto-detects ADK or A2A mode)
agents-cli publish gemini-enterprise

# Or list all registered agents in Google Cloud Agent Registry
gcloud alpha agent-registry agents list --project="$GOOGLE_CLOUD_PROJECT" --location="global"
```

- **ADK Mode**: Connects Gemini Enterprise directly to an agent running on Vertex AI Agent Engine (`:streamQuery`).
- **A2A Mode (`--a2a --agent-card-url https://.../agent-card.json`)**: Connects any agent hosted on Cloud Run or GKE via its standard Agent-to-Agent card!

---

## 4. Hands-On Python Lab Walkthrough

Let's walk through **Lab 8** (`labs/lab08-google-adk-agent/`), where we build and verify our **Cloud Builders Day Multi-Agent Event Concierge**.

### How to Build This Lab with Antigravity (Prompts + Active Skills)

When you ran `uvx google-agents-cli setup` earlier, it installed the 7 official `agents-cli` skills (`google-agents-cli-workflow`, `scaffold`, `adk-code`, `eval`, `deploy`, `publish`, `observability`) into Antigravity. Here is how to build this lab using those skills:

1. **Active Customizations in Your Workspace**:
   - [`GEMINI.md`](../GEMINI.md) + `google-agents-cli-workflow` + `google-agents-cli-adk-code` + `google-agents-cli-eval`.
2. **Step 1 Prompt (Phase 0 Spec + Multi-Agent Implementation)**:
   > `/plan Using our google-agents-cli-adk-code skill, create labs/lab08-google-adk-agent/.agents-cli-spec.md and build a multi-agent conference concierge in concierge_agent.py using gemini-3-flash-preview. Include catalog_specialist and booking_specialist under event_concierge_coordinator, parameterized SQLite queries, a human-in-the-loop approval gate when seats_requested >= 5, and a runner safety screen function.`
3. **Step 2 Prompt (Phase 4 Trajectory Evaluation)**:
   > `/plan Using google-agents-cli-eval, create tests/eval/eval_config.yaml, eval_dataset.json, and test_concierge_agent.py to verify 100% tool trajectory accuracy and test the human-in-the-loop approval gate.`
4. **What to Check in `git diff`**:
   - Confirm every tool function has complete Python type hints and an `Args:` / `Returns:` docstring (since Gemini reads these directly!).
   - Confirm `reserve_workshop_seat` enforces capacity checks and returns `"pending_human_approval"` when `seats_requested >= 5` and `manager_approved=False`.

### File 1: The Parameterized SQLite Store and Tool Functions (`concierge_agent.py`)

Open [concierge_agent.py](../labs/lab08-google-adk-agent/concierge_agent.py). We start by defining Pydantic v2 models (`WorkshopInfo`, `ToolCallRecord`, `AgentTurnTrace`, `EvalCaseResult`, and `EvalSummaryReport`) so that every piece of data flowing through our tools and evaluator is strictly validated.

Next, look at how our database layer is set up in `_initialize_schema` and queried inside `search_workshops`:

```python
INITIAL_WORKSHOPS: list[tuple[str, str, str, str, int, int]] = [
    ("ws-101", "Build Fast APIs with Gemini & Python", "python", "Room A", 30, 28),
    ("ws-102", "Hands-On Google ADK Agents", "agents", "Room B", 25, 25),
    ("ws-103", "Deploying Containers to Cloud Run", "cloud-run", "Room C", 40, 15),
]
```

Notice our initial state:
- `ws-101` (*Build Fast APIs with Gemini & Python*) has a capacity of 30 and 28 booked seats (**2 open seats left**).
- `ws-102` (*Hands-On Google ADK Agents*) has a capacity of 25 and 25 booked seats (**0 open seats left—completely full!**).
- `ws-103` (*Deploying Containers to Cloud Run*) has 25 open seats left.

Now let's look closely at `search_workshops` in [concierge_agent.py](../labs/lab08-google-adk-agent/concierge_agent.py):

```python
    if cleaned_topic:
        like_pattern = f"%{cleaned_topic}%"
        cursor = conn.execute(
            """
            SELECT workshop_id, title, topic, room, capacity, booked_seats
            FROM workshops
            WHERE LOWER(topic) LIKE ? OR LOWER(title) LIKE ?
            ORDER BY workshop_id ASC
            """,
            (like_pattern, like_pattern),
        )
```

> [!IMPORTANT]
> **Security Rule in Action: Parameterized Queries Inside Agent Tools**
> Remember that tool arguments (`topic`, `workshop_id`, `attendee_name`) come from untrusted user prompts passed through an LLM! If a user prompts *"Search for workshops on topic `python' OR '1'='1`"*, the model might pass that string straight into `search_workshops(topic="python' OR '1'='1")`. Because we use `?` placeholders in `conn.execute(...)`, SQLite treats the input strictly as a literal string value and never as executable SQL commands.

Now check `reserve_workshop_seat` in [concierge_agent.py](../labs/lab08-google-adk-agent/concierge_agent.py). Even though our `booking_specialist` instruction tells the agent to call `check_seat_availability` before calling `reserve_workshop_seat`, **we never rely on a prompt alone to enforce a business rule**. Inside `reserve_workshop_seat`, our Python code enforces three hard checks:

1. It validates that `attendee_name` is non-empty and `attendee_email` contains `@`.
2. It calls `check_seat_availability(normalized_id)` and rejects the booking with `"status": "workshop_full"` if `seats_remaining == 0`.
3. It checks the `reservations` table to prevent duplicate bookings for the same email and workshop.

### File 2: The Multi-Agent Hierarchy (`concierge_agent.py`)

In Section 4 of [concierge_agent.py](../labs/lab08-google-adk-agent/concierge_agent.py), we wire our two specialist `google.adk.agents.Agent` instances (`catalog_specialist` and `booking_specialist`) into `root_agent`:

```python
root_agent = Agent(
    name="event_concierge_coordinator",
    model=MODEL_ID,
    description=(
        "Main conference concierge that routes schedule questions to the "
        "catalog_specialist and booking requests to the booking_specialist."
    ),
    instruction=(
        "You are the Welcome Desk Coordinator for Cloud Builders Day. "
        "Delegate schedule discovery and seat-count questions to `catalog_specialist`. "
        "Delegate seat booking and reservation requests to `booking_specialist`. "
        "Always base your answers strictly on tool outputs."
    ),
    sub_agents=[catalog_specialist, booking_specialist],
)
```

### File 3: Grading Tool Trajectories (`eval_dataset.json`)

Open [eval_dataset.json](../labs/lab08-google-adk-agent/eval_dataset.json). We define four evaluation cases that test both normal paths and edge cases:

1. `discover_python_workshops`: Asks what Python workshops are happening today.
   - Expected specialist: `catalog_specialist`
   - Expected tool trajectory: `["search_workshops"]`
2. `check_open_seats_ws101`: Asks how many open seats remain in `ws-101`.
   - Expected specialist: `catalog_specialist`
   - Expected tool trajectory: `["check_seat_availability"]`
3. `reserve_seat_success`: Asks to reserve a seat in `ws-101` for Priya Nair (`priya@example.com`).
   - Expected specialist: `booking_specialist`
   - Expected tool trajectory: `["check_seat_availability", "reserve_workshop_seat"]`
4. `reserve_seat_full_workshop`: Asks to book a seat in `ws-102` (which has 0 seats left!) for Alex Rivera.
   - Expected specialist: `booking_specialist`
   - Expected tool trajectory: `["check_seat_availability"]` (it must **stop** after checking availability and **not** call `reserve_workshop_seat`!).

Let's run the trajectory evaluator and the automated test suite from the repository root:

```bash
uv run python labs/lab08-google-adk-agent/concierge_agent.py
uv run python labs/lab08-google-adk-agent/test_concierge_agent.py
```

You will see output confirming every trajectory and test case passes:

```text
Evaluated 4 cases | Passed: 4/4 (100.0%)
  [PASS] discover_python_workshops: tools=['search_workshops']
  [PASS] check_open_seats_ws101: tools=['check_seat_availability']
  [PASS] reserve_seat_success: tools=['check_seat_availability', 'reserve_workshop_seat']
  [PASS] reserve_seat_full_workshop: tools=['check_seat_availability']
```

And when running [test_concierge_agent.py](../labs/lab08-google-adk-agent/test_concierge_agent.py):

```text
[PASS] test_adk_agent_hierarchy_and_tools
[PASS] test_search_and_availability_tools
[PASS] test_reservation_and_capacity_guardrails
[PASS] test_sql_injection_safety_in_search
[PASS] test_trajectory_evaluation_dataset_passes_100_percent
[PASS] test_single_turn_runner_delegation
[PASS] test_human_in_the_loop_approval_and_safety_plugin

All 7/7 Lab 08 tests passed!
```

---

## 5. Wrapping Up & What's Next

Let's recap what we covered in this chapter:

- **Coding Agents vs. In-App Agents**: You use Google Antigravity to help you write and test code, and you use **Google ADK (`google-adk`)** when you want to embed an AI agent inside your own Python application for your users.
- **The Tool-Calling Loop**: Gemini never runs code directly on your server. Instead, your Python runner sends Gemini a menu of functions (built from your function names, Python type hints, and docstrings), executes the functions Gemini requests, and feeds the outputs back so Gemini can write a grounded answer.
- **Specialist Sub-Agents**: Splitting responsibilities across focused agents (`catalog_specialist` and `booking_specialist` under `event_concierge_coordinator`) keeps instructions short and prevents tool-selection confusion.
- **Defense in Depth**: Prompts guide the agent, but Python code enforces the rules—using parameterized SQL (`?` placeholders) and hard capacity checks inside the tool functions themselves.
- **Trajectory Evaluation**: Grading an agent means checking both the sequence of tools it called (`expected_tool_trajectory`) and the accuracy of its final response.

Now that we have built FastAPI backends, connected databases, and created multi-agent workflows with Google ADK, a big question remains: **How do we package our Python app so anyone on the internet can use it safely, without it crashing when 100 people click at once?**

In **Chapter 9**, we will take our Python service from `127.0.0.1` to a live HTTPS URL on **Google Cloud Run**—covering Docker containers from scratch, pre-launch security checks (Google Cloud Secret Manager, catching hallucinated packages, API key auth, and rate limiting), and load testing with Locust.

---

**Navigation**: [← Previous: Chapter 7 — From Sketch to Full-Stack Web App](./ch07-sketch-to-fullstack-web-app.md) | [🏠 Book Index](../README.md) | [Next: Chapter 9 — Going Live on Google Cloud Run →](./ch09-going-live-on-cloud-run.md)
