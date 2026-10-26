# NordTech Solutions — IT Setup Guide

*Document type: IT / Technical Reference*
*Source doc ID: `it_guide`*
*Category: IT*
*Country: All*
*Last updated: March 2026*

---

## 1. Laptop Setup

New employees receive a company laptop before their first day. The default laptop is a MacBook (macOS); Windows machines are available on request via IT.

1. Power on the laptop. You will see a "NordTech Device Setup" screen powered by our MDM (Jamf for macOS, Intune for Windows).
2. Sign in with the company email address provided by HR in your offer letter (format: firstname.lastname@nordtech.ee).
3. Enter the temporary password sent to your personal email by IT. You will be prompted to set a new password immediately — this becomes your master Google Workspace password.
4. Wait for the MDM profile to install automatically. This installs baseline security policies, disk encryption, and pre-approved applications. This step can take up to 20 minutes — do not power off the laptop during this process.
5. Once setup completes, the laptop will restart automatically. Log in with your new password to reach the desktop.

If setup fails at any step, contact IT support (see Section 6) — do not attempt to reinstall macOS or reset the device yourself.

## 2. VPN Setup

All employees must connect through the company VPN when accessing internal systems (Personio, internal wikis, staging environments) from outside the office network. NordTech uses NordVPN Teams for this.

1. Open the NordVPN Teams app, which is pre-installed as part of the MDM baseline image.
2. Sign in using your NordTech Google Workspace credentials via the "Sign in with SSO" button.
3. Once signed in, select the "NordTech Internal" server profile from the dropdown — do not use a standard consumer NordVPN server, as it will not have access to internal systems.
4. Click Connect. A green icon in the menu bar confirms an active connection.
5. Test your connection by visiting wiki.nordtech.internal in your browser. If the page loads, VPN setup is complete.

VPN connection is required whenever accessing internal systems from home, while traveling, or from any non-office network.

## 3. Software to Install

The following applications are part of the standard employee toolkit and should already be present after MDM setup completes. If any are missing, install them from the internal App Catalog (Self Service on macOS, Company Portal on Windows):

- **Slack** — company communication (see Handbook for etiquette norms)
- **Notion** — internal documentation and wikis
- **Linear** — engineering/product issue tracking
- **Figma** — design collaboration (Design and Product teams; available to all on request)
- **VS Code** — default code editor for engineering roles
- **1Password** — company password manager (mandatory for all employees, see Section 5)

Do not install software from outside the App Catalog without IT approval, as unapproved software may violate the device's security policy and trigger an automatic compliance alert.

## 4. Email and Calendar Setup

NordTech uses Google Workspace for all company email and calendar functions.

1. Your email account (firstname.lastname@nordtech.ee) is created automatically before your first day as part of the pre-boarding process run by HR and IT together.
2. On first login, Gmail and Google Calendar will prompt you to accept the Google Workspace terms of service.
3. Your calendar will already show recurring invites for team standups, the company-wide Monday sync, and your onboarding sessions — these are added automatically based on your team assignment in Personio.
4. Set your calendar working hours to reflect your local time zone and typical schedule; this helps colleagues in other offices avoid booking meetings outside your hours.

## 5. Security Requirements

NordTech takes account security seriously given that employees routinely handle customer HR data.

1. **Two-factor authentication (2FA)** is mandatory on all company accounts — Google Workspace, Slack, Linear, Notion, and 1Password — and must be enabled within **24 hours** of account creation. Use an authenticator app; SMS-based 2FA is not permitted for company accounts.
2. **1Password** must be used to store all work-related passwords, including any third-party tool credentials. Do not store work passwords in browser-native password managers.
3. **Full disk encryption** is enabled automatically as part of the MDM setup in Section 1 and cannot be disabled. If you ever see a warning that disk encryption is inactive, contact IT immediately.
4. Do not share your company credentials with anyone, including other NordTech employees. Each system access request should go through the appropriate approval flow (see manager or IT support).

## 6. IT Support Contacts

- **Email:** it-support@nordtech.ee
- **Slack channel:** #it-support (fastest response during office hours)
- **Response SLA:** 4 hours for critical issues (cannot log in, device compromised, VPN completely down); 1 business day for normal requests (software install, peripheral issues, access requests)

Critical issues outside office hours should be flagged in #it-support with "URGENT" in the message, which triggers a page to the on-call IT engineer.

## 7. Equipment Ordering

Employees may order additional peripherals (monitor, keyboard, mouse, headset, docking station, etc.) through the IT equipment request form linked in #it-support.

1. Submit the equipment request form with the items and estimated cost.
2. Requests are covered by a **one-time peripherals budget of €300** per employee.
3. Any request must be **approved by your manager** before IT will place the order.
4. Approved equipment typically ships within 5 business days to your home address (remote employees) or is available for pickup at your office.

Requests exceeding the €300 budget require additional approval from your manager and Ott Rebane (Finance Manager) — see the Org Chart for contact details.

This budget covers tech peripherals only. Furniture such as desks and chairs is not ordered through IT — fully remote employees can use the separate €500 home office setup budget for that (see the Benefits & Perks Guide, Section 5).

---

*Related documents: for reimbursable expenses outside of standard IT equipment (e.g., home office furniture), see the Expense & Reimbursement Policy and the Benefits & Perks Guide. For the onboarding timeline in which this guide is used, see the Onboarding Checklist (30/60/90 Day).*
