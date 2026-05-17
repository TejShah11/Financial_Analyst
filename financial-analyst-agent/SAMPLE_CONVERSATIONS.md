# Sample Conversations — LedgerMind

Six representative conversations demonstrating the chatbot's capabilities across different query types, routing tracks, and difficulty levels.

---

## Conversation 1 — Simple Narrative Lookup (Easy)

**Route:** `vector_search`  
**Source:** `ifrs-usd-press-release_q1.pdf`  
**Difficulty:** Easy

> **User:** What was Infosys's revenue in Q1 FY26?

> **LedgerMind:** *(answer with revenue figure, constant-currency growth, sequential growth)*

**Screenshot:**

<!-- Attach screenshot here -->
![Conversation 1 — Q1 Revenue](docs/screenshots/conv1_q1_revenue.png)

---

## Conversation 2 — Quantitative / Stock Data Lookup

**Route:** `pandas_calc`  
**Source:** `500209.csv`  
**Difficulty:** Easy

> **User:** What was the closing price of Infosys stock on March 30, 2026?

> **LedgerMind:** *(answer with exact closing price in INR)*

**Screenshot:**

<!-- Attach screenshot here -->
![Conversation 2 — Stock Close Price](docs/screenshots/conv2_stock_close.png)

---

## Conversation 3 — Hard Multi-Document Comparison

**Route:** `vector_search` (multi-quarter)  
**Sources:** `ifrs-usd-press-release_q1.pdf`, `ifrs-usd-press-release_q2.pdf`, `ifrs-usd-press-release_q3.pdf`  
**Difficulty:** Hard

> **User:** How did Infosys revise its FY26 revenue guidance across Q1, Q2, and Q3?

> **LedgerMind:** *(answer tracing guidance from 1%–3% → 2%–3% → 3.0%–3.5% in constant currency)*

**Screenshot:**

<!-- Attach screenshot here -->
![Conversation 3 — Guidance Revision Trend](docs/screenshots/conv3_guidance_revisions.png)

---

## Conversation 4 — Multi-Turn Follow-up (Memory Demo)

**Route:** Turn 1 `vector_search` → Turn 2 `vector_search` with coreference resolution  
**Source:** `ifrs-usd-press-release_q3.pdf`  
**Difficulty:** Hard

> **User:** What was the operating margin in Q3 FY26?

> **LedgerMind:** *(answer with reported IFRS margin and adjusted margin)*

> **User:** What caused the gap between the two figures?

> **LedgerMind:** *(answer explaining the Labour Codes provision of $143 million)*

**Screenshot:**

<!-- Attach screenshot here -->
![Conversation 4 — Multi-Turn Memory](docs/screenshots/conv4_multiturn_margin.png)

---

## Conversation 5 — Out-of-Scope Adversarial (Refusal)

**Route:** `vector_search` → refusal  
**Source:** *(none — out of corpus)*  
**Difficulty:** Hard

> **User:** What was Infosys's credit rating assigned by Moody's?

> **LedgerMind:** *(politely states it does not have Moody's rating data in the provided documents and does not guess)*

**Screenshot:**

<!-- Attach screenshot here -->
![Conversation 5 — Refusal](docs/screenshots/conv5_refusal_credit_rating.png)

---

## Conversation 6 — FY27 Guidance + Download Export

**Route:** `vector_search` → PDF/Excel export  
**Source:** `ifrs-usd-press-release_q4.pdf`  
**Difficulty:** Easy

> **User:** What is Infosys's revenue growth and operating margin guidance for FY27? Export it as a PDF.

> **LedgerMind:** *(answer with 1.5%–3.5% CC growth and 20%–22% margin guidance, plus a downloadable PDF report)*

**Screenshot:**

<!-- Attach screenshot here -->
![Conversation 6 — FY27 Guidance with PDF Export](docs/screenshots/conv6_fy27_guidance_export.png)

---

> **Note:** Screenshots are taken from the Next.js frontend (`frontend/web/`) running against the FastAPI backend at `http://localhost:8000`. To run: `cd frontend/web && npm run dev`.
