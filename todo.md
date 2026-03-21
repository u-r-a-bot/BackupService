# PGSafe — Scheduled Backup Feature TODO

## Architecture Decision: Hybrid Approach

Combine **System Tray** (primary) with **Windows Task Scheduler via schtasks.exe** (fallback).
No Python installation required on client machines. Single exe handles everything.

---

## Why Hybrid

| Scenario | Tray App | Task Scheduler | Hybrid |
|---|---|---|---|
| Laptop sleeping (common) | ✅ | ✅ | ✅ |
| App fully closed | ❌ | ✅ | ✅ |
| After reboot, app not re-opened | ❌ | ✅ | ✅ |
| User sees live status | ✅ | ❌ | ✅ |
| Works without Python on client | ✅ | ✅ | ✅ |
| Survives full shutdown | ❌ | ✅ | ✅ |

---

## Part 1 — System Tray

### What it does
- When user clicks X to close, app minimizes to system tray instead of exiting
- Small PGSafe icon sits in the Windows system tray (bottom right)
- Internal scheduler thread checks every minute if a backup is due and fires it
- Windows toast notification on backup success or failure
- Right-click tray menu exposes quick actions

### Tray Menu Items
```
PGSafe
─────────────────
Open PGSafe
─────────────────
Next backup: ssw in 2h
Last backup: ✓ Today 14:00
─────────────────
Run backup now
─────────────────
Exit
```

### Implementation Notes
- `QSystemTrayIcon` is built into PySide6 — no extra libraries needed
- Override `closeEvent` on `MainWindow` to hide instead of quit
- Add "Start with Windows" option that adds exe to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
- Scheduler thread: simple loop, wakes every 60 seconds, checks due schedules against current time
- Toast notifications: `winotify` library (single pip install, works in frozen exe)

---

## Part 2 — Windows Task Scheduler (Fallback)

### What it does
- When user creates a schedule in PGSafe, the app also registers a Task Scheduler task
- Task calls `pgsafe.exe --headless --schedule-id <id>`
- exe starts silently (no window), runs the backup, logs result, exits
- Covers the case where the tray app is not running — after reboot, full shutdown, user manually exited

### How it works — no Python needed
Task Scheduler just runs your compiled exe like any other program.
Registration is done by shelling out to `schtasks.exe` which is built into every Windows installation:

```
schtasks /create
  /tn "PGSafe\mydb_daily"
  /tr "C:\Users\...\pgsafe.exe --headless --schedule-id 3"
  /sc daily
  /st 14:00
  /ru "CURRENTUSER"
  /f
```

Unregistration on schedule delete:
```
schtasks /delete /tn "PGSafe\mydb_daily" /f
```

### Headless Mode in the EXE
Add CLI argument parsing at the top of `main.py`:
- `pgsafe.exe` → normal GUI launch
- `pgsafe.exe --headless --schedule-id 3` → no window, load schedule by ID, run backup, log result, exit
- `pgsafe.exe --headless --list-schedules` → print schedule status to stdout (useful for debugging)

Use Python's built-in `argparse` — works fine in frozen exe.

### Task Scheduler Settings to enable
- **"Run task as soon as possible after a scheduled start is missed"** — critical for consumer laptops that are off at the scheduled time. When the PC turns on, Windows runs the missed task automatically.
- **"Only run when user is logged on"** — simpler permissions, no password prompt
- **"Stop task if it runs longer than 1 hour"** — safety net

---

## Part 3 — Schedule Storage

### Config file
Store schedules in a JSON file next to the exe or in `%APPDATA%\PGSafe\schedules.json`.
`%APPDATA%` is the right place for per-user app data on Windows.

### Schema per schedule record
```json
{
  "id": 3,
  "label": "ssw daily",
  "db_name": "ssw",
  "host": "localhost",
  "port": 5432,
  "user": "postgres",
  "output_folder": "C:/backups/ssw",
  "filename_pattern": "{db}_{timestamp}.dump",
  "frequency": "daily",
  "days_of_week": ["mon", "wed", "fri"],
  "time": "14:00",
  "retention_keep_last": 7,
  "encrypt": false,
  "last_run_at": "2026-03-21T14:00:00",
  "last_run_status": "success",
  "last_run_file": "C:/backups/ssw/ssw_2026-03-21_14-00.dump",
  "last_run_size_mb": 24.3,
  "task_scheduler_registered": true
}
```

### Password storage — NEVER in the JSON
Use `keyring` library which stores passwords in **Windows Credential Manager** (same vault Chrome uses):
```
keyring.set_password("PGSafe", "schedule_3", "mypassword")
keyring.get_password("PGSafe", "schedule_3")
```
Works in frozen exe. Zero plaintext passwords on disk.

---

## Part 4 — Consumer Edge Cases to Handle

### PC was off at backup time
- Task Scheduler "run missed task" setting handles this automatically
- Tray scheduler catches up on next minute tick if app was sleeping

### PostgreSQL service not running
- Before backup attempt, check if port 5432 is accepting connections
- If not: log "PostgreSQL not running", show notification, skip — do NOT silently fail

### Output folder missing or disconnected (USB drive, network share)
- Check destination exists before starting backup
- Fail fast with clear message: "Backup destination not found: E:\backups"
- Do not attempt backup and produce a 0KB file

### Disk space low on destination
- Check available space on destination drive before starting
- Warn if less than 2x the last backup size is available
- Block backup if less than 500MB free

### VPN / remote database unreachable
- Quick connection test before starting (attempt TCP connect to host:port, 3 second timeout)
- Fail fast with: "Cannot reach database server at x.x.x.x:5432"

### Backup file already exists (same timestamp)
- Timestamp includes HH-MM so collisions are rare but possible
- If file exists, append `_1`, `_2` etc rather than overwriting silently

### Multiple PostgreSQL versions after upgrade
- pg_finder always scans newest version first — handles this automatically
- But log which binary was used in the backup history so it's traceable

---

## Part 5 — Retention / Cleanup

After each successful backup:
1. List all files in output folder matching the pattern for this schedule
2. Sort by creation date, newest first
3. Delete any beyond `retention_keep_last` count
4. Log what was deleted

Default retention: **keep last 7 backups**. User can change per schedule.

---

## Part 6 — New UI Panels Needed

### Schedule Panel (new sidebar item)
- List of active schedules with: name, next run time, last status badge (✓ / ✗ / ?)
- "Add Schedule" button → step-by-step wizard
- Click a schedule → edit or delete it
- Red dot on sidebar icon if any schedule failed its last run

### Add Schedule Wizard (steps)
1. Pick database (pre-fill from last used connection)
2. Set frequency: Daily / Weekly (pick days) / Custom interval
3. Set time of day
4. Set output folder (auto-suggest based on db name)
5. Set retention (default 7)
6. Optional: encrypt backup
7. Confirm — registers Task Scheduler task + saves to JSON

### History Panel (new sidebar item or tab)
- Last 30 backup runs across all schedules
- Columns: date/time, database, status, file size, duration
- Click a row to see full log output from that run
- Export history as CSV button

---

## Part 7 — Implementation Order (Suggested)

1. **CLI argument parsing** (`--headless`, `--schedule-id`) in `main.py` — foundation everything else depends on
2. **Schedule config** read/write with `%APPDATA%\PGSafe\schedules.json`
3. **Password storage** via `keyring`
4. **Headless backup runner** — reuses existing `LogicalBackup`/`PhysicalBackup`, writes result to history log
5. **Task Scheduler registration** via `schtasks.exe` subprocess calls
6. **System tray** — `QSystemTrayIcon`, override close event, tray menu
7. **In-tray scheduler thread** — 60-second tick, checks due schedules
8. **Toast notifications** via `winotify`
9. **Schedule UI panel** — list, add wizard, edit, delete
10. **History panel** — read history log, display table

---

## Dependencies to Add

| Library | Purpose | Frozen exe safe? |
|---|---|---|
| `keyring` | Windows Credential Manager password storage | ✅ |
| `winotify` | Windows toast notifications | ✅ |
| `argparse` | CLI argument parsing | ✅ (stdlib) |
| `schtasks.exe` | Task Scheduler registration | ✅ (built into Windows) |

No new dependencies for tray icon — `QSystemTrayIcon` is already in PySide6.

---

## Notes

- All of this works in a frozen PyInstaller exe — no Python needed on client
- `schtasks.exe` is available on every Windows version since XP
- `keyring` on Windows uses the Credential Manager automatically, no config needed
- The headless mode should suppress ALL Qt window creation to avoid flashing a window on Task Scheduler runs
- Test the headless path thoroughly — it runs without a user watching, errors must be logged not shown in dialogs