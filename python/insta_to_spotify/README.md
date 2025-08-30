# 📸 Insta to Spotify

A Python tool that extracts media from Instagram and matches the content to tracks on Spotify using the Spotify API.

---

## 🚀 Features

* Download Instagram posts, stories, or reels using `yt-dlp`
* Extract audio and process media using `ffmpeg`
* Match and add tracks to a Spotify playlist

---

## 🛠 Requirements

* Python 3.8 or newer
* `ffmpeg` and `ffprobe` in your system PATH
* Spotify Developer credentials
* Browser cookies for Instagram access

---

## ⚙️ Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/your-username/insta-to-spotify.git
   cd insta-to-spotify
   ```

2. Create a virtual environment:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # On Windows
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Install `ffmpeg` if not already installed:

   * [Download FFmpeg](https://www.gyan.dev/ffmpeg/builds/)
   * Extract it and add the `bin` folder to your system `PATH`
   * Verify with:

     ```bash
     ffmpeg -version
     ffprobe -version
     ```

---

## 🔐 Spotify API Setup

To enable Spotify integration, you need to provide API credentials in a `.env` file.

### 1. Create a Spotify Developer App

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Click **"Create an App"**
3. Note your **Client ID** and **Client Secret**
4. Set **Redirect URI** to:

   ```
   http://localhost:8888/callback
   ```

### 2. Create a `.env` File

At the root of the project, add a file named `.env`:

```env
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://localhost:8888/callback
```

> ⚠️ **Do not share your `.env` file.** Be sure to include `.env` in your `.gitignore`.

---

## 🧪 Usage

Run the script:

```bash
python main.py
```

The script will:

* Load your environment variables
* Fetch Instagram media
* Match audio to Spotify tracks
* Add them to your playlist

---

## ❓ Troubleshooting

### `ModuleNotFoundError: No module named 'audioop'`

* You're likely using **Python 3.13+**. Fix it by running:

  ```bash
  pip install audioop-lts
  ```

### `ffmpeg or ffprobe not found`

* Make sure FFmpeg is installed and added to your system `PATH`.

### `RuntimeError: Missing Spotify credentials`

* Ensure your `.env` file is correctly filled with the required keys.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
