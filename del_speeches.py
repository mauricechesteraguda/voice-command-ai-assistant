import os

# Define the directory path where the speech files are located
speech_dir = "speeches/"

# Create a list of all files in the speech dir
files = [f for f in os.listdir(speech_dir) if "speech" in f]

# Iterate over the list of files and delete each one
for file in files:
    file_path = os.path.join(speech_dir, file)
    if os.path.isfile(file_path):
        os.remove(file_path)
