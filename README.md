# Mi Fitness to Strava Auto-Sync

An all-in-one Python tool to automatically extract, process, and bulk-upload your historical workout data from Xiaomi Mi Fitness to Strava.

Unlike standard integrations that only sync *new* workouts, this script allows you to import your entire history and ensures your **Heart Rate (HR) data** is flawlessly mapped and injected into your GPX files before bulk-uploading them.

## Features
- **Auto-Download:** Fetches your RAW `.gpx` tracks from Xiaomi's servers using your local export logs.
- **Heart Rate Injection:** Automatically maps and injects your Xiaomi heart rate data into the GPS `.gpx` files with exact timestamps.
- **Strava Bulk Upload ☁️:** Safely bulk uploads your workouts to Strava.
- **Smart Rate Limiting:** Built-in API sleep regulators that guarantee you will never hit Strava's rate limits (neither overall nor read limits).
- **Incremental & Resumable:** Safely skips pre-downloaded routes and already-uploaded activities. If you stop the script halfway, it flawlessly resumes where it left off.

---

## 1. How to Export Your Data from Xiaomi (Mi Fitness)

To use this script, you first need to request a data export from Xiaomi:

1. Go to the [Xiaomi Privacy Center](https://privacy.mi.com/all/en_US/).
2. Log in with the account you use on the Mi Fitness App.
3. Request your data export (you may have to specifically select "Mi Fitness").
4. Wait for Xiaomi to email you a password-protected `.zip` file (this usually takes a few days).
5. Extract the `.zip` file using the password they provide.

You will see several `.csv` files. The script will automatically locate the ones it needs:
- `*_MiFitness_hlth_center_sport_track_data.csv`
- `*_MiFitness_hlth_center_fitness_data.csv`
- `*_MiFitness_hlth_center_sport_record.csv`

## 2. Preparing the Environment

1. Install Python (3.7 or newer).
2. Install the required Python libraries using your terminal:
   ```bash
   pip install pandas requests
   ```
3. Place this Python script (e.g. `syncfit.py`) in the **exact same folder** as the `.csv` files exported from Xiaomi.

## 3. Strava API Setup (First Time Only)

To let the script upload workouts to your Strava account safely, you need your own App API tokens:

1. Go to [Strava API Settings](https://www.strava.com/settings/api).
2. Create an App (you can name it whatever you want, and set "Authorization Callback Domain" to `localhost`).
3. You will obtain a **Client ID** and a **Client Secret**.

## 4. Usage

Run the script from your terminal:
```bash
python syncfit.py
```

**First time workflow:**
1. The script will notice you haven't configured your credentials and will generate a local `secrets.json` file.
2. Open `secrets.json` with a text editor and paste your **Client ID** and **Client Secret**. Leave `REFRESH_TOKEN` empty.
3. Run the script again. It will automatically print an authorization URL in your terminal. Open it in your browser, **ensure you check the "Upload your activities/Subir actividades" box**, and click Authorize.
4. You will be redirected to an error or blank `localhost` page. Copy the `code=XXXXXX` string from the URL and paste it back into your terminal.
5. The script automatically handles the rest, securing your tokens locally so you never have to do this again.

**The Interactive Menu:**
When running the script, you'll be greeted with an interactive console menu:
* **[1] Run EVERYTHING:** Downloads GPX, maps HR data locally, and uploads to Strava automatically.
* **[2] Local Phase Only:** Only downloads GPX and creates perfected HR-injected files without touching Strava.
* **[3] Cloud Phase Only:** Sweeps the processed GPX folder and strictly handles the Strava Upload queue.

Sit back and watch as your entire Xiaomi history accurately populates your Strava account!
