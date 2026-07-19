# srt-flow — Legal Compliance Research

> **⚠️ Research, not legal advice.** Synthesized from public sources (regulator guidance, law-firm briefings, DeepSeek's own policies, news). Verify with a Quebec privacy lawyer before launch. Compiled 2026-07-18.

Method: 5 research angles → 22 sources fetched → 87 claims extracted → adversarially verified (2/3-vote to kill). 1 claim killed (see §6). Sources listed at end.

---

## TL;DR — the one decision that matters

**Sending user subtitle text to DeepSeek's API is your biggest legal exposure.** DeepSeek's own policies + third-party analysis say:
- Data is **collected, processed, and stored in China** (Hangzhou servers). Subject to China's PIPL + 2017 Cybersecurity Law, which can compel disclosure to the state.
- DeepSeek **trains on submitted inputs**. Consumer privacy policy offers a training opt-out; the **API Terms are silent on retention, training, and opt-out** — no defined retention period, no clear API opt-out found as of research date.
- No SOC 2 / GDPR DPA / published compliance certifications.
- API Terms are **governed by Chinese law**, disputes in Hangzhou, and push **content-moderation liability onto you** (the developer).
- **Canadian federal government banned DeepSeek on government devices (Feb 7, 2025);** Italy pulled its apps; Taiwan, Australia, South Korea, US federal bodies restricted it.

→ Under **Quebec Law 25 §17 you must complete a Privacy Impact Assessment BEFORE sending personal info outside Quebec**, and may only transfer if it gets "adequate protection." A China transfer to a train-on-input provider is exactly the hard case. **This is a founder decision, informed by counsel — not a code fix.**

**Practical options (pick with lawyer):**
1. **Don't send PII to DeepSeek.** Subtitle text often isn't personal data — but can be. Strip/scrub, and never send email/account data. Data minimization is the strongest mitigation.
2. **Disclose + consent.** Name DeepSeek + China explicitly at collection; get informed opt-in (Law 25 requires disclosure of out-of-province transfer at collection).
3. **Switch provider** to one with a no-training API + DPA (OpenAI/Anthropic/Google/DeepL enterprise) if the risk is unacceptable. Cleanest path.
4. Written agreement + PIA on file regardless.

---

## 1. Canada — PIPEDA + Quebec Law 25 (must-have before launch)

You're Quebec/Ontario-based selling to consumers → **Law 25 is the strict one**; comply with it and you largely cover PIPEDA.

**Mandatory before public launch:**
- **Named privacy officer published on the website** — name, title, contact. Defaults to the CEO unless delegated in writing. (Law 25)
- **Privacy policy** in clear, simple language, purpose-specific.
- **Consent** must be free, informed, specific, in clear language, and **requested separately** from other terms. Parental consent for minors under 14.
- **Opt-in consent before any tracking technology** (cookies *and* persistent identifiers) that tracks personal info.
- **Disclose cross-border/out-of-Quebec transfer at the time of collection** (in effect since Sept 22, 2023) — you must tell users their data may go outside Quebec (→ DeepSeek/China).
- **Privacy Impact Assessment (PIA/TIA) before transferring PI outside Quebec** (§17). Assess 4 factors: (1) sensitivity, (2) purpose, (3) protection measures incl. contractual, (4) destination's legal framework. Transfer allowed only if protection is **adequate**. Must be governed by a **written agreement** reflecting the PIA + risk mitigation.
- **Right to erasure** (in effect Sept 2023) — build a user data-deletion path.
- **Breach notification** — if a confidentiality incident risks serious injury, promptly notify the **CAI (Commission d'accès à l'information)** + affected individuals.
- A **TIA is also triggered when data is merely "accessible from" outside Quebec**, not only when explicitly sent. Keep a register of TIAs; review annually / on vendor change.

**Teeth:** Law 25 penalties range **$15,000–$25,000,000 or 4% of worldwide turnover**, whichever is greater.

## 2. DeepSeek API — data handling (from their policies + analysis)

- **Storage/processing in China** (Hangzhou); subject to PIPL + Cybersecurity Law.
- **Trains on inputs.** Consumer policy has a training opt-out; **API Terms specify no retention period, no explicit training statement, no opt-out** — deferred to a general privacy policy that doesn't separate API from consumer use.
- **Retention:** unspecified for API (competitors offer defined ~30-day windows; DeepSeek does not).
- **You own inputs/outputs** per API Terms, but Terms **don't restrict DeepSeek's own use of inputs** for "service improvement."
- **Content-moderation + emergency-disposal duties fall on you**, the developer.
- **No SOC 2 Type II, no GDPR DPA, no HIPAA BAA.**
- **Bans/restrictions:** Canada federal gov (Feb 7, 2025), Italy (app removal + processing limit Jan 30, 2025), Taiwan, Australia, South Korea, US House/Texas/Navy/Pentagon/NASA. Driven by Chinese national-security laws compelling data assistance + broad data collection.

## 3. Cross-border transfer to China

- **China has no EU adequacy decision** (Canada/Japan/NZ/Switzerland do). Transfers to China need **Chapter V safeguards** — commonly **SCCs** + **Transfer Impact Assessment (Schrems II)** + supplementary measures (pseudonymization, encryption, government-access clauses).
- **China TIAs frequently conclude Chinese law conflicts** with SCC obligations (state access), requiring strong extra measures — hard to satisfy. A 2021 EDPB study criticized China's protection level.
- **noyb (Schrems)** filed complaints against six Chinese companies (incl. over EU→China transfers); DPAs can prohibit such transfers.
- **Law 25 §17 PIA** duty applies to *any* out-of-Quebec transfer (province or foreign), assessing the same 4 factors + written contract + adequate protection.

## 4. GDPR / UK-GDPR / CCPA — do they even apply to you?

- **Mere accessibility from the EU does NOT trigger GDPR.** Art. 3(2) needs **targeting** (EU languages/currencies/TLDs, paid EU ad targeting) **or monitoring of behaviour**.
- ⚠️ **Your persistent `anon_id` analytics tracking can qualify as "monitoring of behaviour"** — EDPB reads this broadly (online tracking via cookies/identifiers). If you knowingly track EU-located users, that can pull you into GDPR even without EU-targeted sales. Practical trigger to watch.
- **ePrivacy Art. 5(3) is technology-neutral** → a non-essential **persistent identifier in localStorage needs prior consent, exactly like a cookie**. Switching from cookie to localStorage does **not** avoid it. German DSK + EDPB Guidelines 02/2023 confirm localStorage/IndexedDB are in scope.
- **CCPA/CPRA** applies only if you hit a threshold: **>US$25M revenue**, OR PI of **100,000+ California residents**, OR **50%+ revenue from selling PI**. A small launch is likely **under all three** — low priority now, revisit as you scale.

## 5. Pre-launch compliance checklist (founder-actionable)

**Blockers (Law 25 — apply regardless of EU/US):**
- [ ] Appoint + **publish privacy officer** name/title/contact on site.
- [ ] **Privacy Policy** naming sub-processors: **DeepSeek (China), Stripe, Google**; state data may leave Quebec/Canada.
- [ ] **Complete a §17 PIA** for the DeepSeek/China transfer; keep on file. ← get counsel.
- [ ] **Written agreement** with DeepSeek (or chosen LLM vendor) reflecting PIA + safeguards.
- [ ] **Consent flow**: separate, clear, opt-in; disclose out-of-Quebec transfer at collection.
- [ ] **User data-deletion path** (right to erasure).
- [ ] **Breach-response plan** (CAI + user notification).
- [ ] **Terms of Service** (liability cap, refunds, acceptable-use/copyright warranty).
- [ ] **Contact method** published (also Stripe + Law 25 requirement).

**DeepSeek decision (with counsel):**
- [ ] Decide: minimize/scrub data sent, OR explicit consent, OR switch to no-training vendor w/ DPA.
- [ ] Never send email/account PII in prompts.
- [ ] Confirm current DeepSeek API training/retention/opt-out terms directly (may have changed).

**If/when EU users or tracking matters:**
- [ ] **Consent banner** before writing the persistent `anon_id` to localStorage (ePrivacy), OR make analytics strictly-essential/first-party-anonymous with no persistent cross-session ID.
- [ ] Reassess GDPR if you target EU or knowingly monitor EU users; SCCs + TIA if EU data → China.

**Defer (revisit at scale):**
- [ ] CCPA/CPRA — only at >$25M rev or 100k+ CA residents.

## 6. Verification note

One claim was **refuted** and excluded: *"SCCs are the required mechanism for all non-EEA transfers to non-adequate countries."* Reality: SCCs are the **most common** Chapter V tool but **not the only** lawful basis — Art. 49 derogations (e.g., explicit consent, contract necessity), BCRs, and certifications also exist. Don't treat SCCs as the sole path.

## Sources

**Canada / Law 25:** mccarthy.ca (PIA guide), onetrust.com, outsidegc.com, blg.com (cross-border), upperharbour.ca, watchdogsecurity.io.
**DeepSeek policies:** cdn.deepseek.com (Open Platform ToS + Privacy Policy, primary), tokenmix.ai (API safety analysis).
**DeepSeek bans:** cbc.ca, globalnews.ca, techcrunch.com, aljazeera.com.
**Cross-border/China:** taylorwessing.com, pinsentmasons.com (Schrems II), blg.com.
**GDPR/CCPA/ePrivacy:** clarip.com (EDPB territorial scope), timelex.eu, veracly.app + clym.io (localStorage consent), usercentrics.com.
