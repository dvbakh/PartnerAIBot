# PartnerAIBot — multi-agent budget collection

A prototype for the coursework **"Development of multi-agent technologies in
intelligent systems: Human-Computer Interaction"**.

A Telegram bot collects advertising / partner budgets across GEOs and channels.
An **analyst** states the task in plain language; the system selects the
responsible **managers**, asks them for the figures, checks the data and
assembles a report. The agents do not merely run a pipeline — they compete for
assignments, act on deadlines and may disagree with one another.

> The user-facing bot messages are in Russian (the intended audience); the code,
> comments and this document are in English.

---

## Roles

- **Analyst (аналитик)** — states the collection task and receives the report.
- **Manager (менеджер)** — provides the budgets for a given channel.

In demo mode a single Telegram account plays both roles, so the whole cycle can
be shown by one person.

---

## How it maps to the topic

**Multi-agent part.** Autonomous agents talk over a message bus using explicit
performatives (inspired by **FIPA ACL**: `REQUEST`, `CFP`, `PROPOSE`,
`ACCEPT/REJECT`, `INFORM`, `REPORT`, `CHALLENGE`). Three genuine agent mechanisms
are implemented:

1. **Tender for an executor (Contract Net Protocol, Smith 1980).** For each
   GEO×channel subtask the coordinator announces a call for proposals (`CFP`),
   candidate managers bid (`PROPOSE`) by reliability and load, the coordinator
   awards the work to the best one (`ACCEPT`), the rest become backups.
2. **Deadline autonomy.** The assigned collector reminds the manager itself, and
   if no answer arrives the coordinator reassigns the subtask to a backup.
3. **Quality control with disagreement.** A validator agent compares the amounts
   with last month's history and disputes anomalies (`CHALLENGE`). The human then
   decides: keep the submitted value, or accept the more probable (historical)
   value the validator suggests.

**HCI part.** The interface is a natural-language dialog. The secretary runs a
**mixed-initiative** dialog (Horvitz 1999): it asks for missing fields. Disputed
data is escalated to the human — **human-in-the-loop**: every figure in the
report is confirmed by a person.

---

## Agents

| Agent | Role | What it does |
|-------|------|--------------|
| `SecretaryAgent` | analyst interface | parses month / GEO / channels / deadline, asks for missing fields |
| `CoordinatorAgent` | orchestrator | runs the tender, assigns managers, watches the deadline, reassigns to backups |
| `CollectorAgent` | executor (one per subtask) | bids in the tender, requests budgets, reminds, parses the answer, runs the dispute dialog |
| `ValidatorAgent` | quality control | compares amounts with history, disputes anomalies, suggests the more probable value |
| `ReporterAgent` | reporter | aggregates the result, writes the CSV, updates history |

Message flow:
**analyst → Secretary → (REQUEST) → Coordinator → (CFP/PROPOSE/ACCEPT) → Collectors**;
manager answer → Collector → **(REQUEST) → Validator → (INFORM | CHALLENGE)** →
Collector → **(REPORT) → Coordinator → (REQUEST) → Reporter → report to the analyst**.

---

## Stating the task (with an optional channel)

The analyst writes the task in plain Russian. GEO and deadline are required; a
channel is optional:

- `Собери бюджеты за апрель по BY, дедлайн 25.04` → all channels of BY.
- `Собери бюджеты за апрель по BY Mobile, дедлайн 25.04` → only BY/Mobile.

---

## The report and the table

The report message to the analyst has the form:

```
Отчёт по задаче за <month>.

Суммы по каналам:
<GEO> <CHANNEL>: <sum>
...

Всего партнёров: <N>
Общий бюджет: <sum>

Менеджеры, которые не отправили:
<name> (<GEO>/<CHANNEL>)
```

The exported table (`report_task_<id>.csv`, UTF-8) has the columns:

```
month (mm-dd-yyyy), GEO, Detailed (Channel), Partner, Budget
```

`month` is the first day of the month (e.g. April → `04-01-2026`; the year is the
current one, since the task carries no year).

---

## Project structure

```
PartnerAIBot/
├── main.py            # Telegram bot: interface + deadline timers (the runtime)
├── simulate.py        # full cycle without Telegram (tender, timeout, dispute, report)
├── config.py          # settings, GEO/channel/manager structure, timings
├── core/
│   ├── messages.py    # AgentMessage and performatives (FIPA ACL)
│   └── bus.py         # message bus between agents
├── agents/
│   ├── base.py        # base agent
│   ├── secretary.py   # analyst dialog (mixed-initiative)
│   ├── coordinator.py # tender (Contract Net), coordination, reassignment
│   ├── collector.py   # bid, collect, remind, dispute dialog
│   ├── validator.py   # anomaly check and dispute
│   └── reporter.py    # aggregation, CSV export, history update
├── nlu/extractor.py   # NLU: LLM + offline rule-based parser
├── storage/           # SQLite: schema, repositories, last-month history
└── models/task.py     # task model
```

---

## Install and run

```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # set TELEGRAM_TOKEN and ANALYST_CHAT_ID
python main.py
```

Find your `chat_id` via `@userinfobot`.

### Quick check without Telegram

```bash
python simulate.py
```

Shows the tender, the deadline reassignment, the dispute (with the more-probable
value assigned) and the report in the console.

---

## Single-account demonstration

1. `/start` → **Аналитик**.
2. Type: `Собери бюджеты за апрель по BY, дедлайн 25.04`
   (add a channel to target it, e.g. `по BY Mobile`).
   The bot runs the tender and messages the managers.
3. (optional) `/timeout` — simulate a missed deadline for the current request and
   see the reassignment to a backup.
4. **Менеджеры** → pick a specific manager from the inline buttons, then send the
   list, e.g.:
   ```
   Google 1000
   Meta 9000
   ```
   If a sum differs sharply from last month, the bot asks: `да` keeps your value,
   `нет` accepts the more probable one, or send a corrected list.
5. Once all subtasks are closed the analyst receives the report and a CSV.

`/reset` — clear data and restore history; `/status` — current status.

---

## Settings (`.env` / `config.py`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `USE_LLM` | `false` | `false` — offline rule-based NLU (robust for the defense); `true` — via Mistral |
| `USE_PROXY` | `true` | use a SOCKS5 proxy for Telegram |
| `PROXY_URL` | `socks5://127.0.0.1:10808` | proxy address |
| `REMINDER_AFTER_SEC` / `ESCALATE_AFTER_SEC` | `60` / `120` | when to remind and to reassign (seconds, for the demo) |
| `ANOMALY_THRESHOLD` | `0.5` | deviation from last month that triggers a dispute (0.5 = 50%) |
| `COLLECTOR_MAX_RETRIES` | `2` | how many times to re-ask on an unparsable answer |

**NLU with a fallback.** When the LLM is off/unavailable, `nlu/extractor.py`
switches to a deterministic parser, so the prototype runs locally with no API.

---

## Security

No real tokens are stored in the code: everything comes from `.env` (in
`.gitignore`). The defaults in `config.py` are invalid placeholders.

---

## Prototype limitations

- Agent state lives in the process memory; tasks/collectors/budgets/history live
  in SQLite. After a restart a collector is recreated lazily from the DB, but the
  pending-subtask counters are restored approximately.
- The tender uses a simple bid function (reliability minus load); the rule-based
  parser expects simple formats (one partner per line); the "more probable" value
  is last month's figure.
- This is a local educational prototype, not a production system.
