from flask import Flask, json, render_template
import pandas as pd
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
load_dotenv()

app = Flask(__name__)

SHEET_ID          = "1DMGk4L_WQ0kFrOXHPO-gbkPrFFG02-9I3ZV01AtogLo"
DOUBT_SHEET_ID    = "1NwG9FxQq0Yxugrs2z5RWcG2YMd17Nc2Js4ygJZAllhk"
LIVEEVAL_SHEET_ID = "1e4JrN1pXa-cfr1f1Rshyg0w9VCz5GEkHliIMCDq8eLE"
SESSIONS_SHEET_ID = "113k5JzTSIZknYzLZFnj0lc20Zdcw0svkK3S8R3J8FDI"
TRACKER_SHEET_ID  = "1igZAYA3wT7Yt_oFdkbA459KMAEqa4jJ8J3QC_KOplis"        


# ── helper: authenticate once, reuse ──
def get_client():
    creds_dict = json.loads(os.environ["GOOGLE_CREDS"])
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


# ── load function ──
def load_df():
    client = get_client()
    sheet = client.open_by_key(SHEET_ID)
    worksheet = sheet.sheet1
    data = worksheet.get_all_values()
    headers = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=headers)
    df.columns = df.columns.str.strip()
    df = df.fillna("")
    df = df[['Date', 'Query No', 'Mentor', 'Status', 'Product',
             'Batch Code', 'Query Type', 'Mail Id', 'Time Taken']]
    # Queries sheet date format: "10-Apr-2026" (d-Mon-yyyy)
    df['Date'] = pd.to_datetime(df['Date'].astype(str).str.strip(), format='%d-%b-%Y', errors='coerce')
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')

    def convert_time(text):
        if not text or str(text).strip() == "":
            return None   # excluded from mean — not a real zero
        text = str(text).strip()
        days    = re.search(r'(\d+)\s*day', text)
        hours   = re.search(r'(\d+)\s*hr', text)
        minutes = re.search(r'(\d+)\s*min', text)
        total = 0
        if days:    total += int(days.group(1)) * 1440
        if hours:   total += int(hours.group(1)) * 60
        if minutes: total += int(minutes.group(1))
        return total if total > 0 else None   # no pattern matched → exclude

    df['time_minutes'] = df['Time Taken'].apply(convert_time)
    return df


# ── NEW: load Project Doubt Session sheet (Image 1: Date, Mentor, Count) ──
# Change the worksheet name below to match your actual sheet tab name
def load_doubt_df():
    try:
        client = get_client()
        sheet = client.open_by_key(DOUBT_SHEET_ID)
        worksheet = sheet.sheet1  # first tab of the doubt session sheet
        data = worksheet.get_all_values()
        headers = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
        df.columns = df.columns.str.strip()
        df = df.fillna("")
        # Keep Date, Mentor, Count columns
        df = df[['Date', 'Mentor', 'Count']]
        # Doubt sheet date format: "01/12/2025" (dd/mm/yyyy)
        df['Date']  = pd.to_datetime(df['Date'].astype(str).str.strip(), dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
        df['Count'] = pd.to_numeric(df['Count'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        print(f"Doubt sheet load error: {e}")
        return pd.DataFrame(columns=['Date', 'Mentor', 'Count'])


# ── NEW: load Project Live Evaluation sheet (Image 2: Date, Zen portal, Mentor) ──
# Change the worksheet name below to match your actual sheet tab name
def load_liveeval_df():
    try:
        client = get_client()
        sheet = client.open_by_key(LIVEEVAL_SHEET_ID)
        worksheet = sheet.worksheet("May 2026")  # first tab of the live eval sheet
        data = worksheet.get_all_values()
        headers = data[1]
        rows = data[2:]
        df = pd.DataFrame(rows, columns=headers)
        df.columns = df.columns.str.strip()
        df = df.fillna("")
        # Keep only Date, Zen portal, Mentor (as seen in Image 2)
        df = df[['Date', 'Zen portal', 'Mentor']]
        # Evaluation sheet date format: "01/04/2026 - (Wednesday)" — extract dd/mm/yyyy part
        df['Date'] = df['Date'].astype(str).str.extract(r'(\d{2}/\d{2}/\d{4})')[0]
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        print(f"Live eval sheet load error: {e}")
        return pd.DataFrame(columns=['Date', 'Zen portal', 'Mentor'])


# ── your original build_context, unchanged ──
def build_context(df):
    total_queries  = len(df)
    closed_queries = len(df[df['Status'].str.lower() == 'closed'])
    total_mentors  = df['Mentor'].nunique()
    avg_time = int(df['time_minutes'].dropna().mean()) if df['time_minutes'].notna().any() else 0

    mentor_counts = df['Mentor'].value_counts().to_dict()
    mentor_labels = list(mentor_counts.keys())
    mentor_values = [int(x) for x in mentor_counts.values()]

    daily_trend = df.groupby('Date').size()
    date_labels = list(daily_trend.index)
    date_values = [int(x) for x in daily_trend.values]

    status_counts = df['Status'].value_counts().to_dict()
    status_labels = list(status_counts.keys())
    status_values = [int(x) for x in status_counts.values()]

    unique_dates  = sorted([d for d in df['Date'].dropna().astype(str).unique() if d and d not in ('NaT', 'nan', '')])
    data_records  = df.to_dict(orient='records')
    mentors       = df['Mentor'].dropna().unique().tolist()

    mentor_stats = []
    for m in df['Mentor'].unique():
        if not m:
            continue
        mdf = df[df['Mentor'] == m]
        mentor_stats.append({
            'name':       m,
            'total':      len(mdf),
            'closed':     len(mdf[mdf['Status'].str.lower() == 'closed']),
            'avg_time':   int(mdf['time_minutes'].dropna().mean()) if mdf['time_minutes'].notna().any() else 0,
            'close_rate': round(len(mdf[mdf['Status'].str.lower() == 'closed']) / len(mdf) * 100, 1) if len(mdf) > 0 else 0,
        })
    mentor_stats.sort(key=lambda x: x['total'], reverse=True)

    return dict(
        records        = data_records,
        mentors        = mentors,
        mentor_stats   = mentor_stats,
        unique_dates   = unique_dates,
        total_queries  = total_queries,
        closed_queries = closed_queries,
        total_mentors  = total_mentors,
        avg_time       = avg_time,
        mentor_labels  = mentor_labels,
        mentor_values  = mentor_values,
        date_labels    = date_labels,
        date_values    = date_values,
        status_labels  = status_labels,
        status_values  = status_values,
    )


# ── load Sessions sheet ──
def load_sessions_df():
    """Sessions sheet — columns: Date, Session Name, Mentor Name, Hosted by."""
    try:
        client    = get_client()
        sheet     = client.open_by_key(SESSIONS_SHEET_ID)
        worksheet = sheet.worksheet("Sessions-2026")
        data      = worksheet.get_all_values()
        headers   = data[1]
        rows      = data[2:]
        df        = pd.DataFrame(rows, columns=headers)
        df.columns = df.columns.str.strip()
        df = df.fillna("")
        df = df[['Date', 'Session Name', 'Mentor Name', 'Hosted by']]
        # Sessions sheet date format: "2-Mar-2026" (d-Mon-yyyy)
        df['Date']  = pd.to_datetime(df['Date'].astype(str).str.strip(), format='%d-%b-%Y', errors='coerce')
        df['Month'] = df['Date'].dt.strftime('%B')
        df['Year']  = df['Date'].dt.year.astype(str)
        df['Date']  = df['Date'].dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        print(f"Sessions sheet load error: {e}")
        return pd.DataFrame(columns=['Date', 'Session Name', 'Mentor Name', 'Hosted by', 'Month', 'Year'])


# ── ROUTES ──
@app.route("/")
def home():
    df  = load_df()
    ctx = build_context(df)
    return render_template("home.html", **ctx)


REPORT_MENTORS = [
    "Nandini", "Anitha", "shagufta", "NEHLATH", "shadiya", "Asvin",
    "Vinodhini", "Nilofer", "Subhash", "Kirti Gupta", "Vignesh",
    "Selvamani", "Nikhat Riyaz", "Gangatharam", "lokesh","Selva Ganapathy",
    "Arunraj","Geetha"
]


@app.route("/reports")
def reports():
    from flask import request
    date_from     = request.args.get("date_from", "").strip()
    date_to       = request.args.get("date_to", "").strip()
    mentor_filter = request.args.get("mentor", "all").strip()

    df          = load_df()
    doubt_df    = load_doubt_df()
    liveeval_df = load_liveeval_df()
    sessions_df = load_sessions_df()
    tracker_df  = load_tracker_df()

    # Apply date filters
    def filter_by_date(frame, date_col="Date"):
        f = frame.copy()
        if date_from:
            f = f[f[date_col].astype(str) >= date_from]
        if date_to:
            f = f[f[date_col].astype(str) <= date_to]
        return f

    df_f          = filter_by_date(df)
    doubt_f       = filter_by_date(doubt_df)
    liveeval_f    = filter_by_date(liveeval_df)
    sessions_f    = filter_by_date(sessions_df)

    # Tracker uses Assigned Date
    tracker_f = tracker_df.copy()
    if not tracker_f.empty and "Assigned Date" in tracker_f.columns:
        if date_from:
            tracker_f = tracker_f[tracker_f["Assigned Date"].dt.strftime("%Y-%m-%d") >= date_from]
        if date_to:
            tracker_f = tracker_f[tracker_f["Assigned Date"].dt.strftime("%Y-%m-%d") <= date_to]

    # Build per-mentor report for allowed mentors only
    mentors_to_show = [m for m in REPORT_MENTORS]
    if mentor_filter != "all":
        mentors_to_show = [m for m in mentors_to_show if m == mentor_filter]

    reports_data = []
    for mentor in mentors_to_show:
        mq  = df_f[df_f["Mentor"] == mentor]
        md  = doubt_f[doubt_f["Mentor"] == mentor]
        ml  = liveeval_f[liveeval_f["Mentor"] == mentor]
        ms  = sessions_f[sessions_f["Mentor Name"] == mentor]
        mt  = tracker_f[tracker_f["Mentor"] == mentor] if not tracker_f.empty else pd.DataFrame()

        closed = len(mq[mq["Status"].str.lower() == "closed"])
        open_q = len(mq[mq["Status"].str.lower().isin(["open", ""])])
        times  = mq["time_minutes"].dropna()
        avg_t  = int(times.mean()) if len(times) > 0 else 0

        # Query details list (for table in reports page)
        query_records = []
        for _, row in mq.iterrows():
            status_val = row.get("Status", "").strip()
            if not status_val:
                status_val = "Unassigned"
            query_records.append({
                "date":       row.get("Date", ""),
                "query_no":   row.get("Query No", ""),
                "product":    row.get("Product", ""),
                "query_type": row.get("Query Type", ""),
                "status":     status_val,
                "time_taken": row.get("Time Taken", ""),
            })

        # Project eval count & status breakdown
        liveeval_count = len(ml)
        liveeval_status = {}
        if not ml.empty and "Zen portal" in ml.columns:
            liveeval_status = ml["Zen portal"].value_counts().to_dict()

        # Projects assigned from tracker
        projects_assigned = len(mt) if not mt.empty else 0

        session_types = {}
        if not ms.empty and "Session Name" in ms.columns:
            session_types = ms["Session Name"].value_counts().to_dict()

        reports_data.append({
            "mentor":           mentor,
            "total_queries":    len(mq),
            "closed_queries":   closed,
            "open_queries":     open_q,
            "close_rate":       round(closed / len(mq) * 100, 1) if len(mq) > 0 else 0,
            "avg_time":         avg_t,
            "doubt_learners":   int(md["Count"].sum()) if not md.empty else 0,
            "live_evals":       liveeval_count,
            "liveeval_status":  liveeval_status,
            "sessions_count":   len(ms),
            "session_types":    session_types,
            "projects_assigned": projects_assigned,
            "query_records":    query_records,
        })

    # Only keep mentors with at least some data
    reports_data = [r for r in reports_data if
                    r["total_queries"] > 0 or r["doubt_learners"] > 0 or
                    r["live_evals"] > 0 or r["sessions_count"] > 0 or r["projects_assigned"] > 0]

    return render_template("reports.html",
        reports       = reports_data,
        all_mentors   = REPORT_MENTORS,
        date_from     = date_from,
        date_to       = date_to,
        mentor_filter = mentor_filter,
    )


# ── DELETED mentors route ──
# The /mentors page has been removed. Mentor data is now shown
# directly in /queries and /projects pages.
# Keeping this comment as a placeholder so nothing breaks.
# mentors() route removed — data lives in /queries and /projects


# ── NEW: Queries page (query-focused analytics) ──
@app.route("/queries")
def queries():
    df  = load_df()
    ctx = build_context(df)
    return render_template("queries.html", **ctx)


# ── NEW: Projects page (doubt sessions + live eval) ──
@app.route("/projects")
def projects():
    df          = load_df()
    ctx         = build_context(df)
    doubt_df    = load_doubt_df()
    liveeval_df = load_liveeval_df()

    # Raw records for JS-side filtering
    ctx['doubt_records']   = doubt_df.to_dict(orient='records')
    ctx['liveeval_records'] = liveeval_df.to_dict(orient='records')

    # All unique dates for the date filter dropdown (union of both sheets)
    all_doubt_dates = sorted(doubt_df['Date'].dropna().unique().tolist())
    ctx['all_doubt_dates'] = all_doubt_dates

    # Summary KPIs
    ctx['doubt_total_sessions'] = len(doubt_df)
    ctx['doubt_total_learners'] = int(doubt_df['Count'].sum()) if not doubt_df.empty else 0
    ctx['liveeval_total']       = len(liveeval_df)

    # Keep existing per-mentor dicts for backward compat
    doubt_by_mentor = {}
    liveeval_by_mentor = {}
    for mentor in ctx['mentors']:
        try:
            mdf = doubt_df[doubt_df['Mentor'] == mentor]
            doubt_by_mentor[mentor] = {
                'dates':  mdf['Date'].tolist(),
                'counts': mdf['Count'].tolist(),
            }
        except Exception:
            doubt_by_mentor[mentor] = {'dates': [], 'counts': []}
        try:
            mdf    = liveeval_df[liveeval_df['Mentor'] == mentor]
            status = mdf['Zen portal'].value_counts().to_dict()
            liveeval_by_mentor[mentor] = {
                'labels': list(status.keys()),
                'values': [int(v) for v in status.values()],
            }
        except Exception:
            liveeval_by_mentor[mentor] = {'labels': [], 'values': []}

    ctx['doubt_by_mentor']    = doubt_by_mentor
    ctx['liveeval_by_mentor'] = liveeval_by_mentor

    return render_template("projects.html", **ctx)



# ── NEW: Sessions page ──
@app.route("/sessions")
def sessions():
    df  = load_df()
    ctx = build_context(df)
    sessions_df = load_sessions_df()

    ctx['sessions_records']  = sessions_df.to_dict(orient='records')
    ctx['session_names']     = sorted(sessions_df['Session Name'].dropna().unique().tolist())
    ctx['session_mentors']   = sorted(sessions_df['Mentor Name'].dropna().unique().tolist())
    ctx['session_hosts']     = sorted(sessions_df['Hosted by'].dropna().unique().tolist())
    ctx['session_months']    = sorted(sessions_df['Month'].dropna().unique().tolist())
    ctx['session_years']     = sorted(sessions_df['Year'].dropna().unique().tolist())
    ctx['sessions_total']    = len(sessions_df)
    ctx['sessions_mentors_count'] = sessions_df['Mentor Name'].nunique()
    ctx['sessions_types_count']   = sessions_df['Session Name'].nunique()
    ctx['sessions_hosts_count']   = sessions_df['Hosted by'].nunique()

    return render_template("sessions.html", **ctx)



# ════════════════════════════════════════════════════════════
#                      TRACKER CONFIG
# ════════════════════════════════════════════════════════════


# ── Two managers — both receive all alerts ──
MANAGER_EMAILS = [
    "nehlath@hclguvi.com",
    "amitkumar@hclguvi.com"
]

MENTOR_EMAILS = {
    "shadiya":      "shadiya@hclguvi.com",
    "NEHLATH":      "nehlath@hclguvi.com",
    "Gomathi":      "gomathi@hclguvi.com",
    "Nilofer":      "nilofer.mubeen@hclguvi.com",
    "Asvin":        "asvin@hclguvi.com",
    "Vinodhini":    "vinodhini@hclguvi.com",
    "Subhash":      "subhash.govindharaj@hclguvi.com",
    "Kirti Gupta":  "kirti.gupta@hclguvi.com",
    "Vignesh":      "vignesh.p@hclguvi.com",
    "Selvamani":    "selvamani.a@hclguvi.com",
    "Nikhat Riyaz": "nikhat.begum@hclguvi.com",
    "Gangatharam":  "gangatharam@hclguvi.com",
    "lokesh":       "lokesh@hclguvi.com",
}

SMTP_FROM = "nilofer.mubeen@hclguvi.com"


# ── email helper (SendGrid — works on Render) ──
def send_email(to_list, subject, body):
    """Send a plain-text email via SendGrid HTTP API. to_list is a list of address strings."""
    import urllib.request, urllib.error, json as _json

    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
    print(f"[EMAIL] Attempting -> to={to_list} via SendGrid")

    if not SENDGRID_API_KEY:
        print("[EMAIL ERROR] SENDGRID_API_KEY env var not set")
        return False

    try:
        payload = _json.dumps({
            "personalizations": [{"to": [{"email": addr} for addr in to_list]}],
            "from": {"email": SMTP_FROM},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[EMAIL SENT] SUCCESS to={to_list} | subject={subject} | status={resp.status}")
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"[EMAIL ERROR] HTTPError {e.code}: {err_body}")
        return False
    except Exception as e:
        print(f"[EMAIL ERROR] {type(e).__name__}: {e}")
        return False


# ── load tracker sheet (both tabs combined) ──
def load_tracker_df():
    try:
        client = get_client()
        sheet  = client.open_by_key(TRACKER_SHEET_ID)
        frames = []

        # data_start_row = the first row of actual tracker data (1-indexed, as in Google Sheets)
        tab_config = {
            "Data Science": 1007,
            "AI ML":        100,
        }

        for tab_name, data_start_row in tab_config.items():
            try:
                ws = sheet.worksheet(tab_name)

                # Get headers from row 1 and deduplicate
                raw_headers = [h.strip() for h in ws.row_values(1)]

                seen = {}
                headers = []
                for h in raw_headers:
                    if h in seen:
                        seen[h] += 1
                        headers.append(f"{h}_{seen[h]}")
                    else:
                        seen[h] = 1
                        headers.append(h)

                print(f"[TRACKER] '{tab_name}' headers after dedup: {headers}")

                # Get only the actual data rows using a specific range
                last_col_letter = chr(ord('A') + len(headers) - 1)
                range_str = f"A{data_start_row}:{last_col_letter}"
                rows = ws.get(range_str)

                print(f"[TRACKER] '{tab_name}': {len(rows)} rows fetched from row {data_start_row}")

                if not rows:
                    print(f"[TRACKER] '{tab_name}': No data found in range {range_str}")
                    continue

                df_tab = pd.DataFrame(rows, columns=headers[:len(rows[0])])
                df_tab.columns = df_tab.columns.str.strip()
                df_tab = df_tab.fillna("")

                # Drop rows where Batch is empty (trailing empty rows)
                if 'Batch' in df_tab.columns:
                    df_tab = df_tab[df_tab['Batch'].str.strip() != '']

                print(f"[TRACKER] '{tab_name}': {len(df_tab)} clean rows")
                df_tab["Sheet"] = tab_name
                frames.append(df_tab)

            except Exception as e:
                import traceback
                print(f"[TRACKER] Tab '{tab_name}' error: {e}")
                traceback.print_exc()

        if not frames:
            print("[TRACKER ERROR] No frames loaded")
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        df.columns = df.columns.str.strip()
        df = df.fillna("")

        needed = ["S.No", "Batch", "Mode", "Language", "Project Number",
                  "Project Title", "Assigned Date", "Deadline Date",
                  "Assigned by", "Mentor", "Sheet"]

        missing = [c for c in needed if c not in df.columns]
        if missing:
            print(f"[TRACKER WARNING] Missing columns: {missing}")
            print(f"[TRACKER] Available columns: {df.columns.tolist()}")

        df = df[[c for c in needed if c in df.columns]]
        df["Assigned Date"] = pd.to_datetime(df["Assigned Date"], dayfirst=True, errors="coerce")
        df["Deadline Date"] = pd.to_datetime(df["Deadline Date"], dayfirst=True, errors="coerce")

        def norm_mode(m):
            m2 = str(m).strip().upper()
            if m2.startswith("WE") or m2 == "WEEKEND":
                return "Weekend"
            return "Weekday"

        df["Mode_Simple"] = df["Mode"].apply(norm_mode)
        print(f"[TRACKER] Final combined rows: {len(df)}")
        return df

    except Exception as e:
        import traceback
        print(f"[TRACKER ERROR] {e}")
        traceback.print_exc()
        return pd.DataFrame()


# ── alert logic ──
_alert_log = []   # in-memory log: [{type, batch, mentor, detail, sent_at}]
_last_alert_run_date = None  # gate: ensures mails fire only once per day

# AlertLog lives in the Tracker sheet as a sub-sheet called "AlertLog"
ALERT_LOG_SHEET_ID = TRACKER_SHEET_ID
ALERT_LOG_TAB      = "AlertLog"
ALERT_LOG_HEADERS  = ["sent_at", "type", "sheet", "batch", "mentor", "detail", "email_to", "sent", "dedup_key"]

def _get_write_client():
    """Authenticate with write scope for AlertLog operations."""
    creds_dict = json.loads(os.environ["GOOGLE_CREDS"])
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def _load_sent_keys():
    """Load already-sent alert dedup keys from the AlertLog sheet."""
    try:
        client = _get_write_client()
        ws     = client.open_by_key(ALERT_LOG_SHEET_ID).worksheet(ALERT_LOG_TAB)
        rows   = ws.get_all_values()
        if len(rows) <= 1:
            return set()   # only header or empty
        headers = rows[0]
        try:
            key_col = headers.index("dedup_key")
        except ValueError:
            print("[ALERT DEDUP] 'dedup_key' column not found in AlertLog sheet")
            return set()
        sent_keys = set()
        for row in rows[1:]:
            if len(row) > key_col and row[key_col].strip():
                sent_keys.add(row[key_col].strip())
        print(f"[ALERT DEDUP] Loaded {len(sent_keys)} sent keys from AlertLog sheet")
        return sent_keys
    except Exception as e:
        print(f"[ALERT DEDUP] Could not load sent keys from sheet: {e}")
        return set()

def _append_alert_log_row(entry, dedup_key_str):
    """Append one alert entry as a new row in the AlertLog sheet."""
    try:
        client = _get_write_client()
        ws     = client.open_by_key(ALERT_LOG_SHEET_ID).worksheet(ALERT_LOG_TAB)
        # Ensure header row exists
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(ALERT_LOG_HEADERS, value_input_option="RAW")
        row = [
            entry.get("sent_at", ""),
            entry.get("type", ""),
            entry.get("sheet", ""),
            entry.get("batch", ""),
            entry.get("mentor", ""),
            entry.get("detail", ""),
            entry.get("email_to", ""),
            "TRUE" if entry.get("sent") else "FALSE",
            dedup_key_str,
        ]
        ws.append_row(row, value_input_option="RAW")
        print(f"[ALERT LOG] Appended row to AlertLog sheet: {dedup_key_str}")
    except Exception as e:
        print(f"[ALERT LOG] Could not append to AlertLog sheet: {e}")

def run_tracker_alerts(from_cron=False):

    global _alert_log, _last_alert_run_date
    if from_cron:
        today_str = datetime.now().strftime("%Y-%m-%d")
        if _last_alert_run_date == today_str:
            print(f"[ALERT] Already ran today ({today_str}). Skipping to prevent duplicate mails.")
            return
        _last_alert_run_date = today_str
    df = load_tracker_df()
    if df.empty:
        return
    today     = pd.Timestamp(datetime.now().date())
    today_str = today.strftime("%Y-%m-%d")

    # Load persisted sent keys from AlertLog sheet (strings)
    sent_keys = _load_sent_keys()

    # ── 1. Deadline alerts (Projects 1–5 only; Final project skipped) ──
    deadline_rows = df[df["Deadline Date"].dt.normalize() == today]
    for _, row in deadline_rows.iterrows():
        mentor  = row.get("Mentor", "").strip()
        batch   = row.get("Batch", "")
        proj    = row.get("Project Title", "")
        proj_no = str(row.get("Project Number", "")).strip()
        match = re.search(r'\d+', proj_no)

        # ── Skip Final project — no alert needed ──
        if str(proj).strip().lower() == "final":
            print(f"[ALERT] Skipping Final project deadline for batch {batch}")
            continue

        # ── Only alert for projects 1–5 ──
        try:
            proj_num = int(match.group())
        except (ValueError, TypeError):
            print(f"[ALERT] Could not parse Project Number '{proj_no}' for batch {batch}, skipping.")
            continue

        if proj_num > 5:
            print(f"[ALERT] Project Number {proj_num} > 5, skipping for batch {batch}")
            continue

        # ── Build "next step" message based on project number ──
        if proj_num <= 4:
            next_proj_label  = f"Project {proj_num + 1}"
            next_action_line = f"✅ Plan and assign {next_proj_label} for Batch {batch}"
            next_action_body = f"Please plan and assign {next_proj_label} for this batch."
        else:  # proj_num == 5
            next_proj_label  = "the Final Project"
            next_action_line = f"✅ It's time to assign the Final Project for Batch {batch}"
            next_action_body = f"Project 5 deadline is today. Please assign the Final Project for this batch."

        # Build a unique key for this alert — skip if already sent today
        dedup_key = f"{today_str}|Deadline|{batch}|{proj}"
        if dedup_key in sent_keys:
            print(f"[ALERT DEDUP] Skipping already-sent alert: {dedup_key}")
            continue
        sent_keys.add(dedup_key)

        email   = MENTOR_EMAILS.get(mentor)
        to_list = [e for e in ([email] + MANAGER_EMAILS) if e]

        subject = f"[MentorHub] ⏰ Deadline Today: {batch} – {proj}"
        body = (
            f"Hi {mentor},\n\n"
            f"This is an automated alert from MentorHub.\n\n"
            f"Today is the deadline for the project below. Please take action:\n\n"
            f"  ✅ Check the sessions\n"
            f"  ✅ Complete the class tracking\n"
            f"  {next_action_line}\n\n"
            f"  Batch         : {batch}\n\n"
            f"  Project Title : {proj}\n\n"
            f"  Project Number: {proj_no}\n\n"
            f"  Deadline Date : {row['Deadline Date'].strftime('%d/%m/%Y')}\n\n"
            f"  Mentor        : {mentor}\n\n"
            f"{next_action_body}\n\n\n"
            f"Please ensure everything is in order before end of day.\n\n"
            f"Regards,\nMentorHub"
        )
        sent = False
        if to_list:
            sent = send_email(to_list, subject, body)
        entry = {
            "type":     "Deadline",
            "sheet":    row.get("Sheet", ""),
            "batch":    batch,
            "mentor":   mentor,
            "detail":   f"{proj} — deadline today",
            "email_to": ", ".join(to_list) if to_list else "NOT CONFIGURED",
            "sent":     sent,
            "sent_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _alert_log.append(entry)
        _append_alert_log_row(entry, dedup_key)

    # ── 2. Final-project out-of-order alerts ──
    # Only consider 2026+ data. Only send email if the Final was assigned
    # AFTER today (i.e. a newly assigned batch, not a historical one).
    cutoff_2026 = pd.Timestamp("2026-01-01")
    for (sheet_name, batch), grp in df.groupby(["Sheet", "Batch"]):
        grp = grp.dropna(subset=["Assigned Date"])
        # Restrict to 2026+ rows only
        grp = grp[grp["Assigned Date"] >= cutoff_2026]
        final_rows = grp[grp["Project Title"].str.strip().str.lower() == "final"]
        other_rows = grp[grp["Project Title"].str.strip().str.lower() != "final"]
        if final_rows.empty or other_rows.empty:
            continue
        final_date = final_rows["Assigned Date"].min()
        # Skip old batches — only alert if the Final was assigned AFTER today
        if final_date <= today:
            continue
        # alert if Final was assigned before the latest numbered project
        if final_date < other_rows["Assigned Date"].max():
            # Dedup: only send once per (batch, sheet) — not tied to today's date
            dedup_key = f"OOO|{sheet_name}|{batch}"
            if dedup_key in sent_keys:
                print(f"[ALERT DEDUP] Skipping already-sent OOO alert: {dedup_key}")
                continue
            sent_keys.add(dedup_key)

            mentor   = grp["Mentor"].iloc[0].strip()
            m_email  = MENTOR_EMAILS.get(mentor)
            to_list  = [e for e in ([m_email] + MANAGER_EMAILS) if e]
            subject  = f"[MentorHub] ⚠️ Final Project Assigned Out of Order: {batch}"
            body = (
                f"Hi,\n\n"
                f"This is an automated alert from MentorHub.\n\n"
                f"The FINAL project for batch '{batch}' (Sheet: {sheet_name}) "
                f"appears to have been assigned BEFORE some preceding projects.\n\n"
                f"  Batch         : {batch}\n"
                f"  Mentor        : {mentor}\n"
                f"  Final Assigned: {final_date.strftime('%d/%m/%Y')}\n\n"
                f"Please review and correct the assignment order.\n\nRegards,\nMentorHub"
            )
            sent = False
            if to_list:
                sent = send_email(to_list, subject, body)
            entry = {
                "type":     "Out-of-Order Final",
                "sheet":    sheet_name,
                "batch":    batch,
                "mentor":   mentor,
                "detail":   f"Final assigned {final_date.strftime('%d/%m/%Y')} before other projects",
                "email_to": ", ".join(to_list) if to_list else "NOT CONFIGURED",
                "sent":     sent,
                "sent_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            _alert_log.append(entry)
            _append_alert_log_row(entry, dedup_key)

    print(f"[ALERT DEDUP] Session complete. {len(sent_keys)} total keys tracked via AlertLog sheet.")


# ── build tracker context ──
def build_tracker_ctx(df):
    if df.empty:
        return {"tracker_empty": True, "tracker_records": []}

    records = []
    for _, r in df.iterrows():
        rec = {}
        for col in df.columns:
            val = r[col]
            if pd.isna(val):
                rec[col] = ""
            elif isinstance(val, pd.Timestamp):
                rec[col] = val.strftime("%Y-%m-%d")
            else:
                rec[col] = str(val)
        records.append(rec)

    mentors   = sorted(df["Mentor"].dropna().unique().tolist())
    languages = sorted(df["Language"].dropna().unique().tolist())
    sheets    = sorted(df["Sheet"].dropna().unique().tolist())

    # chart 1 — project title vs no of batches
    title_batch = (
        df[df["Project Title"].str.strip().str.lower() != "final"]
        .groupby("Project Title")["Batch"].nunique()
        .sort_values(ascending=False)
        .head(20)
    )
    # chart 2 — unique project titles per mentor
    mentor_proj = (
        df[df["Project Title"].str.strip().str.lower() != "final"]
        .groupby("Mentor")["Project Title"].nunique()
        .sort_values(ascending=False)
    )
    # chart 3 — batches per mentor × language (stacked)
    lang_pivot = (
        df.groupby(["Mentor", "Language"])["Batch"]
        .nunique().reset_index(name="count")
    )
    # chart 4 — weekend vs weekday
    mode_counts = df["Mode_Simple"].value_counts().to_dict()
    # chart 5 — assigned by
    assigned_counts = df["Assigned by"].value_counts().to_dict()
    # chart 6 — batches per mentor × mode (stacked)
    mode_pivot = (
        df.groupby(["Mentor", "Mode_Simple"])["Batch"]
        .nunique().reset_index(name="count")
    )
    # chart 7 — batch completion
    total_per_batch   = df.groupby(["Sheet", "Batch"])["Project Number"].count()
    assigned_per_batch = df.groupby(["Sheet", "Batch"])["Assigned Date"].apply(
        lambda s: s.notna().sum()
    )
    completion = pd.DataFrame({"total": total_per_batch, "assigned": assigned_per_batch}).reset_index()
    completion["label"] = completion["Sheet"].str[:2] + "·" + completion["Batch"]

    # deadline alerts preview
    today = pd.Timestamp(datetime.now().date())
    deadline_today = df[df["Deadline Date"].dt.normalize() == today]

    # out-of-order final preview — 2026 data only
    cutoff_2026 = pd.Timestamp("2026-01-01")
    ooo_batches = []
    for (sn, batch), grp in df.groupby(["Sheet", "Batch"]):
        grp2 = grp.dropna(subset=["Assigned Date"])
        # Restrict to rows assigned in 2026 or later
        grp2 = grp2[grp2["Assigned Date"] >= cutoff_2026]
        finals = grp2[grp2["Project Title"].str.strip().str.lower() == "final"]
        others = grp2[grp2["Project Title"].str.strip().str.lower() != "final"]
        if finals.empty or others.empty:
            continue
        if finals["Assigned Date"].min() < others["Assigned Date"].max():
            ooo_batches.append({
                "sheet": sn, "batch": batch,
                "mentor": grp2["Mentor"].iloc[0],
                "final_date": finals["Assigned Date"].min().strftime("%d/%m/%Y"),
            })

    return dict(
        tracker_empty        = False,
        tracker_records      = records,
        mentors              = mentors,
        languages            = languages,
        sheets               = sheets,
        total_batches        = int(df["Batch"].nunique()),
        total_projects       = len(df),
        total_mentors        = int(df["Mentor"].nunique()),
        total_langs          = int(df["Language"].nunique()),
        # chart 1
        title_labels         = title_batch.index.tolist(),
        title_values         = [int(x) for x in title_batch.values],
        # chart 2
        mentor_proj_labels   = mentor_proj.index.tolist(),
        mentor_proj_values   = [int(x) for x in mentor_proj.values],
        # chart 3 — lang stacked
        lang_pivot           = lang_pivot.to_dict(orient="records"),
        lang_list            = sorted(df["Language"].dropna().unique().tolist()),
        # chart 4
        mode_labels          = list(mode_counts.keys()),
        mode_values          = [int(v) for v in mode_counts.values()],
        # chart 5
        assigned_labels      = list(assigned_counts.keys()),
        assigned_values      = [int(v) for v in assigned_counts.values()],
        # chart 6 — mode stacked
        mode_pivot           = mode_pivot.to_dict(orient="records"),
        mode_list            = ["Weekend", "Weekday"],
        # chart 7
        completion_labels    = completion["label"].tolist(),
        completion_total     = [int(x) for x in completion["total"].tolist()],
        completion_assigned  = [int(x) for x in completion["assigned"].tolist()],
        # alerts
        deadline_today       = deadline_today[["Sheet", "Batch", "Project Title", "Mentor", "Deadline Date"]].to_dict(orient="records") if not deadline_today.empty else [],
        ooo_batches          = ooo_batches,
    )


# ── ROUTES ──
@app.route("/tracker")
def tracker():
    df  = load_tracker_df()
    ctx = build_tracker_ctx(df)
    return render_template("tracker.html", **ctx)

@app.route("/tracker-alerts")
def tracker_alerts():
    df  = load_tracker_df()
    ctx = build_tracker_ctx(df)
    ctx["alert_log"] = list(reversed(_alert_log))   # newest first
    return render_template("tracker_alerts.html", **ctx)


@app.route("/test-email")
def test_email():
    """Hit this URL to send a quick test email to all managers."""
    ok = send_email(
        MANAGER_EMAILS,
        "[MentorHub] Test Email",
        "This is a test email from MentorHub.\n\nIf you receive this, SMTP is working correctly."
    )
    return f"<pre>Email {'SENT OK' if ok else 'FAILED — check Render logs'}</pre>"


@app.route("/run-alerts")
def manual_run_alerts():
    """Trigger alert check (cron-safe).
    Use ?cron=true for cron jobs.
    Runs in background and returns immediately."""

    from flask import request
    import threading
    import sys
    import os

    from_cron = request.args.get("cron", "").lower() == "true"

    def run_in_bg():
        try:
            # 🔥 CRITICAL FIX: suppress ALL output during cron
            if from_cron:
                sys.stdout = open(os.devnull, 'w')
                sys.stderr = open(os.devnull, 'w')

            run_tracker_alerts(from_cron=from_cron)

        except Exception:
            # do nothing (avoid printing errors in cron)
            pass

    t = threading.Thread(target=run_in_bg, daemon=True)
    t.start()

    # 🔥 MUST BE SMALL RESPONSE
    return "OK", 200


if __name__ == "__main__":
    app.run(debug=True)
