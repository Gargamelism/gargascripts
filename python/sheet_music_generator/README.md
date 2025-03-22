1. **Install Dependencies**:
    Ensure you have all the required dependencies installed. You can use the provided `requirements.txt` file to install them.
    ```sh
    pip install -r requirements.txt
    ```

2.  **Install Mp3 conversion dependencies, and download the sound font (sf2 file)**
    ```sh
    sudo apt-get install fluidsynth
    mkdir -p ~/soundfonts
    wget https://musical-artifacts.com/artifacts/6045/02._St._Piano_2_Remastered.sf2  -O ~/soundfonts/st_piano.sf2
    ```

4. **Run the Script**:
    Execute the script using Python. Navigate to the directory containing `sheet_music_generator.py` and run:
    ```sh
    python sheet_music_generator.py
    ```
