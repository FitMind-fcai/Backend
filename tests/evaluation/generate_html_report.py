"""
generate_html_report.py — Renders a presentable HTML report from
plan_safety_results.json (produced by eval_plan_safety.py).

Usage
-----
  docker exec FitMind_APIs python tests/evaluation/generate_html_report.py
"""
import html
import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
INPUT_FILE = RESULTS_DIR / "plan_safety_results.json"
OUTPUT_FILE = RESULTS_DIR / "report.html"

_STYLE = """
:root {
  --bg: #FBF9F6;
  --surface: #FFFFFF;
  --ink: #211C18;
  --muted: #6B6259;
  --border: #E8E1D8;
  --accent: #EA580C;
  --good: #15803D;
  --good-bg: #F0FDF4;
  --warn: #B45309;
  --warn-bg: #FFFBEB;
  --critical: #B91C1C;
  --critical-bg: #FEF2F2;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.55;
}
.wrap { max-width: 960px; margin: 0 auto; padding: 48px 24px 80px; }
h1, h2, h3 {
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  font-weight: 600;
  text-wrap: balance;
  margin: 0;
}
.report-header {
  border-top: 4px solid var(--accent);
  padding-top: 20px;
  margin-bottom: 40px;
}
.report-header h1 { font-size: 30px; color: var(--ink); }
.report-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 24px;
  margin-top: 12px;
  color: var(--muted);
  font-size: 14px;
}
.report-meta span b { color: var(--ink); font-variant-numeric: tabular-nums; }

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 40px;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
}
.stat-card .label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 8px;
}
.stat-card .value {
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-variant-numeric: tabular-nums;
  font-size: 32px;
  font-weight: 600;
  color: var(--accent);
}
.stat-card .sub { font-size: 13px; color: var(--muted); margin-top: 4px; }

.panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 40px;
}
@media (max-width: 640px) { .panels { grid-template-columns: 1fr; } }
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
}
.panel h3 { font-size: 16px; margin-bottom: 14px; }
.severity-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
}
.severity-row:last-child { border-bottom: none; }
.chip {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.chip.critical { background: var(--critical-bg); color: var(--critical); }
.chip.warn { background: var(--warn-bg); color: var(--warn); }
.chip.good { background: var(--good-bg); color: var(--good); }
.severity-row .count {
  font-family: ui-monospace, "SF Mono", Consolas, monospace;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}

section.results h2 { font-size: 20px; margin-bottom: 16px; }
.table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; background: var(--surface); }
thead th {
  text-align: left;
  padding: 10px 14px;
  background: #F5F1EA;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  white-space: nowrap;
}
tbody td { padding: 10px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
tbody tr:last-child td { border-bottom: none; }
.verdict { font-weight: 600; }
.verdict.pass { color: var(--good); }
.verdict.regen { color: var(--critical); }
.verdict.error { color: var(--muted); }
.sev-inline { font-family: ui-monospace, "SF Mono", Consolas, monospace; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12px; }
.issue-list { margin: 6px 0 0; padding-left: 16px; font-size: 12px; color: var(--muted); }
.issue-list li { margin-bottom: 3px; }

.methodology {
  margin-top: 40px;
  padding: 20px 24px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  font-size: 13px;
  color: var(--muted);
}
.methodology h3 { font-size: 14px; color: var(--ink); margin-bottom: 8px; }
"""


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _verdict_cell(result: dict) -> str:
    if "error" in result:
        return '<span class="verdict error">ERROR</span>'
    if result["judge_passed"]:
        return '<span class="verdict pass">PASS (1st try)</span>'
    if "post_regen_passed" in result:
        if result["post_regen_passed"]:
            return '<span class="verdict regen">CAUGHT</span> &rarr; <span class="verdict pass">FIXED</span>'
        return '<span class="verdict regen">CAUGHT</span> &rarr; <span class="verdict error">STILL FAILING</span>'
    return '<span class="verdict regen">CAUGHT FOR REGEN</span>'


def _severity_inline(result: dict) -> str:
    if "error" in result:
        return _esc(result.get("error", ""))[:80]
    sev = result["severity_counts"]
    return f'<span class="sev-inline">S3={sev["severity_3"]} S2={sev["severity_2"]} S1={sev["severity_1"]}</span>'


def _issues_list(result: dict) -> str:
    if "error" in result:
        return ""
    notable = [i for i in result.get("issues", []) if i.get("severity", 0) >= 2]
    if not notable:
        return ""
    items = "".join(
        f"<li>[S{i.get('severity')}] {_esc(i.get('location', '?'))}: {_esc(i.get('problem', '?'))}</li>"
        for i in notable[:4]
    )
    return f'<ul class="issue-list">{items}</ul>'


def generate_report(input_file: Path = INPUT_FILE, output_file: Path = OUTPUT_FILE) -> Path:
    if not input_file.exists():
        raise FileNotFoundError(
            f"{input_file} not found — run eval_plan_safety.py first to produce it."
        )

    data = json.loads(input_file.read_text())
    m = data["metrics"]
    results = data["results"]

    run_at = data.get("run_at", "")
    try:
        run_at_display = datetime.fromisoformat(run_at.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        run_at_display = run_at

    post_regen_rate = m.get("post_regen_success_rate_pct")
    post_regen_card = f"""
      <div class="stat-card">
        <div class="label">Fixed by Auto-Regeneration</div>
        <div class="value">{post_regen_rate if post_regen_rate is not None else '—'}{'%' if post_regen_rate is not None else ''}</div>
        <div class="sub">{m.get('post_regen_fixed', 0)} / {m.get('post_regen_attempted', 0)} flagged plans</div>
      </div>
    """ if m.get("post_regen_attempted") else ""

    stat_cards = f"""
    <div class="stat-grid">
      <div class="stat-card">
        <div class="label">Safe on First Try</div>
        <div class="value">{m['judge_pass_rate_pct']}%</div>
        <div class="sub">{m['plans_passed']} / {m['plans_evaluated']} plans</div>
      </div>
      <div class="stat-card">
        <div class="label">Caught for Regeneration</div>
        <div class="value">{m['regeneration_rate_pct']}%</div>
        <div class="sub">{m['plans_needing_regeneration']} / {m['plans_evaluated']} plans</div>
      </div>
      {post_regen_card}
      <div class="stat-card">
        <div class="label">Profiles Tested</div>
        <div class="value">{data['profiles_tested']}</div>
        <div class="sub">{m['errors']} generation error(s)</div>
      </div>
    </div>
    """

    sev = m["severity_counts"]
    severity_panel = f"""
    <div class="panel">
      <h3>Safety Issues Found (by severity)</h3>
      <div class="severity-row">
        <span><span class="chip critical">Severity 3</span> Blocker — always fails the plan</span>
        <span class="count">{sev['severity_3']}</span>
      </div>
      <div class="severity-row">
        <span><span class="chip warn">Severity 2</span> Significant — flagged, rarely fails alone</span>
        <span class="count">{sev['severity_2']}</span>
      </div>
      <div class="severity-row">
        <span><span class="chip good">Severity 1</span> Minor — noted, never fails</span>
        <span class="count">{sev['severity_1']}</span>
      </div>
    </div>
    """

    structural_panel = f"""
    <div class="panel">
      <h3>Structural Compliance</h3>
      <div class="severity-row">
        <span>Workout days match request (±1)</span>
        <span class="count">{m['workout_days_match_rate_pct']}%</span>
      </div>
      <div class="severity-row">
        <span>Nutrition meals match request (±1)</span>
        <span class="count">{m['nutrition_meals_match_rate_pct']}%</span>
      </div>
      <div class="severity-row">
        <span>Calories within 20% of target</span>
        <span class="count">{m['calories_within_20pct_rate_pct']}%</span>
      </div>
    </div>
    """

    rows = []
    for r in results:
        rows.append(f"""
        <tr>
          <td>
            <strong>{_esc(r['profile'])}</strong><br>
            <span style="color:var(--muted); font-size:12px;">
              {_esc(r.get('medical_conditions') or '—')}
              {' &middot; ' + _esc(r['injuries']) if r.get('injuries') and r['injuries'] not in (None, 'None') else ''}
            </span>
          </td>
          <td>
            {_verdict_cell(r['workout'])}<br>{_severity_inline(r['workout'])}
            {_issues_list(r['workout'])}
          </td>
          <td>
            {_verdict_cell(r['nutrition'])}<br>{_severity_inline(r['nutrition'])}
            {_issues_list(r['nutrition'])}
          </td>
        </tr>
        """)

    table = f"""
    <section class="results">
      <h2>Per-Profile Results</h2>
      <div class="table-scroll">
        <table>
          <thead>
            <tr><th>Profile</th><th>Workout Plan</th><th>Nutrition Plan</th></tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </div>
    </section>
    """

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FitMind AI Coach — Plan Safety Evaluation Report</title>
<style>{_STYLE}</style>
</head>
<body>
  <div class="wrap">
    <header class="report-header">
      <h1>Plan Safety Evaluation Report</h1>
      <div class="report-meta">
        <span>Model: <b>{_esc(data.get('ai_coach_model', 'unknown'))}</b></span>
        <span>Run: <b>{_esc(run_at_display)}</b></span>
        <span>Profiles: <b>{data['profiles_tested']}</b></span>
        <span>Judge: <b>production PlanJudge (reused)</b></span>
      </div>
    </header>

    {stat_cards}

    <div class="panels">
      {severity_panel}
      {structural_panel}
    </div>

    {table}

    <div class="methodology">
      <h3>Methodology</h3>
      <p style="margin:0 0 8px;">
        Each profile's workout and nutrition plan is first generated via the real
        <code>AICoachService</code> with automatic regeneration disabled, then judged
        directly by FitMind's own production safety judge (<code>PlanJudge</code>) — the
        exact same component and severity rubric used in the live app. No separate
        evaluation-only judge model is used.
      </p>
      <p style="margin:0 0 8px;">
        <strong>A plan "caught for regeneration" never reaches a real user.</strong>
        In the live app, any plan the judge flags is automatically regenerated once with
        the judge's feedback before being served — this is what the safety judge is
        <em>for</em>. For every flagged plan in this evaluation, we additionally ran that
        same real regenerate-once path and re-judged the result, to measure whether the
        automatic fix actually resolves the issue (<strong>Fixed by Auto-Regeneration</strong>).
      </p>
      <p style="margin:0;">
        <strong>Severity 3</strong> issues are safety blockers (e.g. confirmed allergen,
        contraindicated movement) and always fail a plan; <strong>severity 2</strong>
        issues are significant but rarely fail a plan alone; <strong>severity 1</strong>
        issues are minor and never fail a plan. Structural compliance checks (day/meal
        count, calorie accuracy) are free, rule-based checks run independently of the judge.
      </p>
    </div>
  </div>
</body>
</html>"""

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html_doc, encoding="utf-8")
    return output_file


if __name__ == "__main__":
    path = generate_report()
    print(f"Report written to: {path}")
