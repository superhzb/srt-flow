# Privacy Policy

_Last updated: 18 July 2026_

srt-flow ("we", "us", "the Service") is operated as a sole proprietorship by
**ZHIBIN HUANG**, located in **Quebec, Canada**. This policy explains
what personal information we collect, why, who we share it with, and your rights.

Contact for any privacy question or request: **support@srt-flow.com**. This
address is also our designated privacy contact under Quebec's Law 25.

## 1. What we collect

| Data                                                             | Source         | Why                                       |
| ---------------------------------------------------------------- | -------------- | ----------------------------------------- |
| Email address                                                    | Google sign-in | Account identity, receipts, support       |
| Google subject ID                                                | Google sign-in | Stable account key                        |
| IP address                                                       | Your browser   | Security, rate-limiting, abuse prevention |
| Uploaded subtitle (`.srt`) files and their text                  | You            | To perform the translation you request    |
| Translation output                                               | Generated      | To deliver and store your results         |
| Payment records (amount, credit balance)                         | Stripe         | Billing, credit ledger                    |
| Analytics identifiers (`anon_id`, `session_id`) and usage events | Your browser   | Product analytics (first-party only)      |

We do **not** collect passwords (sign-in is Google OAuth only). We do **not**
use third-party advertising or analytics trackers.

## 2. Card payments

Card and payment details are collected and processed by **Stripe**. We never see
or store your full card number. See Stripe's privacy policy at stripe.com/privacy.

## 3. How your subtitle text is processed — please read

To translate your file, the subtitle **text you upload is sent to our LLM
provider, DeepSeek** (`api.deepseek.com`, operated from China).

**Important:**
- DeepSeek may use submitted text to train and improve its models.
- Your subtitle text therefore leaves our systems, is transferred to a provider
  in China, and may be retained and used by that provider.
- **Do not upload subtitle files containing sensitive, confidential, or personal
  information** you are not comfortable sharing under these terms. Subtitles are
  dialogue text — avoid uploading anything private.
- China has no data-protection adequacy decision under the GDPR or Quebec Law 25.
  By uploading, you consent to this cross-border transfer as necessary to provide
  the Service you request.

If you are an EU/UK/EEA user, this transfer is a material part of the Service; if
you do not consent, do not upload files.

## 4. Sub-processors

| Provider           | Purpose                 | Location     |
| ------------------ | ----------------------- | ------------ |
| **Google** (OAuth) | Sign-in / identity      | USA          |
| **Stripe**         | Payments                | USA / global |
| **DeepSeek**       | LLM translation         | China        |
| **Cloudflare**     | Network / email routing | Global       |

## 5. Retention

- **Uploaded files and translation output:** deleted automatically 30 days
  after the job is created. You may request earlier deletion at any time.
- **Analytics events:** identity fields are scrubbed at 365 days.
- **Account + billing records:** retained as long as your account exists and as
  required by tax/accounting law.

## 6. Your rights

Depending on where you live (PIPEDA, Quebec Law 25, GDPR, CCPA) you may:

- Access the personal information we hold about you.
- Correct it.
- **Delete your account and associated data** ("right to erasure").
- Withdraw consent / object to processing.
- Request data portability.

To exercise any right, email **support@srt-flow.com**. We respond within the
timeframe required by applicable law.

## 7. Cookies & local storage

We use first-party local storage for an `anon_id` and `session_id` to measure
product usage. When you sign in, the `anon_id` is associated with your account
server-side. We use no third-party or advertising cookies. Sign-in uses a secure,
HttpOnly session cookie required for the Service to function.

## 8. Security

Sign-in via Google OAuth (no passwords). Session cookies are HttpOnly, Secure,
SameSite=lax. Uploads are size- and type-restricted with path-traversal guards.

## 9. Changes

We may update this policy; the "last updated" date will change. Material changes
will be surfaced in-app.

## 10. Contact

**support@srt-flow.com** — Quebec, Canada.
