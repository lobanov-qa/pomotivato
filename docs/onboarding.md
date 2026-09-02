# Pomotivato — getting started

Pomotivato is a desktop pomodoro timer with a task funnel and an
after-the-fact focus rating. One local app, no accounts, no cloud, no
telemetry: all data lives in a single SQLite file on your machine.

## The idea in one paragraph

Tasks flow through a funnel: **Backlog → Planned → Doing → Done/Archive**.
The day's "Doing" tasks form a dial of 1..12 sectors (6 by default). Start a
block, the minute hand sweeps your sector, time is up — you rate your focus
1..5 with an optional comment, take a break, and the next sector begins.
Averages, streaks and estimate-vs-actual statistics come from your own
ratings. Tasks may optionally carry goal fields (definition of done,
if–then plan, importance/urgency quadrant); filling them in is never
required — a task can be created in 5 seconds with just a title.

## Install & run

Binaries are published on the GitHub Releases page; setup instructions
appear here with the first release. During development there is no public
entry point yet.

## User data locations

- Linux: `~/.local/share/pomotivato/`
- Windows: `%APPDATA%\Pomotivato\`

Deleting that directory removes all app data (it is local-only by design).

## Troubleshooting

- App won't start: look at the console output for the first error line;
  make sure no other instance is already running.
- Lost data: nothing is synced anywhere — recover from your own backups of
  the data directory.
