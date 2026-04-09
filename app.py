from flask import Flask, request, jsonify, session
from flask_cors import CORS
import sqlite3
import hashlib
import json
import os

app = Flask(__name__)
app.secret_key = "finwise_secret_2024"
CORS(app, supports_credentials=True, origins=["*"])

DB_PATH = "finwise.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS financial_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            profile_data TEXT NOT NULL,
            analyzed_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS advice_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            advice_type TEXT NOT NULL,
            advice_content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)

init_db()

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def current_user_id():
    return session.get("user_id")

# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not name or not email or not password:
        return jsonify({"error": "All fields required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                         (name, email, hash_password(password)))
        return jsonify({"message": "Account created successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email=? AND password_hash=?",
                            (email, hash_password(password))).fetchone()
    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    session["user_id"] = user["id"]
    return jsonify({"message": "Login successful", "name": user["name"], "id": user["id"]})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})

@app.route("/api/me", methods=["GET"])
def me():
    uid = current_user_id()
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    with get_db() as conn:
        user = conn.execute("SELECT id, name, email, created_at FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(dict(user))

# ── PROFILE ───────────────────────────────────────────────────────────────────

@app.route("/api/profile", methods=["POST"])
def save_profile():
    uid = current_user_id()
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    profile = request.json
    with get_db() as conn:
        conn.execute("""
            INSERT INTO financial_profiles (user_id, profile_data, analyzed_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                profile_data=excluded.profile_data,
                analyzed_at=excluded.analyzed_at
        """, (uid, json.dumps(profile)))
    return jsonify({"message": "Profile saved"})

@app.route("/api/profile", methods=["GET"])
def get_profile():
    uid = current_user_id()
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    with get_db() as conn:
        row = conn.execute("SELECT profile_data FROM financial_profiles WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"profile": None})
    return jsonify({"profile": json.loads(row["profile_data"])})

# ── ADVICE ENGINE (Rule-Based) ────────────────────────────────────────────────

def generate_financial_advice(p):
    income = float(p.get("monthly_income", 0))
    expenses = float(p.get("monthly_expenses", 0))
    savings = float(p.get("monthly_savings", 0))
    current_savings = float(p.get("current_savings", 0))
    debt = float(p.get("total_debt", 0))
    age = int(p.get("age", 30))
    dependents = int(p.get("dependents", 0))
    risk = p.get("risk_tolerance", "moderate")
    goal = p.get("primary_goal", "wealth_building")
    country = p.get("country", "USA")

    savings_rate = (savings / income * 100) if income > 0 else 0
    debt_to_income = (debt / (income * 12)) if income > 0 else 0
    emergency_fund_needed = expenses * 6
    emergency_fund_months = (current_savings / expenses) if expenses > 0 else 0

    score = 50
    if savings_rate >= 20: score += 15
    elif savings_rate >= 10: score += 8
    if debt_to_income < 0.3: score += 10
    elif debt_to_income > 1.0: score -= 15
    if emergency_fund_months >= 6: score += 10
    elif emergency_fund_months >= 3: score += 5
    if age < 35: score += 5
    score = max(0, min(100, score))

    advice = f"""## 💼 Overall Financial Health Score: {score}/100

Your financial health score is **{score}/100** — {'Excellent' if score>=80 else 'Good' if score>=60 else 'Fair' if score>=40 else 'Needs Improvement'}.

---

## 📊 Financial Snapshot

| Metric | Your Value | Benchmark | Status |
|--------|-----------|-----------|--------|
| Monthly Income | ${income:,.0f} | — | — |
| Monthly Expenses | ${expenses:,.0f} | <80% income | {'✅ Good' if expenses < income*0.8 else '⚠️ High'} |
| Savings Rate | {savings_rate:.1f}% | ≥20% | {'✅ Excellent' if savings_rate>=20 else '⚠️ Below Target'} |
| Emergency Fund | {emergency_fund_months:.1f} months | 6 months | {'✅ Good' if emergency_fund_months>=6 else '⚠️ Build Up'} |
| Debt-to-Income | {debt_to_income:.2f}x | <0.3x | {'✅ Healthy' if debt_to_income<0.3 else '⚠️ High'} |

---

## 🎯 Top 5 Recommendations

**1. {'Build Emergency Fund' if emergency_fund_months < 6 else 'Maintain Emergency Fund'}**
{'You need $' + f"{emergency_fund_needed - current_savings:,.0f}" + ' more to reach a 6-month emergency fund ($' + f"{emergency_fund_needed:,.0f}" + ' total). Save $' + f"{(emergency_fund_needed - current_savings)/12:,.0f}" + '/month for the next 12 months.' if emergency_fund_months < 6 else 'Your emergency fund is healthy. Keep $' + f"{emergency_fund_needed:,.0f}" + ' accessible in a high-yield savings account.'}

**2. {'Reduce Debt Aggressively' if debt > 0 else 'Stay Debt-Free'}**
{'With $' + f"{debt:,.0f}" + ' in debt and a ' + f"{debt_to_income:.1f}x" + ' debt-to-income ratio, focus on the highest-interest debt first (avalanche method). Allocate at least $' + f"{min(savings * 0.4, debt * 0.1):,.0f}" + '/month extra toward debt.' if debt > 0 else 'Excellent! Staying debt-free is a huge financial advantage. Redirect funds to investments.'}

**3. {'Increase Savings Rate' if savings_rate < 20 else 'Optimize Savings Allocation'}**
{'Your savings rate is ' + f"{savings_rate:.1f}%" + '. The target is 20%. You need to save $' + f"{income * 0.2 - savings:,.0f}" + '/month more. Review subscriptions and discretionary spending.' if savings_rate < 20 else 'Great savings rate of ' + f"{savings_rate:.1f}%" + '! Ensure your savings are allocated: 50% investments, 30% goals, 20% emergency/buffer.'}

**4. Optimize Monthly Cash Flow**
Your monthly surplus is **${income - expenses:,.0f}**. {'This is healthy.' if income > expenses else 'You are spending more than you earn — this is critical to fix immediately.'} Consider the 50/30/20 rule: 50% needs (${income*0.5:,.0f}), 30% wants (${income*0.3:,.0f}), 20% savings (${income*0.2:,.0f}).

**5. {'Start Investing Immediately' if current_savings > emergency_fund_needed else 'First Complete Emergency Fund, Then Invest'}**
{'You have sufficient emergency reserves. Start investing $' + f"{savings * 0.6:,.0f}" + '/month in a diversified portfolio suited to your ' + risk + ' risk tolerance.' if current_savings > emergency_fund_needed else 'Once you hit $' + f"{emergency_fund_needed:,.0f}" + ' in savings, begin investing $' + f"{savings * 0.5:,.0f}" + '/month.'}

---

## 📅 30 / 60 / 90 Day Action Plan

**Next 30 Days:**
- Open a high-yield savings account if you don't have one
- {'Add $' + f"{(emergency_fund_needed - current_savings)/12:,.0f}" + ' to emergency fund' if emergency_fund_months < 6 else 'Review and rebalance existing investments'}
- Track every expense for 30 days using an app
- {'List all debts with interest rates and minimum payments' if debt > 0 else 'Set up automatic investment contributions'}

**Next 60 Days:**
- {'Pay off one small debt completely (snowball win)' if debt > 0 else 'Increase investment contributions by 5%'}
- Review and cancel unused subscriptions (avg saving: $50-150/month)
- Set up automatic transfers on payday
- Get quotes for term life insurance {'(critical with ' + str(dependents) + ' dependents)' if dependents > 0 else ''}

**Next 90 Days:**
- {'Achieve 3-month emergency fund milestone' if emergency_fund_months < 3 else 'Review investment portfolio performance'}
- Consult a tax advisor for {'India-specific' if country == 'India' else 'US-specific' if country == 'USA' else ''} deductions
- Set up a written budget and financial goals document
- Review progress against this plan

---

## ⚠️ Risk Warnings

{'- **Negative Cash Flow Risk**: Expenses exceed income. This is unsustainable.' if expenses >= income else ''}
{'- **High Debt Risk**: Debt-to-income ratio is concerning. Prioritize payoff.' if debt_to_income > 0.5 else ''}
{'- **No Emergency Fund Risk**: Without 6 months of expenses saved, any job loss or emergency could be devastating.' if emergency_fund_months < 3 else ''}
{'- **Dependents Risk**: With ' + str(dependents) + ' dependents, ensure you have adequate life and health insurance.' if dependents > 0 else ''}
"""
    return advice


def generate_retirement_advice(p):
    income = float(p.get("monthly_income", 0))
    savings = float(p.get("monthly_savings", 0))
    current_savings = float(p.get("current_savings", 0))
    age = int(p.get("age", 30))
    retirement_age = int(p.get("retirement_age", 60))
    country = p.get("country", "USA")
    risk = p.get("risk_tolerance", "moderate")

    years_to_retire = max(1, retirement_age - age)
    annual_income = income * 12
    retirement_corpus_needed = annual_income * 25
    growth_rates = {"conservative": 0.07, "moderate": 0.10, "aggressive": 0.13}
    rate = growth_rates.get(risk, 0.10)
    monthly_rate = rate / 12

    fv_current = current_savings * ((1 + monthly_rate) ** (years_to_retire * 12))
    n = years_to_retire * 12
    fv_contributions = savings * (((1 + monthly_rate) ** n - 1) / monthly_rate) if monthly_rate > 0 else savings * n
    projected_corpus = fv_current + fv_contributions

    required_monthly = 0
    if projected_corpus < retirement_corpus_needed and monthly_rate > 0:
        remaining = retirement_corpus_needed - fv_current
        required_monthly = remaining * monthly_rate / (((1 + monthly_rate) ** n) - 1)

    readiness_score = min(100, int((projected_corpus / retirement_corpus_needed) * 100))

    advice = f"""## 🏖️ Retirement Readiness Score: {readiness_score}/100

{'🟢 On Track' if readiness_score >= 80 else '🟡 Needs Attention' if readiness_score >= 50 else '🔴 Behind Schedule'}

---

## 📊 Retirement Projections

| Item | Value |
|------|-------|
| Current Age | {age} |
| Target Retirement Age | {retirement_age} |
| Years to Retire | {years_to_retire} |
| Assumed Growth Rate | {rate*100:.0f}% per year ({risk}) |
| Corpus Needed (25x rule) | ${retirement_corpus_needed:,.0f} |
| Projected Corpus | ${projected_corpus:,.0f} |
| Current Shortfall | ${max(0, retirement_corpus_needed - projected_corpus):,.0f} |

---

## 💰 Monthly Savings Required

To retire comfortably at **{retirement_age}**, you need **${retirement_corpus_needed:,.0f}**.

- Currently saving: **${savings:,.0f}/month**
- {'✅ You are on track! Keep saving at this rate.' if projected_corpus >= retirement_corpus_needed else '⚠️ You need to save **$' + f"{required_monthly:,.0f}" + '/month** to reach your goal.'}
- Every extra $100/month saved now grows to **${100 * (((1+monthly_rate)**(n)-1)/monthly_rate):,.0f}** by retirement.

---

## 🏦 Recommended Retirement Accounts

{'**For USA:**' if country == 'USA' else '**For India:**' if country == 'India' else '**General Recommendations:**'}

{'- **401(k)**: Max out to $23,000/year. Get employer match first (free money!)' if country == 'USA' else ''}
{'- **Roth IRA**: Contribute $7,000/year for tax-free growth. Best if young.' if country == 'USA' else ''}
{'- **HSA**: If eligible, contributes triple-tax advantage.' if country == 'USA' else ''}
{'- **NPS (National Pension System)**: Extra ₹50,000 deduction under 80CCD(1B).' if country == 'India' else ''}
{'- **EPF/PPF**: Max out PPF at ₹1.5L/year — guaranteed 7.1% tax-free returns.' if country == 'India' else ''}
{'- **ELSS Mutual Funds**: 3-year lock-in, equity returns, tax savings under 80C.' if country == 'India' else ''}
{'- **Diversified Portfolio**: Mix of equity funds, bonds, and real estate.' if country not in ['USA', 'India'] else ''}

---

## 📅 Retirement Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| 1x Annual Salary Saved | By age 30 | {'✅ Done' if current_savings >= annual_income else '⏳ $' + f"{annual_income - current_savings:,.0f}" + ' to go'} |
| 3x Annual Salary Saved | By age 40 | {'✅ Done' if current_savings >= annual_income*3 else '⏳ $' + f"{annual_income*3 - current_savings:,.0f}" + ' to go'} |
| 6x Annual Salary Saved | By age 50 | {'✅ Done' if current_savings >= annual_income*6 else '⏳ $' + f"{annual_income*6 - current_savings:,.0f}" + ' to go'} |
| 10x Annual Salary Saved | By age 60 | {'✅ Done' if current_savings >= annual_income*10 else '⏳ $' + f"{annual_income*10 - current_savings:,.0f}" + ' to go'} |

---

## 🚀 Catch-Up Strategies

{'- **Increase savings by 1% every year** — automate this each January' if readiness_score < 80 else ''}
{'- **Avoid early withdrawals** — penalties + lost compounding is devastating' }
- **Delay retirement by 2-3 years** if needed — adds significantly to corpus
- **Part-time work in early retirement** reduces drawdown rate dramatically
- **Downsize housing** in retirement to unlock equity and reduce expenses
"""
    return advice


def generate_tax_advice(p):
    income = float(p.get("monthly_income", 0))
    savings = float(p.get("monthly_savings", 0))
    current_savings = float(p.get("current_savings", 0))
    age = int(p.get("age", 30))
    dependents = int(p.get("dependents", 0))
    employment = p.get("employment_type", "salaried")
    country = p.get("country", "USA")
    debt = float(p.get("total_debt", 0))

    annual_income = income * 12
    annual_savings = savings * 12

    if country == "USA":
        if annual_income <= 11600: tax_rate, bracket = 0.10, "10%"
        elif annual_income <= 47150: tax_rate, bracket = 0.12, "12%"
        elif annual_income <= 100525: tax_rate, bracket = 0.22, "22%"
        elif annual_income <= 191950: tax_rate, bracket = 0.24, "24%"
        elif annual_income <= 243725: tax_rate, bracket = 0.32, "32%"
        else: tax_rate, bracket = 0.35, "35%"
        estimated_tax = annual_income * tax_rate
        potential_savings = min(annual_savings * 0.3, 8000)
    elif country == "India":
        if annual_income * 84 <= 300000: tax_rate, bracket = 0.0, "0%"
        elif annual_income * 84 <= 700000: tax_rate, bracket = 0.05, "5%"
        elif annual_income * 84 <= 1000000: tax_rate, bracket = 0.10, "10%"
        elif annual_income * 84 <= 1200000: tax_rate, bracket = 0.15, "15%"
        elif annual_income * 84 <= 1500000: tax_rate, bracket = 0.20, "20%"
        else: tax_rate, bracket = 0.30, "30%"
        estimated_tax = annual_income * tax_rate
        potential_savings = min(annual_savings * 0.25, 5000)
    else:
        tax_rate = 0.20
        bracket = "~20%"
        estimated_tax = annual_income * tax_rate
        potential_savings = annual_savings * 0.15

    advice = f"""## 📊 Tax Optimization Strategy

**Estimated Annual Tax Liability: ${estimated_tax:,.0f}** ({bracket} bracket)
**Potential Tax Savings: Up to ${potential_savings:,.0f}/year**

---

## 💰 Your Tax Situation

| Item | Value |
|------|-------|
| Annual Income | ${annual_income:,.0f} |
| Tax Bracket | {bracket} |
| Estimated Tax | ${estimated_tax:,.0f} |
| Effective Rate | {tax_rate*100:.0f}% |
| After-Tax Income | ${annual_income - estimated_tax:,.0f} |

---

## 🎯 Tax-Saving Opportunities

{'**USA Tax Strategies:**' if country == 'USA' else '**India Tax Strategies:**' if country == 'India' else '**General Tax Strategies:**'}

{'**1. Maximize 401(k) Contributions** — Up to $23,000/year pre-tax. Saves up to $' + f"{23000 * tax_rate:,.0f}" + ' in taxes.' if country == 'USA' else ''}
{'**2. Contribute to Roth IRA** — $7,000/year for tax-free growth. Best if in lower bracket now.' if country == 'USA' else ''}
{'**3. HSA Contributions** — Triple tax advantage: deductible, grows tax-free, withdrawn tax-free for medical.' if country == 'USA' else ''}
{'**4. Itemize Deductions** if mortgage interest + state taxes + charity > $14,600 standard deduction.' if country == 'USA' else ''}
{'**5. Child Tax Credit** — $2,000 per child under 17.' if country == 'USA' and dependents > 0 else ''}
{'**6. Home Office Deduction** — If self-employed, deduct home office proportionally.' if country == 'USA' and employment in ['self_employed', 'freelancer', 'business_owner'] else ''}

{'**1. Section 80C** — Invest ₹1.5L in ELSS, PPF, LIC to save ₹' + f"{150000 * 0.30:,.0f}" + ' in tax.' if country == 'India' else ''}
{'**2. Section 80D** — Deduct health insurance premium (₹25,000 self, ₹50,000 parents above 60).' if country == 'India' else ''}
{'**3. NPS Section 80CCD(1B)** — Extra ₹50,000 deduction beyond 80C limit.' if country == 'India' else ''}
{'**4. HRA Exemption** — If renting, claim HRA exemption to significantly reduce taxable income.' if country == 'India' and employment == 'salaried' else ''}
{'**5. Standard Deduction** — ₹50,000 automatic deduction for salaried employees.' if country == 'India' and employment == 'salaried' else ''}
{'**6. Capital Gains Planning** — Hold equity investments >1 year for LTCG at 10% vs STCG at 15%.' if country == 'India' else ''}

{'**1. Maximize tax-advantaged retirement accounts** in your country.' if country not in ['USA', 'India'] else ''}
{'**2. Consider tax-loss harvesting** — offset capital gains with losses.' if country not in ['USA', 'India'] else ''}

---

## 📈 Investment Vehicles for Tax Efficiency

| Vehicle | Tax Benefit | Priority |
|---------|------------|---------|
| {'401k / NPS' if country in ['USA', 'India'] else 'Pension Account'} | Pre-tax contributions | 🔴 High |
| {'Roth IRA / ELSS' if country in ['USA', 'India'] else 'ISA/TFSA'} | Tax-free growth | 🔴 High |
| {'HSA' if country == 'USA' else 'PPF' if country == 'India' else 'Bonds'} | Triple/Double benefit | 🟡 Medium |
| Index Funds (ETFs) | Low turnover = low tax | 🟡 Medium |
| Municipal Bonds | Tax-exempt interest | 🟢 If high bracket |

---

## 🗓️ Tax Calendar Action Items

- **Now**: Calculate exact deductions you're currently missing
- **Q4**: Make additional retirement contributions before year end
- **January**: Collect all investment statements and interest documents
- **Before Filing**: Consult a {'CPA' if country == 'USA' else 'CA (Chartered Accountant)' if country == 'India' else 'tax professional'} to find jurisdiction-specific savings
- **Year-Round**: Track deductible expenses in a dedicated folder/app

{'**Self-Employed Note**: Track ALL business expenses — home office, internet, phone, equipment, travel, meals (50%). These reduce your self-employment tax too.' if employment in ['self_employed', 'freelancer', 'business_owner'] else ''}
"""
    return advice


def generate_insurance_advice(p):
    income = float(p.get("monthly_income", 0))
    expenses = float(p.get("monthly_expenses", 0))
    debt = float(p.get("total_debt", 0))
    age = int(p.get("age", 30))
    dependents = int(p.get("dependents", 0))
    employment = p.get("employment_type", "salaried")
    country = p.get("country", "USA")

    annual_income = income * 12
    life_cover_needed = annual_income * 10 + debt
    disability_monthly = income * 0.6
    health_deductible = 1500 if country == "USA" else 0
    emergency_fund = expenses * 6

    advice = f"""## 🛡️ Insurance Needs Analysis

**Your complete insurance coverage requirement has been calculated below.**

---

## 📋 Coverage Summary

| Insurance Type | Coverage Needed | Priority |
|---------------|----------------|---------|
| Life Insurance | ${life_cover_needed:,.0f} | {'🔴 Critical' if dependents > 0 else '🟡 Recommended'} |
| Health Insurance | Full coverage + ${health_deductible:,} deductible | 🔴 Critical |
| Disability Insurance | ${disability_monthly:,.0f}/month | 🔴 High |
| {'Renters/Home Insurance' } | Replacement value | 🟡 Important |
| Liability/Umbrella | $1,000,000+ | 🟢 Recommended |

---

## 🏥 1. Life Insurance — **${life_cover_needed:,.0f} Coverage**

**Calculation:** (Annual Income × 10) + Total Debt
= (${annual_income:,.0f} × 10) + ${debt:,.0f} = **${life_cover_needed:,.0f}**

{'**CRITICAL**: With ' + str(dependents) + ' dependent(s), life insurance is non-negotiable.' if dependents > 0 else 'Even without dependents, life insurance covers debts and final expenses.'}

- **Recommended type**: Term life insurance (20-30 year term)
- **Annual premium estimate**: ${life_cover_needed * 0.003:,.0f} - ${life_cover_needed * 0.005:,.0f}/year (${life_cover_needed * 0.003 / 12:,.0f} - ${life_cover_needed * 0.005 / 12:,.0f}/month)
- Buy before age 35 for lowest premiums
- {'Consider employer group life (often 1-2x salary free) but supplement with private policy.' if employment == 'salaried' else 'As self-employed, you must buy individual term policy — no employer coverage.'}

---

## 🏥 2. Health Insurance

{'**USA**: Critical — medical bankruptcy is real.' if country == 'USA' else '**India**: Despite government schemes, private health cover is essential.' if country == 'India' else 'Essential in any country.'}

- Minimum coverage: **${income * 24:,.0f}** (2 years income)
- {'Look for low deductible plan if you have health conditions; high-deductible HSA plan if healthy.' if country == 'USA' else 'Get a family floater of at least ₹10-20 lakhs. Top-up with super top-up plan.' if country == 'India' else ''}
- {'Employer health plan: Evaluate if coverage is sufficient. May need supplemental.' if employment == 'salaried' else 'You must buy individual/family plan. Budget $300-800/month for individual coverage.' if employment in ['self_employed', 'freelancer'] else ''}
- **Critical riders to add**: Critical illness cover, hospital cash benefit

---

## 🦽 3. Disability Insurance — **${disability_monthly:,.0f}/month**

Often overlooked but **your income is your biggest asset**.

- Coverage target: 60% of monthly income = **${disability_monthly:,.0f}/month**
- Annual cost estimate: **${disability_monthly * 12 * 0.02:,.0f} - ${disability_monthly * 12 * 0.03:,.0f}/year**
- Short-term disability: covers 3-6 months
- Long-term disability: covers until retirement age
- {'Check if employer offers group disability plan — if so, still supplement to 60% of income.' if employment == 'salaried' else 'As self-employed, this is critical. No sick pay otherwise.'}

---

## 🏠 4. Property Insurance

- Renters insurance: ~$15-30/month (covers belongings + liability)
- Homeowners insurance: 0.5-1% of home value per year
- Always include liability protection of at least $300,000

---

## 🔢 Coverage Gap Analysis

| Need | Recommended | Action |
|------|-------------|--------|
| Life | ${life_cover_needed:,.0f} | {'✅ Get term policy now' if age < 40 else '⚠️ Act fast — premiums rise with age'} |
| Health | ${income * 24:,.0f} | Review current plan coverage |
| Disability | ${disability_monthly:,.0f}/month | Often missing — get quote |
| Emergency Fund | ${emergency_fund:,.0f} | {'✅ Self-insures small risks' if True else ''} |

---

## 📅 Action Steps (Priority Order)

1. **This week**: Get term life insurance quote online (takes 15 minutes)
2. **This month**: Review health insurance coverage gaps
3. **Next 60 days**: Set up disability insurance if not covered
4. **Quarterly**: Review beneficiary designations on all policies
5. **Annually**: Re-evaluate coverage as income/dependents change

{'**Important for parents**: Update beneficiaries, set up a will/guardian designation for your ' + str(dependents) + ' dependents.' if dependents > 0 else ''}
"""
    return advice


def generate_investment_advice(p):
    income = float(p.get("monthly_income", 0))
    savings = float(p.get("monthly_savings", 0))
    current_savings = float(p.get("current_savings", 0))
    expenses = float(p.get("monthly_expenses", 0))
    age = int(p.get("age", 30))
    risk = p.get("risk_tolerance", "moderate")
    goal = p.get("primary_goal", "wealth_building")
    country = p.get("country", "USA")
    retirement_age = int(p.get("retirement_age", 60))

    emergency_fund = expenses * 6
    investable = max(0, current_savings - emergency_fund)
    monthly_invest = savings * 0.7

    allocations = {
        "conservative": {"Stocks/Equity": 30, "Bonds/Debt": 50, "Real Estate/REITs": 10, "Gold/Commodities": 5, "Cash/Money Market": 5},
        "moderate":     {"Stocks/Equity": 60, "Bonds/Debt": 25, "Real Estate/REITs": 10, "Gold/Commodities": 3, "Cash/Money Market": 2},
        "aggressive":   {"Stocks/Equity": 80, "Bonds/Debt": 10, "Real Estate/REITs": 5,  "Gold/Commodities": 2, "Cash/Money Market": 3},
    }
    alloc = allocations.get(risk, allocations["moderate"])

    instruments = {
        "USA": {
            "Stocks/Equity": "S&P 500 Index Fund (VOO/SPY), Total Market ETF (VTI)",
            "Bonds/Debt": "Total Bond Market ETF (BND), Treasury I-Bonds",
            "Real Estate/REITs": "Vanguard Real Estate ETF (VNQ)",
            "Gold/Commodities": "GLD ETF or physical gold",
            "Cash/Money Market": "High-yield savings (5%+ APY) or T-bills"
        },
        "India": {
            "Stocks/Equity": "Nifty 50 Index Fund, ELSS Mutual Funds, Direct equity bluechips",
            "Bonds/Debt": "PPF, RBI Bonds, Debt Mutual Funds, FD",
            "Real Estate/REITs": "Embassy REITs, Mindspace REITs",
            "Gold/Commodities": "Sovereign Gold Bonds (SGBs), Gold ETF",
            "Cash/Money Market": "Liquid Mutual Funds, Flexi FD"
        }
    }
    instr = instruments.get(country, instruments["USA"])

    years = retirement_age - age
    growth_rate = {"conservative": 0.07, "moderate": 0.10, "aggressive": 0.13}[risk]
    projected_10yr = investable * ((1 + growth_rate) ** 10) + monthly_invest * (((1 + growth_rate/12) ** 120 - 1) / (growth_rate/12))
    projected_retire = investable * ((1 + growth_rate) ** years) + monthly_invest * (((1 + growth_rate/12) ** (years*12) - 1) / (growth_rate/12)) if years > 0 else investable

    advice = f"""## 📈 Personalized Investment Strategy

**Risk Profile**: {risk.capitalize()} | **Monthly Investment**: ${monthly_invest:,.0f}
**Investable Now**: ${investable:,.0f} | **Expected Return**: {growth_rate*100:.0f}%/year

---

## 🎯 Recommended Asset Allocation

"""
    for asset, pct in alloc.items():
        amount = monthly_invest * pct / 100
        advice += f"**{asset}: {pct}%** (${amount:,.0f}/month)\n"
        if asset in instr:
            advice += f"→ {instr[asset]}\n\n"

    advice += f"""
---

## 💰 Projected Growth

| Timeline | Projected Value |
|----------|----------------|
| 1 Year   | ${investable * (1+growth_rate) + monthly_invest * 13:,.0f} |
| 5 Years  | ${investable * ((1+growth_rate)**5) + monthly_invest * (((1+growth_rate/12)**60-1)/(growth_rate/12)):,.0f} |
| 10 Years | ${projected_10yr:,.0f} |
| At Retirement ({retirement_age}) | ${projected_retire:,.0f} |

*Assumes {growth_rate*100:.0f}% annual return with regular monthly contributions of ${monthly_invest:,.0f}*

---

## 📅 Dollar-Cost Averaging Plan

Invest **${monthly_invest:,.0f}/month** consistently regardless of market conditions:

- **Week 1 of each month**: Set up auto-transfer on payday
- **Invest same amount every month** — removes emotion from investing
- **Never try to time the market** — time IN the market beats timing
- **Rebalance every 6-12 months** back to target allocation

---

## 🏆 Investment Priority Order

1. **Emergency Fund First** — ${emergency_fund:,.0f} in liquid savings
2. **Employer Match** — 401k/EPF match is 100% instant return
3. **High-Interest Debt** — Pay off anything above 7% interest
4. **Tax-Advantaged Accounts** — {'IRA/401k' if country == 'USA' else 'NPS/PPF/ELSS' if country == 'India' else 'Pension/Tax accounts'}
5. **Taxable Brokerage** — Remaining amount in index funds

---

## ⚠️ Investment Rules to Follow

- Never invest money you need in the next 3 years
- {'Keep ' + str(int(alloc["Cash/Money Market"])) + '% in liquid/safe assets at all times'}
- Diversify — never put >10% in a single stock
- {'Avoid speculative assets (crypto, penny stocks) given your conservative profile.' if risk == 'conservative' else 'Limit speculative investments (crypto, options) to max 5% of portfolio.' if risk == 'moderate' else 'Even aggressive investors should keep speculative assets under 15% of portfolio.'}
- Stay invested during market downturns — volatility is normal
- Review and rebalance annually, not monthly
"""
    return advice


ADVICE_GENERATORS = {
    "financial":  generate_financial_advice,
    "retirement": generate_retirement_advice,
    "tax":        generate_tax_advice,
    "insurance":  generate_insurance_advice,
    "investment": generate_investment_advice,
}

@app.route("/api/advice/<advice_type>", methods=["POST"])
def get_advice(advice_type):
    uid = current_user_id()
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    if advice_type not in ADVICE_GENERATORS:
        return jsonify({"error": "Invalid advice type"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT profile_data FROM financial_profiles WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Please complete your financial profile first"}), 400
    profile = json.loads(row["profile_data"])
    advice_text = ADVICE_GENERATORS[advice_type](profile)
    with get_db() as conn:
        conn.execute("INSERT INTO advice_history (user_id, advice_type, advice_content) VALUES (?, ?, ?)",
                     (uid, advice_type, advice_text))
    return jsonify({"advice": advice_text, "type": advice_type})

@app.route("/api/scenario", methods=["POST"])
def scenario_model():
    uid = current_user_id()
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.json
    scenario_type = data.get("scenario", "base")
    years = int(data.get("years", 10))
    with get_db() as conn:
        row = conn.execute("SELECT profile_data FROM financial_profiles WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Profile not found"}), 400
    profile = json.loads(row["profile_data"])
    monthly_savings = float(profile.get("monthly_savings", 1000))
    current_savings = float(profile.get("current_savings", 0))
    risk_tolerance = profile.get("risk_tolerance", "moderate")
    rates = {
        "conservative": {"bull": 0.07, "base": 0.05, "bear": 0.02},
        "moderate":     {"bull": 0.12, "base": 0.08, "bear": 0.01},
        "aggressive":   {"bull": 0.18, "base": 0.11, "bear": -0.03}
    }.get(risk_tolerance, {"bull": 0.12, "base": 0.08, "bear": 0.01})
    rate = rates[scenario_type]
    monthly_rate = rate / 12
    projections = []
    balance = current_savings
    for year in range(1, years + 1):
        for _ in range(12):
            balance = balance * (1 + monthly_rate) + monthly_savings
        projections.append({"year": year, "balance": round(balance, 2)})
    return jsonify({"scenario": scenario_type, "rate": rate, "projections": projections, "final_balance": projections[-1]["balance"]})

if __name__ == "__main__":
    print("🚀 FinWise Backend running on http://localhost:5000")
    app.run(debug=True, port=5000)