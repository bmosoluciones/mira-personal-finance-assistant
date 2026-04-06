# Using the portable MIRA `.zip` on Windows (no installer)

This guide is for advanced Windows users who **cannot install programs** with an `.exe` installer and need to run MIRA from the portable `.zip` package.

## Target result

At the end of this guide you will have:

- The portable MIRA files extracted into a stable directory that is unlikely to be deleted by accident.
- A desktop shortcut to quickly open MIRA.
- (Optional) A Start Menu entry for easier launch.

## 1) Download the portable `.zip`

1. Open: `https://mira.bmogroup.solutions/releases/`
2. Download the latest Windows portable archive (the `.zip` artifact).
3. Do **not** run the file from Downloads directly.

## 2) Choose a safe extraction folder

Avoid temporary or auto-cleaned directories such as:

- `Downloads`
- `Desktop` (if your organization auto-cleans profiles)
- `%TEMP%`

Recommended stable location:

- `%LOCALAPPDATA%\Programs\MIRA\`

Create the folder if needed and extract the `.zip` there.

Example final executable path:

- `%LOCALAPPDATA%\Programs\MIRA\MIRA.exe`

## 3) Launch once to validate

Double-click `MIRA.exe` from the extracted directory.

If Windows SmartScreen appears:

1. Click **More info**.
2. Click **Run anyway**.

## 4) Create a desktop shortcut

1. Open the extraction folder.
2. Right-click `MIRA.exe` -> **Send to** -> **Desktop (create shortcut)**.
3. Rename shortcut to `MIRA` if desired.

This gives non-admin users a convenient launcher without installing software system-wide.

## 5) Optional: add a Start Menu entry

You can add a per-user Start Menu shortcut (no admin rights needed):

1. Press `Win + R`, run:

   ```text
   shell:programs
   ```

2. In the opened folder, create a shortcut pointing to:

   ```text
   %LOCALAPPDATA%\Programs\MIRA\MIRA.exe
   ```

3. Name it `MIRA`.

MIRA should now appear in the user Start Menu search.

## 6) Update workflow for new versions

Because this is a portable install:

1. Download the new `.zip` release.
2. Close MIRA.
3. Replace the files in `%LOCALAPPDATA%\Programs\MIRA\`.
4. Re-open from the existing shortcut (desktop and Start Menu shortcuts continue working if `MIRA.exe` path remains the same).

## Troubleshooting

- **Shortcut does not open MIRA:** verify `Target` points to the current `MIRA.exe` path.
- **App disappears after cleanup:** move installation from volatile folders (Downloads/Desktop/temp) to `%LOCALAPPDATA%\Programs\MIRA\`.
- **Blocked by policy:** some organizations block unsigned binaries; request IT allowlisting for MIRA.
