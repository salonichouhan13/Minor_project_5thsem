# AttendIQ - Smart Attendance System (QR + Web Dashboard)

Flask + SQLite + vanilla JS. Teachers generate a time-limited QR code; students scan it on their phone and enter their Student ID.

## Run locally
```bash
cd smart-attendance
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```
Open http://localhost:5000. On first run `database.db` is created with 24 demo students and 30 days of demo attendance.

## Teacher login
- First run: open http://localhost:5000 and you are sent to **/setup** to create the teacher account (one time only).
- After that every dashboard page and API needs sign-in. Only the student scan page (`/scan/<token>`) is public.
- Passwords are hashed, 5 wrong attempts lock sign-in for 5 minutes, sessions last 8 hours. Change password in Settings.
- Deploying? Create the account **immediately** after the first deploy, or set `ADMIN_USER` and `ADMIN_PASSWORD` environment variables. Set `SECRET_KEY` and, on HTTPS, `SECURE_COOKIES=1`.
- Local debug mode: `set FLASK_DEBUG=1` (Windows) before `python app.py`.

## Student PIN and phone lock (anti-proxy)
- Students page, **Generate PINs**: creates a 4-digit PIN for every student who has none and downloads `student_pins.csv`. PINs are stored hashed, so this file (or the dialog shown after adding a student or resetting a PIN) is the only time you see them. Give each student only their own.
- To scan, a student enters Student ID + PIN. The first successful scan links that phone to them. After that:
  - their account only works from that phone,
  - that phone cannot mark anyone else.
- Phone changed or PIN forgotten? Open the student, then **Reset PIN** or **Unlink phone**.
- 5 wrong attempts on one Student ID, or 15 from one IP, locks scanning for 10 minutes. Teachers get a Security alert.
- Honest limits: a student who sends the QR photo or link to a friend can still let that friend mark their **own** attendance from outside the class. Keep the QR window short and regenerate it. Stronger fixes: a QR that rotates every ~20 seconds, or a location check.

## Try the full flow
1. Open **Generate QR**, pick a class and duration, press **Generate QR**.
2. Phone and laptop must be on the **same Wi-Fi**. The QR contains your laptop's LAN IP, so the phone opens the scan page directly.
   No phone handy? Open the link shown under the QR in another tab.
3. Click **Generate PINs** on the Students page first. Then enter a Student ID (demo IDs: CS24001 to CS24024) and that student's PIN from the CSV.
4. Watch Dashboard, Attendance and Recent Activity update. Scanning twice shows a duplicate warning; scanning after expiry is rejected.

## Notes
- Charts, icons and fonts load from CDNs, so the dashboard needs internet access.
- If the phone cannot open the link, allow Python through your firewall (port 5000).
- To reset all data, stop the server and delete `database.db`.

## Structure
`app.py` routes + API and validation | `utils/db.py` schema and seed | `utils/helpers.py` QR image + LAN IP | `templates/` pages | `static/css/style.css` theme | `static/js/app.js` page logic
