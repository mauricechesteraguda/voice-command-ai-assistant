import signal
import subprocess
import time
import speech_recognition as sr

from ollama import Client

from gtts import gTTS

import os

import re

import multiprocessing

import psutil


# Define the directory path where the speech files are located
speech_dir = "speeches/"

is_talking = False
is_stop = False
pr = []

# global is_stop
# is_stop = False

client = Client(host="http://localhost:11434")
tempo_ratio = 1.3


def kill_child_processes(parent_pid, sig=signal.SIGTERM):
    try:
        parent = psutil.Process(parent_pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for process in children:
        process.send_signal(sig)


def listen_for_command():
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        print("Listening for command...")
        recognizer.adjust_for_ambient_noise(source)  # Adjust for ambient noise
        audio = recognizer.listen(source)

    try:
        print("Recognizing command...")
        command = recognizer.recognize_google(audio)
        print("You said:", command)
        return command
    except sr.UnknownValueError:
        print("Sorry, I didn't catch that. Please try again.")
        return None
    except sr.RequestError as e:
        print(
            "Could not request results from Google Speech Recognition service; {0}".format(
                e
            )
        )
        return None


system_message = "You are a helpful AI assistant. Make your answers to my queries short but very informative as much as possible especially if i am not asking about codes. If the user wanted a much shorter response, do it. Now my query is "


def queue_message(command):
    # Regular expression pattern to match sentence endings (. ! ?)
    sentence_endings = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|!)\s"
    sentences = re.split(sentence_endings, command)
    # Remove any empty strings in the list
    sentences = [sentence.strip() for sentence in sentences if sentence.strip() != ""]
    return sentences


def process_command(command):
    global is_talking
    global is_stop
    global pr
    is_stop = False

    if (
        "end now" in command
        or "end statement" in command
        or "stop now" in command
        or "shut up" in command
        or "shutup" in command
        or "terminate now" in command
    ):
        is_stop = True
        print("Cancelling current response...")
    else:
        response = client.chat(
            model="llama2:7b",
            messages=[
                {
                    "role": "user",
                    "content": system_message + command,
                },
            ],
        )
        print(response["message"]["content"])

        sentences = queue_message(response["message"]["content"])

        i = 0
        while i < len(sentences):
            m = sentences[i]
            generate_speech(m, i, sentences)
            i += 1
            if is_stop:
                break

        is_talking = False


def generate_speech(text, i, sentences):
    global is_talking
    global pr
    tts = gTTS(text, slow=False)
    tts.save(speech_dir + "speech" + str(i) + ".mp3")
    if not is_talking:
        if i == 0:
            # Create a Process object to run the custom_function with a parameter
            process = multiprocessing.Process(target=speak, args=(len(sentences),))
            process.start()  # Start the process

        else:
            speak(sentences)

        is_talking = True


def speak(num_sentences):
    global is_stop
    time.sleep(1)

    for i in range(num_sentences):
        command = [
            "mplayer",
            "-af",
            "scaletempo",
            "-speed",
            "1.3",
            f"speeches/speech{i}.mp3",
        ]
        subprocess.run(command)
        if is_stop:
            break


if __name__ == "__main__":
    # Create a list of all files in the speech dir
    files = [f for f in os.listdir(speech_dir) if "speech" in f]

    # Iterate over the list of files and delete each one
    for file in files:
        file_path = os.path.join(speech_dir, file)
        if os.path.isfile(file_path):
            os.remove(file_path)

    while True:
        command = listen_for_command()
        if command and command.lower() == "exit":
            print("Exiting...")
            break
        elif command and (
            "end now" in command
            or "end statement" in command
            or "stop now" in command
            or "shut up" in command
            or "shutup" in command
            or "terminate now" in command
        ):
            print(pr)
            for p in pr:
                try:
                    # # Terminate the process using its PID
                    # os.kill(p, signal.SIGTERM)
                    kill_child_processes(p.pid, signal.SIGTERM)

                    # p.terminate()
                    print("Processes killed...")
                    print("Cancelling current response...")
                except:
                    print("process killing failed...")
            os.kill(p.pid, signal.SIGTERM)
            pr = []

        elif command:
            # Create a Process object to run the custom_function with a parameter
            process = multiprocessing.Process(target=process_command, args=(command,))
            process.start()  # Start the process
            # Get the PID of the process
            print(pr)
            pr.append(process)
            print(pr)
            # # process.join()   # Wait for the process to complete (optional)
            # process_command(command)
